"""Provider-independent email types. A new provider only has to implement ``EmailProvider.send``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class EmailError(Exception):
    """Sending failed. The message never contains the API key or the message body."""


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str
    idempotency_key: str | None = None


class EmailProvider(Protocol):
    name: str

    async def send(self, sender: str, message: EmailMessage) -> None: ...
