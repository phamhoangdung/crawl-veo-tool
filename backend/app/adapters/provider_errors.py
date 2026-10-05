"""Standardized errors shared between adapters/services related to the AI Account Pool
(Phase 8) — see docs/phases/phase-8-ai-account-pool.md."""

import httpx


class ProviderQuotaExceededError(RuntimeError):
    """1 specific key rejected by the provider for rate limit/out of quota (HTTP 429).

    Different from ordinary network/server errors (500...) — this error signals "this key needs
    a rest", not "this request is wrong", so the service layer catches it separately to switch
    to another key in the pool instead of raising straight up to the user.
    """

    def __init__(self, provider: str, original: httpx.HTTPStatusError) -> None:
        super().__init__(f"{provider}: hết quota/rate-limit (HTTP 429)")
        self.provider = provider
        self.original = original


class AllProvidersExhaustedError(RuntimeError):
    """Every key in the pool PLUS the fallback (free) provider failed — the job should
    pause (VideoStatus.PAUSED_QUOTA) instead of failing outright, to retry when a new key arrives
    or the cooldown expires."""
