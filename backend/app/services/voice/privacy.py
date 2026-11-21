"""
Data-protection helpers for the voice path.

* ``redact_for_provider`` removes the most dangerous content from text before it
  is sent to an external AI provider: payment card numbers (Luhn-checked) and
  spoken passwords / PINs / one-time codes. Optionally masks emails and phone
  numbers. This is a safety net, not a guarantee: it cannot find every
  identifier in free speech, so it complements (never replaces) data
  minimisation, provider agreements and the retention settings.
* ``ProviderControls`` is the runtime shutdown switch for each external provider.
"""

from __future__ import annotations

import re

from app.services.voice.errors import ProviderError

_CARD = re.compile(r"(?<![\w-])(?:\d[ -]?){12,18}\d(?![\w-])")
_SECRET = re.compile(
    r"\b(password|passcode|pin|otp|one[- ]time (?:code|password)|cvv|cvc|security code)\b(\s*(?:is|was|:|=)?\s*)([^\s,.;]+(?:\s+\d+)*)",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?<![\w-])\+?\d[\d ()-]{7,}\d(?![\w-])")


def _luhn_ok(digits: str) -> bool:
    total, flip = 0, False
    for ch in reversed(digits):
        n = int(ch)
        if flip:
            n *= 2
            if n > 9:
                n -= 9
        total += n
        flip = not flip
    return total % 10 == 0


def _mask_card(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    return "[card number removed]" if 13 <= len(digits) <= 19 and _luhn_ok(digits) else match.group(0)


def redact_for_provider(text: str, *, secrets: bool = True, contact_details: bool = False) -> str:
    if secrets:
        text = _CARD.sub(_mask_card, text)
        text = _SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}[removed]", text)
    if contact_details:
        text = _EMAIL.sub("[email removed]", text)
        text = _PHONE.sub("[phone number removed]", text)
    return text


class ProviderControls:
    """Runtime on/off switch per provider ("openai", "elevenlabs"). Everything is on by default."""

    def __init__(self) -> None:
        self._disabled: set[str] = set()

    def disable(self, provider: str) -> None:
        self._disabled.add(provider)

    def enable(self, provider: str) -> None:
        self._disabled.discard(provider)

    def is_enabled(self, provider: str) -> bool:
        return provider not in self._disabled

    def require(self, provider: str) -> None:
        if provider in self._disabled:
            raise ProviderError(provider, "disabled", f"{provider} has been switched off by an administrator.", recoverable=False)
