from __future__ import annotations


class ProviderError(Exception):
    """
    A failure in a speech or reasoning provider, in a provider-neutral shape so
    the conversation manager can decide what to do without knowing which
    provider failed.

    `recoverable` means a retry or reconnect might succeed (throttling, a
    dropped connection). Non-recoverable errors (bad key, exhausted quota,
    invalid request) need an operator, so callers should fall back or hand the
    call to a person instead of retrying.

    Messages must never contain API keys or customer speech.
    """

    def __init__(self, provider: str, code: str, message: str, *, recoverable: bool) -> None:
        super().__init__(f"{provider}:{code}: {message}")
        self.provider = provider
        self.code = code
        self.message = message
        self.recoverable = recoverable
