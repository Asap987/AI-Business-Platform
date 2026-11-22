"""Connection handling shared by the ElevenLabs speech-to-text and text-to-speech adapters."""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from app.services.voice.errors import ProviderError

logger = logging.getLogger(__name__)
PROVIDER = "elevenlabs"


class Socket(Protocol):
    async def send(self, message: str) -> None: ...
    async def recv(self) -> str | bytes: ...
    async def close(self) -> None: ...


Connector = Callable[[str, dict[str, str]], Awaitable[Socket]]


async def default_connect(url: str, headers: dict[str, str]) -> Socket:
    from websockets.asyncio.client import connect  # imported lazily: only needed live

    return await connect(url, additional_headers=headers, max_size=2**22)  # type: ignore[return-value]


def parse_json(raw: str | bytes) -> dict[str, Any] | None:
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


# A call can install a list here; every retried connection adds one, so retries show up in its usage record.
retry_counter: ContextVar[list[int] | None] = ContextVar("elevenlabs_retry_counter", default=None)


async def connect_with_retries(
    connector: Connector,
    url: str,
    api_key: str,
    *,
    timeout_seconds: float,
    max_retries: int,
    backoff_seconds: float,
) -> Socket:
    """
    Open a WebSocket, retrying recoverable failures a bounded number of times.
    A rejected key (HTTP 401/403 at the handshake) is never retried. Error
    messages carry only the exception type: no URL, key or server text.
    """
    attempts = max_retries + 1
    last: ProviderError | None = None
    for attempt in range(attempts):
        try:
            return await asyncio.wait_for(connector(url, {"xi-api-key": api_key}), timeout_seconds)
        except asyncio.TimeoutError:
            last = ProviderError(PROVIDER, "connect_timeout", "Timed out connecting.", recoverable=True)
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (401, 403):
                raise ProviderError(PROVIDER, "auth", "ElevenLabs rejected the API key.", recoverable=False) from exc
            last = ProviderError(
                PROVIDER, "connect_failed", f"Could not connect ({type(exc).__name__}).", recoverable=True
            )
        if attempt < attempts - 1:
            counter = retry_counter.get()
            if counter is not None:
                counter[0] += 1
            await asyncio.sleep(backoff_seconds * (2**attempt))
    assert last is not None
    raise last
