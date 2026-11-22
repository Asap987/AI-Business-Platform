"""Resend (https://resend.com) adapter, using only the standard library so no new dependency is added.

Endpoint and fields follow Resend's "Send Email" API: POST https://api.resend.com/emails with a Bearer key and
a JSON body of from/to/subject/html/text. Not yet exercised against the live service (needs a key and a verified
domain); the request shape is covered by offline tests with an injected transport.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from collections.abc import Callable

from app.services.email.base import EmailError, EmailMessage

API_URL = "https://api.resend.com/emails"

# (url, headers, body) -> (status, response text)
Transport = Callable[[str, dict[str, str], bytes], tuple[int, str]]


def _urllib_transport(timeout: float) -> Transport:
    def post(url: str, headers: dict[str, str], body: bytes) -> tuple[int, str]:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https URL
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace")

    return post


class ResendProvider:
    name = "resend"

    def __init__(self, api_key: str, *, timeout: float = 10.0, transport: Transport | None = None):
        self._key = api_key
        self._post = transport or _urllib_transport(timeout)

    async def send(self, sender: str, message: EmailMessage) -> None:
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json", "User-Agent": "kasora-ai/1.0"}
        if message.idempotency_key:
            headers["Idempotency-Key"] = message.idempotency_key
        body = json.dumps({"from": sender, "to": [message.to], "subject": message.subject,
                           "html": message.html, "text": message.text}).encode()
        try:
            status, _ = await asyncio.to_thread(self._post, API_URL, headers, body)
        except Exception as exc:  # network, DNS, timeout
            raise EmailError(f"Resend request failed ({type(exc).__name__})") from None
        if status >= 300:
            raise EmailError(f"Resend rejected the email (HTTP {status})")
