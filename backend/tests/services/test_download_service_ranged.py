"""Phase 21 — tải đa luồng qua HTTP Range. Test riêng khỏi
test_download_service.py (test Phase 20 — giới hạn số video) vì đây test 1
tầng khác hẳn: giới hạn số KẾT NỐI cho MỖI video.

Tiêu chí quan trọng nhất (xem Definition of Done ở phase-21): file tải theo
Range phải GIỐNG HỆT file tải 1 luồng, byte-for-byte — không chỉ "gần đúng".
"""

import asyncio
import hashlib

import httpx
import pytest

from app.core.config import get_settings
from app.services import download_service, progress_service


@pytest.fixture(autouse=True)
def _small_part_threshold(monkeypatch: pytest.MonkeyPatch):
    """`download_part_min_bytes` mặc định 8MB — quá lớn cho test đơn vị (tải
    thật 8MB mỗi test thì chậm). Hạ xuống 200 byte để các test dùng nội dung
    vài trăm byte/vài chục KB vẫn thật sự đi qua nhánh chia phần, không lặng
    lẽ rơi về fallback vì "chưa đủ lớn"."""
    monkeypatch.setenv("DOWNLOAD_PART_MIN_BYTES", "200")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _content(size: int) -> bytes:
    """Nội dung giả nhưng KHÔNG lặp lại đều — nếu code ghi nhầm offset (vd lệch
    1 byte, hoặc 2 phần ghi đè lên nhau), so sánh với nội dung ngẫu nhiên kiểu
    này chắc chắn phát hiện ra; nội dung toàn 1 byte lặp lại (vd b"\\x00" * n)
    sẽ không phát hiện được lỗi lệch offset."""
    return bytes((i * 2654435761) % 256 for i in range(size))


def _mock_ranged_transport(content: bytes, *, supports_range: bool = True) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            headers = {"content-length": str(len(content))}
            if supports_range:
                headers["accept-ranges"] = "bytes"
            return httpx.Response(200, headers=headers)

        range_header = request.headers.get("range")
        if range_header is None:
            return httpx.Response(200, content=content)

        assert supports_range, "test không nên gửi Range nếu server báo không hỗ trợ"
        raw = range_header.removeprefix("bytes=")
        start_s, end_s = raw.split("-")
        start, end = int(start_s), int(end_s)
        chunk = content[start : end + 1]
        return httpx.Response(
            206,
            content=chunk,
            headers={"content-range": f"bytes {start}-{end}/{len(content)}"},
        )

    return httpx.MockTransport(handle)


@pytest.fixture(autouse=True)
def _clear_progress():
    yield
    progress_service.clear(1)


class TestSplitRanges:
    def test_covers_whole_file_no_gap_no_overlap(self) -> None:
        ranges = download_service._split_ranges(100, 3)
        covered: set[int] = set()
        for start, end in ranges:
            span = set(range(start, end + 1))
            assert not (span & covered), "2 khoảng đè lên nhau"
            covered |= span
        assert covered == set(range(100))

    def test_single_part_covers_everything(self) -> None:
        assert download_service._split_ranges(50, 1) == [(0, 49)]

    @pytest.mark.parametrize("size,parts", [(1000, 8), (17, 4), (1, 1), (7, 3)])
    def test_covers_whole_file_various_sizes(self, size: int, parts: int) -> None:
        ranges = download_service._split_ranges(size, parts)
        assert len(ranges) == parts
        assert ranges[0][0] == 0
        assert ranges[-1][1] == size - 1
        for (a_start, a_end), (b_start, _b_end) in zip(ranges, ranges[1:]):
            assert a_end + 1 == b_start


class TestProbe:
    @pytest.mark.anyio
    async def test_detects_range_support(self) -> None:
        content = _content(1000)
        async with httpx.AsyncClient(transport=_mock_ranged_transport(content)) as client:
            size, supports_range = await download_service._probe(client, "https://x/test")
        assert size == 1000
        assert supports_range is True

    @pytest.mark.anyio
    async def test_detects_no_range_support(self) -> None:
        content = _content(1000)
        transport = _mock_ranged_transport(content, supports_range=False)
        async with httpx.AsyncClient(transport=transport) as client:
            size, supports_range = await download_service._probe(client, "https://x/test")
        assert size == 1000
        assert supports_range is False

    @pytest.mark.anyio
    async def test_non_200_returns_unknown(self) -> None:
        transport = httpx.MockTransport(lambda r: httpx.Response(404))
        async with httpx.AsyncClient(transport=transport) as client:
            size, supports_range = await download_service._probe(client, "https://x/test")
        assert size is None
        assert supports_range is False


