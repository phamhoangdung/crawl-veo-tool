"""Test the real fal.ai adapter with fake HTTP.

The meaningful scope of this test suite: the **mechanism** (auth header, queue flow,
error classification, safe file download). It does NOT prove that the model paths or
input field names are correct — only a real key can check those, and they are
clearly marked in the docstring of `client.py`.
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
        """An unknown model must say clearly what is available — this table will certainly need fixing when
        fal.ai renames models."""
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
        """fal.ai uses `Authorization: Key ...`; sending `Bearer` would get a 401."""
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
        # Do not let the test wait 2s per poll like in a real run. Use monkeypatch
        # rather than assigning directly: direct assignment would leave the value 0 for every later test.
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
        """Changing the key is blocked just the same — must be distinguished from a quota error, otherwise the
        service would burn through every key in the pool for a prompt that can never pass."""
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
        """If the protocol changes we must know immediately, not keep running with an empty dict."""
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
        """The error message must point at where to look, because that is exactly the easiest place to go wrong."""
        with pytest.raises(falai.GenerationError, match="output"):
            falai._extract_media_url({"output": "?", "seed": 1}, kind="image")


class TestDownloadSafety:
    @pytest.mark.asyncio
    async def test_empty_file_is_rejected_and_not_left_behind(self, tmp_path: Path) -> None:
        """An empty file sitting exactly where the cache expects would be treated as "already generated" —
        pressing again later would return that broken file instead of generating again."""
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
