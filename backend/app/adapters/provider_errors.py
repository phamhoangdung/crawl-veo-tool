"""Lỗi chuẩn hoá dùng chung giữa các adapter/service liên quan tới AI Account Pool
(Phase 8) — xem docs/phases/phase-8-ai-account-pool.md."""

import httpx


class ProviderQuotaExceededError(RuntimeError):
    """1 key cụ thể bị provider từ chối vì rate-limit/hết quota (HTTP 429).

    Khác với lỗi mạng/lỗi server thường (500...) — lỗi này báo hiệu "key này cần
    nghỉ", không phải "request này sai", nên service layer bắt riêng để chuyển
    sang key khác trong pool thay vì raise thẳng lên cho người dùng.
    """

    def __init__(self, provider: str, original: httpx.HTTPStatusError) -> None:
        super().__init__(f"{provider}: hết quota/rate-limit (HTTP 429)")
        self.provider = provider
        self.original = original


class AllProvidersExhaustedError(RuntimeError):
    """Toàn bộ key trong pool CỘNG provider fallback (free) đều thất bại — job nên
    tạm dừng (VideoStatus.PAUSED_QUOTA) thay vì fail hẳn, để thử lại khi có key mới
    hoặc cooldown hết hạn."""