class TestDownloadStreamMatchesSingleConnection:
    """Tiêu chí quan trọng nhất: file tải đa luồng phải giống hệt file tải 1
    luồng, byte-for-byte — không phải "gần đúng" (xem DoD phase-21)."""

    @pytest.mark.anyio
    async def test_ranged_output_matches_single_connection_output(self, tmp_path) -> None:
        content = _content(500_000)
        transport = _mock_ranged_transport(content)

        single_dest = tmp_path / "single.bin"
        ranged_dest = tmp_path / "ranged.bin"

        async with httpx.AsyncClient(transport=transport) as client:
            await download_service._download_stream(
                client, "https://x/test", single_dest,
                connections=1, slots=asyncio.Semaphore(4),
                video_id=None, known_size=len(content), supports_range=True,
            )
            await download_service._download_stream(
                client, "https://x/test", ranged_dest,
                connections=8, slots=asyncio.Semaphore(4),
                video_id=None, known_size=len(content), supports_range=True,
            )

        single_bytes = single_dest.read_bytes()
        ranged_bytes = ranged_dest.read_bytes()

        assert single_bytes == content
        assert ranged_bytes == content
        assert hashlib.sha256(single_bytes).hexdigest() == hashlib.sha256(ranged_bytes).hexdigest()

    @pytest.mark.anyio
    async def test_connections_1_never_sends_range_header(self, tmp_path) -> None:
        """`connections<=1` phải đi thẳng đường cũ (fallback), không qua nhánh
        chia phần — kể cả khi server có hỗ trợ Range (xem thiết kế phase-21:
        mặc định không đổi hành vi cũ)."""
        content = _content(1000)
        seen_range_header = False

        def handle(request: httpx.Request) -> httpx.Response:
            nonlocal seen_range_header
            if request.method == "HEAD":
                return httpx.Response(
                    200, headers={"content-length": "1000", "accept-ranges": "bytes"}
                )
            if "range" in request.headers:
                seen_range_header = True
            return httpx.Response(200, content=content)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            await download_service._download_stream(
                client, "https://x/test", tmp_path / "out.bin",
                connections=1, slots=asyncio.Semaphore(4),
                video_id=None, known_size=1000, supports_range=True,
            )

        assert seen_range_header is False

    @pytest.mark.anyio
    async def test_falls_back_when_server_does_not_support_range(self, tmp_path) -> None:
        content = _content(1000)
        transport = _mock_ranged_transport(content, supports_range=False)

        async with httpx.AsyncClient(transport=transport) as client:
            await download_service._download_stream(
                client, "https://x/test", tmp_path / "out.bin",
                connections=8, slots=asyncio.Semaphore(4),
                video_id=None, known_size=1000, supports_range=False,
            )

        assert (tmp_path / "out.bin").read_bytes() == content

    @pytest.mark.anyio
    async def test_falls_back_when_size_below_threshold(self, tmp_path) -> None:
        content = _content(100)  # nhỏ hơn download_part_min_bytes mặc định
        transport = _mock_ranged_transport(content)

        async with httpx.AsyncClient(transport=transport) as client:
            await download_service._download_stream(
                client, "https://x/test", tmp_path / "out.bin",
                connections=8, slots=asyncio.Semaphore(4),
                video_id=None, known_size=100, supports_range=True,
            )

        assert (tmp_path / "out.bin").read_bytes() == content

    @pytest.mark.anyio
    async def test_falls_back_when_size_unknown(self, tmp_path) -> None:
        content = _content(1000)
        transport = _mock_ranged_transport(content)

        async with httpx.AsyncClient(transport=transport) as client:
            await download_service._download_stream(
                client, "https://x/test", tmp_path / "out.bin",
                connections=8, slots=asyncio.Semaphore(4),
                video_id=None, known_size=None, supports_range=True,
            )

        assert (tmp_path / "out.bin").read_bytes() == content


