"""Test adapter fal.ai thật bằng HTTP giả.

Phạm vi có ý nghĩa của bộ test này: **cơ chế** (header xác thực, luồng hàng đợi,
phân loại lỗi, an toàn khi tải file). Nó KHÔNG chứng minh được đường dẫn model hay
tên trường đầu vào là đúng — những thứ đó chỉ có key thật mới kiểm được, và đã
đánh dấu rõ trong docstring của `client.py`.
"""

from pathlib import Path

import httpx
import pytest

from app.adapters.falai import client as falai
from app.adapters.falai.errors import PromptBlockedError
from app.adapters.provider_errors import ProviderQuotaExceededError

_SUBMITTED = {
    "request_id": "req-1",
    "status_url": "https://queue.fal.run/status/req-1",
    "response_url": "https://queue.fal.run/result/req-1",
}


def _transport(
    *,
    submit: httpx.Response | None = None,
    statuses: list[httpx.Response] | None = None,
    result: httpx.Response | None = None,
    media: httpx.Response | None = None,
    seen: list[httpx.Request] | None = None,
) -> httpx.MockTransport:
    status_queue = list(statuses or [httpx.Response(200, json={"status": "COMPLETED"})])

    def handle(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        url = str(request.url)
        if request.method == "POST":
            return submit or httpx.Response(200, json=_SUBMITTED)
        if url == _SUBMITTED["status_url"]:
            return status_queue.pop(0) if status_queue else httpx.Response(
                200, json={"status": "COMPLETED"}
            )
        if url == _SUBMITTED["response_url"]:
            return result or httpx.Response(
                200, json={"images": [{"url": "https://cdn.fal/x.png"}]}
            )
        return media or httpx.Response(200, content=b"noi-dung-file")

    return httpx.MockTransport(handle)


async def _run_image(transport: httpx.MockTransport, output: Path) -> None:
    async with httpx.AsyncClient(transport=transport) as client:
        await falai._run(
            client, "k-123", "fal-ai/nano-banana", {"prompt": "x"}, output, kind="image"
        )


class TestEndpointMapping:
    def test_unknown_model_names_the_known_ones(self) -> None:
        """Model lạ phải báo rõ đang có gì — bảng này chắc chắn sẽ phải sửa khi
        fal.ai đổi tên model."""
        with pytest.raises(falai.GenerationError, match="nano-banana"):
            falai.resolve_endpoint("model-khong-ton-tai")

    def test_known_model_resolves(self) -> None:
        assert falai.resolve_endpoint("kling-3.0").startswith("fal-ai/")


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_downloads_result_to_output_path(self, tmp_path: Path) -> None:
        output = tmp_path / "out.png"
        await _run_image(_transport(), output)
        assert output.read_bytes() == b"noi-dung-file"

    @pytest.mark.asyncio
    async def test_uses_key_prefix_not_bearer(self, tmp_path: Path) -> None:
        """fal.ai dùng `Authorization: Key ...`; gửi `Bearer` sẽ bị 401."""
        seen: list[httpx.Request] = []
        await _run_image(_transport(seen=seen), tmp_path / "out.png")
        assert seen[0].headers["Authorization"] == "Key k-123"

    @pytest.mark.asyncio
    async def test_polls_until_completed(self, tmp_path: Path, monkeypatch) -> None:
        seen: list[httpx.Request] = []
        transport = _transport(
            statuses=[
                httpx.Response(200, json={"status": "IN_QUEUE"}),
                httpx.Response(200, json={"status": "IN_PROGRESS"}),
                httpx.Response(200, json={"status": "COMPLETED"}),
            ],
            seen=seen,
        )
        # Không để test ngồi chờ 2s/lần hỏi như lúc chạy thật. Dùng monkeypatch
        # chứ không gán thẳng: gán thẳng sẽ để nguyên giá trị 0 cho mọi test sau.
        monkeypatch.setattr(falai, "_POLL_INTERVAL_SECONDS", 0)
        await _run_image(transport, tmp_path / "out.png")

        status_calls = [r for r in seen if str(r.url) == _SUBMITTED["status_url"]]
        assert len(status_calls) == 3


class TestErrorClassification:
    @pytest.mark.asyncio
    async def test_429_becomes_quota_error_so_pool_rotates(self, tmp_path: Path) -> None:
        transport = _transport(submit=httpx.Response(429, json={"detail": "rate limit"}))
        with pytest.raises(ProviderQuotaExceededError):
            await _run_image(transport, tmp_path / "out.png")

    @pytest.mark.asyncio
    async def test_policy_rejection_becomes_prompt_blocked(self, tmp_path: Path) -> None:
        """Đổi key cũng bị chặn y hệt — phải phân biệt với lỗi quota, nếu không
        service sẽ đốt sạch key trong pool cho một prompt không bao giờ qua được."""
        transport = _transport(
            submit=httpx.Response(422, json={"detail": "Blocked by content policy"})
        )
        with pytest.raises(PromptBlockedError):
            await _run_image(transport, tmp_path / "out.png")

    @pytest.mark.asyncio
    async def test_other_400_is_plain_generation_error(self, tmp_path: Path) -> None:
        transport = _transport(submit=httpx.Response(400, json={"detail": "thiếu prompt"}))
        with pytest.raises(falai.GenerationError, match="thiếu prompt"):
            await _run_image(transport, tmp_path / "out.png")

    @pytest.mark.asyncio
    async def test_failed_job_raises(self, tmp_path: Path) -> None:
        transport = _transport(
            statuses=[httpx.Response(200, json={"status": "FAILED", "detail": "hỏng"})]
        )
        with pytest.raises(falai.GenerationError, match="thất bại"):
            await _run_image(transport, tmp_path / "out.png")

    @pytest.mark.asyncio
    async def test_submit_without_status_url_raises(self, tmp_path: Path) -> None:
        """Giao thức đổi thì phải biết ngay, không được chạy tiếp với dict rỗng."""
        transport = _transport(submit=httpx.Response(200, json={"request_id": "x"}))
        with pytest.raises(falai.GenerationError, match="status_url"):
            await _run_image(transport, tmp_path / "out.png")


class TestResultParsing:
    def test_image_url_from_list(self) -> None:
        url = falai._extract_media_url({"images": [{"url": "u"}]}, kind="image")
        assert url == "u"

    def test_video_url_from_object(self) -> None:
        url = falai._extract_media_url({"video": {"url": "v"}}, kind="video")
        assert url == "v"

    def test_missing_url_lists_available_keys(self) -> None:
        """Thông báo lỗi phải chỉ ra chỗ cần nhìn, vì đây đúng là chỗ dễ sai nhất."""
        with pytest.raises(falai.GenerationError, match="output"):
            falai._extract_media_url({"output": "?", "seed": 1}, kind="image")


class TestDownloadSafety:
    @pytest.mark.asyncio
    async def test_empty_file_is_rejected_and_not_left_behind(self, tmp_path: Path) -> None:
        """File rỗng nằm đúng chỗ cache mong đợi sẽ bị coi là "đã sinh rồi" —
        lần sau bấm lại sẽ trả về file hỏng đó thay vì sinh lại."""
        output = tmp_path / "out.png"
        transport = _transport(media=httpx.Response(200, content=b""))
        with pytest.raises(falai.GenerationError, match="rỗng"):
            await _run_image(transport, output)

        assert not output.exists()
        assert list(tmp_path.glob("*.part")) == [], "không được để lại file tải dở"

    @pytest.mark.asyncio
    async def test_interrupted_download_leaves_no_file_at_target(
        self, tmp_path: Path
    ) -> None:
        output = tmp_path / "out.png"
        transport = _transport(media=httpx.Response(500))
        with pytest.raises(httpx.HTTPStatusError):
            await _run_image(transport, output)
        assert not output.exists()
