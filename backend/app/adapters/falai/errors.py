"""Errors specific to the image/video generation provider (Phase 14).

Quota/rate-limit errors share `ProviderQuotaExceededError` in
`app/adapters/provider_errors.py` (Phase 8) so key rotation works as before.
"""


class PromptBlockedError(RuntimeError):
    """The provider refuses the prompt for violating content policy.

    Unlike quota: another key is blocked the same way, and only fixing the prompt gets past it —
    so the service does not rotate keys but raises this error up so the UI can suggest editing the prompt.
    """

    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(f"{provider} chặn prompt vì vi phạm chính sách: {reason}")
        self.provider = provider
        self.reason = reason
