"""Chooses the telephony provider. The default is ALWAYS the simulator; a real provider needs two deliberate switches plus credentials."""

from __future__ import annotations

from app.core.config import Settings
from app.services.telephony.interfaces import TelephonyProvider
from app.services.telephony.mock import MockTelephony


def missing_for_live_telephony(settings: Settings) -> list[str]:
    """Names (never values) of what is still needed before real transfers can happen."""
    if settings.telephony_provider != "telnyx":
        return ["TELEPHONY_PROVIDER=telnyx"]
    missing = []
    if not settings.telephony_live_approved:
        missing.append("TELEPHONY_LIVE_APPROVED")
    if settings.telnyx_api_key is None:
        missing.append("TELNYX_API_KEY")
    if not settings.telnyx_public_key:
        missing.append("TELNYX_PUBLIC_KEY")
    return missing


def build_telephony(settings: Settings) -> TelephonyProvider:
    if missing_for_live_telephony(settings):
        return MockTelephony()
    from app.services.telephony.telnyx import TelnyxTelephony

    return TelnyxTelephony(settings.telnyx_api_key.get_secret_value(), from_number=settings.telnyx_from_number or None,
                           timeout_secs=settings.telnyx_transfer_timeout_seconds)
