"""Telnyx call events. Public URL, so every request must carry a valid Ed25519 signature or it is rejected.

Switched off (404) unless live telephony is fully configured. Only events for transfer attempts this system started are
acted on; everything else is acknowledged and ignored. Nothing from the body is stored or logged."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.v1.deps import get_settings_dep
from app.core.config import Settings
from app.services.telephony.factory import missing_for_live_telephony
from app.services.telephony.telnyx import get_registry, verify_signature

router = APIRouter(tags=["telephony"])
MAX_BODY = 64 * 1024


@router.post("/telephony/telnyx/webhook")
async def telnyx_webhook(request: Request, settings: Settings = Depends(get_settings_dep)):
    if missing_for_live_telephony(settings):
        raise HTTPException(404, "Not found")
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(413, "Too large")
    if not verify_signature(settings.telnyx_public_key or "", request.headers.get("telnyx-timestamp"), request.headers.get("telnyx-signature-ed25519"), raw):
        raise HTTPException(400, "Invalid signature")
    try:
        envelope = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Invalid body")
    get_registry().handle_event(envelope)
    return {"received": True}
