"""Lỗi riêng của provider sinh ảnh/video (Phase 14).

Lỗi quota/rate-limit dùng chung `ProviderQuotaExceededError` ở
`app/adapters/provider_errors.py` (Phase 8) để rotation key hoạt động như cũ.
"""


class PromptBlockedError(RuntimeError):
    """Provider từ chối prompt vì vi phạm chính sách nội dung.

    Khác quota: thử key khác cũng bị chặn y hệt, phải sửa prompt mới qua được —
    nên service không rotate key mà trả lỗi này lên để UI đề nghị sửa prompt.
    """

    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(f"{provider} chặn prompt vì vi phạm chính sách: {reason}")
        self.provider = provider
        self.reason = reason