class TestConnectionSlotsLimit:
    """Semaphore kết nối phải giới hạn đúng số worker Range chạy thật cùng lúc
    — bất kể 1 video xin nhiều phần hay nhiều video cùng tải (Phase 20+21
    dùng chung 1 hàng rào, xem docs/phases/phase-21-parallel-download.md)."""

    @pytest.mark.anyio
    async def test_limits_concurrent_range_requests(self, tmp_path) -> None:
        size = 800  # > ngưỡng test (200) để chắc chắn đi qua nhánh chia phần
        content = _content(size)
        concurrent = 0
        max_concurrent = 0
        lock = asyncio.Lock()

        async def handle(request: httpx.Request) -> httpx.Response:
            nonlocal concurrent, max_concurrent
            if request.method == "HEAD":
                return httpx.Response(
                    200, headers={"content-length": str(size), "accept-ranges": "bytes"}
                )
            async with lock:
                concurrent += 1
                max_concurrent = max(max_concurrent, concurrent)
            await asyncio.sleep(0.02)
            async with lock:
                concurrent -= 1
            range_header = request.headers["range"].removeprefix("bytes=")
            start, end = (int(x) for x in range_header.split("-"))
            return httpx.Response(
                206,
                content=content[start : end + 1],
                headers={"content-range": f"bytes {start}-{end}/{size}"},
            )

        transport = httpx.MockTransport(handle)
        slots = asyncio.Semaphore(2)

        async with httpx.AsyncClient(transport=transport) as client:
            await download_service._download_stream(
                client, "https://x/test", tmp_path / "out.bin",
                connections=8, slots=slots,
                video_id=None, known_size=size, supports_range=True,
            )

        assert max_concurrent == 2
        assert (tmp_path / "out.bin").read_bytes() == content


