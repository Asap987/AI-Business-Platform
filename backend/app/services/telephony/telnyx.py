"""
Telnyx Call Control adapter for TRANSFERS only. Written from Telnyx's public documentation (transfer command, webhook
envelope, Ed25519 webhook signatures). It has NOT been run against a real Telnyx account: nothing here has placed a call.

How confirmation works (this is the part that must never be faked):
  * POST /v2/calls/{call_control_id}/actions/transfer answering 200 {"result": "ok"} only means Telnyx ACCEPTED the command.
  * A transfer counts as CONFIRMED only when a signed ``call.bridged`` webhook arrives carrying this attempt's marker.
  * A ``call.hangup`` carrying the marker before that means NO_ANSWER / BUSY / FAILED.
  * No final event in time means UNCONFIRMED, which the routing code never treats as success.

Not built here (separately approved work): answering inbound calls, streaming call audio to speech services, buying numbers.
The API key is read from settings by the factory and is only ever sent in the Authorization header; it is never logged.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import re
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from typing import Any, Awaitable, Callable
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.services.telephony.interfaces import TelephonyProvider, TransferOutcome, TransferResult, TransferTarget

logger = logging.getLogger("kasora.telephony.telnyx")

API_BASE = "https://api.telnyx.com/v2"
SIGNATURE_TOLERANCE_SECONDS = 300  # Telnyx SDK default
_E164 = re.compile(r"^\+[1-9][0-9]{6,14}$")
_EXT = re.compile(r"^[0-9*#]{1,20}$")
_MARKER_PREFIX = "kasora-attempt:"

# (status code, parsed JSON or {}) ; raises on network failure. Injected so tests never touch the network.
HttpPost = Callable[[str, dict[str, str], dict[str, Any], float], Awaitable[tuple[int, dict[str, Any]]]]


async def urllib_post(url: str, headers: dict[str, str], body: dict[str, Any], timeout: float) -> tuple[int, dict[str, Any]]:
    def run() -> tuple[int, dict[str, Any]]:
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={**headers, "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https URL
                return resp.status, json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read() or b"{}")
            except ValueError:
                return exc.code, {}

    return await asyncio.to_thread(run)


def verify_signature(public_key_b64: str, timestamp: str | None, signature_b64: str | None, raw_body: bytes,
                     *, now: float | None = None, tolerance: int = SIGNATURE_TOLERANCE_SECONDS) -> bool:
    """Telnyx signs ``{timestamp}|{raw body}`` with Ed25519. Any malformed input is simply 'not valid'."""
    try:
        if not (public_key_b64 and timestamp and signature_b64):
            return False
        if abs((now if now is not None else time.time()) - int(timestamp)) > tolerance:
            return False
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64, validate=True))
        key.verify(base64.b64decode(signature_b64, validate=True), timestamp.encode() + b"|" + raw_body)
        return True
    except (InvalidSignature, ValueError, binascii.Error, TypeError):
        return False


def _marker(attempt_id: str) -> str:
    return base64.b64encode((_MARKER_PREFIX + attempt_id).encode()).decode()


def _attempt_from_state(client_state: Any) -> str | None:
    if not isinstance(client_state, str):
        return None
    try:
        text = base64.b64decode(client_state, validate=True).decode()
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return None
    return text[len(_MARKER_PREFIX):] if text.startswith(_MARKER_PREFIX) and len(text) > len(_MARKER_PREFIX) else None


class TelnyxEventRegistry:
    """Matches signed webhook events to the transfer attempt waiting for them. In-process: one worker only (see docs)."""

    def __init__(self, remember: int = 2000) -> None:
        self._waiters: dict[str, asyncio.Future[TransferOutcome]] = {}
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._remember = remember

    def expect(self, attempt_id: str) -> asyncio.Future[TransferOutcome]:
        fut: asyncio.Future[TransferOutcome] = asyncio.get_running_loop().create_future()
        self._waiters[attempt_id] = fut
        return fut

    def forget(self, attempt_id: str) -> None:
        self._waiters.pop(attempt_id, None)

    def handle_event(self, envelope: Any) -> bool:
        """True when the event settled a waiting attempt. Unknown, duplicate or late events are ignored."""
        try:
            data = envelope["data"]
            event_id, event_type, payload = data.get("id"), data.get("event_type"), data["payload"]
        except (KeyError, TypeError, AttributeError):
            return False
        if isinstance(event_id, str):
            if event_id in self._seen:
                return False
            self._seen[event_id] = None
            while len(self._seen) > self._remember:
                self._seen.popitem(last=False)
        attempt = _attempt_from_state(payload.get("client_state")) if isinstance(payload, dict) else None
        fut = self._waiters.get(attempt) if attempt else None
        if fut is None or fut.done():
            return False
        if event_type == "call.bridged":
            fut.set_result(TransferOutcome.CONFIRMED)
        elif event_type == "call.hangup":
            cause = str(payload.get("hangup_cause") or "").lower()
            # Cause names are from memory of Telnyx's list and still need checking against real events.
            fut.set_result(TransferOutcome.NO_ANSWER if cause in ("timeout", "no_answer") else TransferOutcome.BUSY if cause == "user_busy" else TransferOutcome.FAILED)
        else:
            return False
        return True


_registry = TelnyxEventRegistry()


def get_registry() -> TelnyxEventRegistry:
    return _registry


class TelnyxTelephony(TelephonyProvider):
    name = "telnyx"
    simulated = False

    def __init__(self, api_key: str, registry: TelnyxEventRegistry | None = None, http: HttpPost = urllib_post, *,
                 from_number: str | None = None, timeout_secs: int = 25, wait_margin_secs: float = 5.0, base_url: str = API_BASE) -> None:
        if not api_key:
            raise ValueError("A Telnyx API key is required")
        self._key, self._registry, self._http = api_key, registry or _registry, http
        self._from, self._timeout, self._margin, self._base = from_number, timeout_secs, wait_margin_secs, base_url

    async def transfer_call(self, call_ref: str, target: TransferTarget) -> TransferResult:
        attempt = uuid4().hex
        if not call_ref or not _E164.match(target.phone or "") or (target.extension and not _EXT.match(target.extension)):
            logger.warning("telnyx transfer %s refused before sending: invalid call reference, number or extension", attempt)
            return TransferResult(TransferOutcome.FAILED, attempt)
        marker = _marker(attempt)
        body: dict[str, Any] = {"to": target.phone, "timeout_secs": self._timeout, "command_id": attempt,
                                "client_state": marker, "target_leg_client_state": marker}
        if self._from:
            body["from"] = self._from
        if target.extension:
            body["send_digits_on_answer"] = "ww" + target.extension
        waiter = self._registry.expect(attempt)  # registered BEFORE sending so a fast webhook cannot be missed
        try:
            try:
                status, _ = await self._http(f"{self._base}/calls/{call_ref}/actions/transfer", {"Authorization": f"Bearer {self._key}"}, body, 15.0)
            except Exception:  # network trouble: the command may or may not have reached Telnyx
                logger.warning("telnyx transfer %s: request did not complete; outcome unknown", attempt)
                return TransferResult(TransferOutcome.UNCONFIRMED, attempt)
            if status != 200:
                logger.warning("telnyx transfer %s: command not accepted (HTTP %s)", attempt, status)
                return TransferResult(TransferOutcome.FAILED if 400 <= status < 500 else TransferOutcome.UNCONFIRMED, attempt)
            try:
                outcome = await asyncio.wait_for(waiter, self._timeout + self._margin)
            except asyncio.TimeoutError:
                outcome = TransferOutcome.UNCONFIRMED
            logger.info("telnyx transfer %s finished: %s", attempt, outcome.value)
            return TransferResult(outcome, attempt)
        finally:
            self._registry.forget(attempt)

    async def hang_up(self, call_ref: str) -> None:
        try:
            await self._http(f"{self._base}/calls/{call_ref}/actions/hangup", {"Authorization": f"Bearer {self._key}"}, {"command_id": uuid4().hex}, 15.0)
        except Exception:
            logger.warning("telnyx hang up request did not complete")

    async def health_check(self) -> bool:
        """No request is made: a live check would touch the account. Configuration presence is all that is verified."""
        return bool(self._key)