class TestRangePartRetry:
    @pytest.mark.anyio
    async def test_retries_failed_part_without_duplicating_progress(self, tmp_path) -> None:
        content = _content(40)
        attempts = 0

        async def handle(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise httpx.ConnectError("giả lập mất mạng giữa chừng")
            range_header = request.headers["range"].removeprefix("bytes=")
            start, end = (int(x) for x in range_header.split("-"))
            return httpx.Response(
                206,
                content=content[start : end + 1],
                headers={"content-range": f"bytes {start}-{end}/40"},
            )

        transport = httpx.MockTransport(handle)
        dest = tmp_path / "out.bin"
        with open(dest, "wb") as f:
            f.truncate(40)

        progress_service.start(1, "test")
        progress_service.set_stage(1, "downloading", 40, kind="download")

        async with httpx.AsyncClient(transport=transport) as client:
            await download_service._download_range_part(
                client, "https://x/test", dest, 0, 39, video_id=1, slots=asyncio.Semaphore(1)
            )

        assert dest.read_bytes() == content
        task = next(p for p in progress_service.snapshot() if p.video_id == 1)
        # Đúng 40 byte, không phải 80 (nếu retry cộng dồn nhầm cả lần lỗi).
        assert task.current == 40

    @pytest.mark.anyio
    async def test_gives_up_after_max_attempts(self, tmp_path) -> None:
        async def always_fail(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("mất mạng vĩnh viễn")

        transport = httpx.MockTransport(always_fail)
        dest = tmp_path / "out.bin"
        with open(dest, "wb") as f:
            f.truncate(10)

        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(httpx.ConnectError):
                await download_service._download_range_part(
                    client, "https://x/test", dest, 0, 9, video_id=None, slots=asyncio.Semaphore(1)
                )


class TestDownloadBilibiliVideoSlot:
    """`_download_bilibili_video_slot` — lớp keo nối `get_play_streams` → tải
    video+audio SONG SONG → ghép ffmpeg. Trọng tâm: 1 stage "downloading" duy
    nhất với tổng dung lượng = video + audio, không phải 2 chặng nối tiếp như
    trước Phase 21 (xem thiết kế trong phase-21-parallel-download.md)."""

    @pytest.mark.anyio
    async def test_merges_video_and_audio_into_single_stage_total(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        video_bytes = _content(1000)
        audio_bytes = _content(300)

        def handle(request: httpx.Request) -> httpx.Response:
            is_video = "video" in str(request.url)
            content = video_bytes if is_video else audio_bytes
            if request.method == "HEAD":
                return httpx.Response(
                    200,
                    headers={
                        "content-length": str(len(content)),
                        "accept-ranges": "bytes",
                    },
                )
            range_header = request.headers.get("range")
            if range_header is None:
                return httpx.Response(200, content=content)
            raw = range_header.removeprefix("bytes=")
            start, end = (int(x) for x in raw.split("-"))
            chunk = content[start : end + 1]
            return httpx.Response(
                206,
                content=chunk,
                headers={"content-range": f"bytes {start}-{end}/{len(content)}"},
            )

        transport = httpx.MockTransport(handle)
        real_async_client = httpx.AsyncClient

        class _ClientFactory:
            def __call__(self, *args, **kwargs):
                kwargs["transport"] = transport
                return real_async_client(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", _ClientFactory())

        class FakeBilibiliClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get_play_streams(self, bvid, cid):
                return {
                    "video": [{"baseUrl": "https://x/video-stream"}],
                    "audio": [{"baseUrl": "https://x/audio-stream"}],
                }

        monkeypatch.setattr(download_service, "BilibiliClient", FakeBilibiliClient)

        merge_calls = []

        def fake_merge(video_path, audio_path, output_path):
            # Đọc NGAY trong lúc ghép — hàm thật xoá 2 file tạm này ngay sau
            # khi ghép xong, đọc lại sau khi hàm trả về sẽ luôn ra FileNotFound.
            merge_calls.append(
                (video_path.read_bytes(), audio_path.read_bytes(), output_path)
            )
            # ffmpeg thật sẽ tạo ra file output — giả lập bằng cách ghi tạm.
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"fake merged mp4")

        monkeypatch.setattr(download_service.ffmpeg, "merge_video_audio", fake_merge)
        monkeypatch.setattr(download_service, "_STORAGE_ROOT", tmp_path)

        stages_seen: list[tuple[str, int | None]] = []
        original_set_stage = progress_service.set_stage

        def spy_set_stage(video_id, stage, total=None, **kwargs):
            stages_seen.append((stage, total))
            return original_set_stage(video_id, stage, total, **kwargs)

        monkeypatch.setattr(download_service.progress_service, "set_stage", spy_set_stage)
        progress_service.start(1, "test")

        output_path = await download_service._download_bilibili_video_slot(
            job_id=1, video_id=1, bvid="BV1", cid=1, connections=4
        )

        assert output_path.read_bytes() == b"fake merged mp4"
        assert len(merge_calls) == 1
        merged_video_bytes, merged_audio_bytes, _ = merge_calls[0]
        assert merged_video_bytes == video_bytes
        assert merged_audio_bytes == audio_bytes

        # Đúng 1 chặng "downloading" duy nhất, tổng = video + audio — không
        # phải 2 chặng "video" rồi "audio" nối tiếp như hành vi trước Phase 21.
        downloading_stages = [s for s in stages_seen if s[0] == "downloading"]
        assert downloading_stages == [("downloading", len(video_bytes) + len(audio_bytes))]
        assert ("video", None) not in stages_seen
        assert ("audio", None) not in stages_seen


class TestRangeNotHonored:
    @pytest.mark.anyio
    async def test_falls_back_to_whole_file_when_cdn_ignores_range(self, tmp_path) -> None:
        """CDN báo `accept-ranges: bytes` ở HEAD nhưng GET thật lại trả 200
        (cả file) thay vì 206 — hiếm nhưng đã ghi nhận, không được ghi đè lung
        tung tạo file hỏng (xem docs/phases/phase-21-parallel-download.md)."""
        content = _content(1000)

        def handle(request: httpx.Request) -> httpx.Response:
            if request.method == "HEAD":
                return httpx.Response(
                    200, headers={"content-length": "1000", "accept-ranges": "bytes"}
                )
            # Nói dối: trả 200 + cả file thay vì 206 dù có header Range.
            return httpx.Response(200, content=content)

        transport = httpx.MockTransport(handle)
        dest = tmp_path / "out.bin"

        async with httpx.AsyncClient(transport=transport) as client:
            await download_service._download_stream(
                client, "https://x/test", dest,
                connections=4, slots=asyncio.Semaphore(4),
                video_id=None, known_size=1000, supports_range=True,
            )

        assert dest.read_bytes() == content
