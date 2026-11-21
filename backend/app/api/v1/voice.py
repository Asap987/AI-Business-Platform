"""Live voice test call over a WebSocket (browser audio in, assistant audio out).

Protocol (one WebSocket, ``/api/v1/voice/test-call``, cookie session):
  server -> client JSON: {"type":"ready","input_format":"pcm_s16le_16000_mono","output_format":...}
                         {"type":"state","state":...} {"type":"transcript","speaker":"customer"|"assistant","text":...}
                         {"type":"interrupted"} {"type":"handover"} {"type":"error","code":...}
  server -> client binary: assistant audio chunks (output_format)
  client -> server binary: customer audio, PCM signed 16-bit little-endian, 16 kHz, mono (max 32 KB per frame)
  client -> server JSON:   {"type":"end"}

Safety: same-origin check (cookies ride on WebSocket handshakes, so Origin must be verified here), session
cookie bound to one business, ``voice:use`` permission, per-business call limits, and nothing is stored: the
transcript exists only in memory for the length of the call. Calls are not saved as conversations because a
saved conversation needs an identified customer; a test call has none.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import Principal, get_db, has_permission, principal_from_token, require
from app.api.v1.privacy import load_privacy
from app.database.models import Agent, Department
from app.services.voice.call_runner import MAX_FRAME_BYTES, CallRunner
from app.services.voice.errors import ProviderError
from app.services.voice.schemas.transcription import STTStreamConfig
from app.services.voice.session_store import SessionLimitError
from app.services.voice.stack import missing_for_live_voice

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])
WS_POLICY, WS_TRY_LATER = 1008, 1013


@router.get("/status")
async def status(request: Request, p: Principal = Depends(require("voice:use"))):
    """Says whether live voice can run and what is missing, by NAME only. Never returns key values."""
    settings = request.app.state.settings
    missing = missing_for_live_voice(settings)
    if not settings.elevenlabs_default_voice_id:
        missing.append("ELEVENLABS_DEFAULT_VOICE_ID")
    return {"available": request.app.state.voice_stack is not None and not missing, "missing": missing,
            "disabled_providers": sorted(settings.voice_disabled_providers)}


async def _business_context(db: AsyncSession, business_id: UUID, name: str) -> str:
    """The minimum the assistant needs up front. Hours, policies and procedures come from the knowledge tool."""
    depts = (await db.execute(select(Department.name).where(Department.business_id == business_id).order_by(Department.name))).scalars().all()
    lines = [f"Business name: {name}."]
    if depts:
        lines.append("Departments: " + ", ".join(depts) + ".")
    return "\n".join(lines)


async def _refuse(ws: WebSocket, code: str, close_code: int) -> None:
    await ws.send_json({"type": "error", "code": code})
    await ws.close(code=close_code)


@router.websocket("/test-call")
async def test_call(ws: WebSocket, agent_id: UUID | None = None):
    app = ws.app
    settings, factory = app.state.settings, app.state.session_factory
    # 1. Origin: browsers attach cookies to cross-site WebSocket handshakes, so check it ourselves.
    if ws.headers.get("origin") not in set(settings.cors_origins):
        await ws.close(code=WS_POLICY)
        return
    # 2. Who is calling, and for which business. Close the DB session before the long call starts.
    async with factory() as db:
        try:
            principal = await principal_from_token(db, ws.cookies.get(settings.session_cookie_name), settings)
        except HTTPException:
            await ws.close(code=WS_POLICY)
            return
        if not has_permission(principal.role, "voice:use"):
            await ws.close(code=WS_POLICY)
            return
        business_id, business_name = principal.business_id, principal.business.name
        voice_id = settings.elevenlabs_default_voice_id
        agent = None
        if agent_id is not None:
            agent = (await db.execute(select(Agent).where(Agent.id == agent_id, Agent.business_id == business_id))).scalar_one_or_none()
            if agent is None:
                await ws.close(code=WS_POLICY)  # another business's agent looks the same as a missing one
                return
            cfg = agent.config if isinstance(agent.config, dict) else {}
            voice_id = cfg.get("voice_id") or voice_id
        privacy = await load_privacy(db, business_id)
        context = await _business_context(db, business_id, business_name)

    await ws.accept()
    stack = app.state.voice_stack
    if stack is None:
        await _refuse(ws, "voice_not_enabled", WS_TRY_LATER)
        return
    if privacy is not None and not privacy.ai_providers_enabled:  # the business switched AI providers off
        await _refuse(ws, "ai_disabled_by_business", WS_POLICY)
        return
    if not voice_id:
        await _refuse(ws, "no_voice_configured", WS_TRY_LATER)
        return
    try:
        session = stack.store.create(business_id, agent_id=agent.id if agent else None, voice_id=voice_id, language_code=settings.voice_default_language,
                                   redact_contact_details=privacy.redact_contact_details if privacy else None)
    except SessionLimitError:
        await _refuse(ws, "too_many_calls", WS_TRY_LATER)
        return
    try:
        stream = await stack.stt.open_stream(STTStreamConfig(language_hint=session.language_code))
    except ProviderError as err:
        stack.store.end(session)
        stack.store.discard(session)
        await _refuse(ws, f"speech_unavailable_{err.code}", WS_TRY_LATER)
        return

    async def send_json(msg):
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await ws.send_text(json.dumps(msg))

    async def send_audio(chunk: bytes):
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await ws.send_bytes(chunk)

    runner = CallRunner(session=session, stt=stream, manager=stack.manager, store=stack.store,
                        send_json=send_json, send_audio=send_audio, business_context=context)
    await send_json({"type": "ready", "input_format": "pcm_s16le_16000_mono", "output_format": settings.elevenlabs_tts_output_format,
                     "max_frame_bytes": MAX_FRAME_BYTES})

    async def receive() -> None:
        try:
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    return
                if message.get("bytes") is not None:
                    await runner.feed_audio(message["bytes"])
                elif message.get("text") is not None:
                    try:
                        if json.loads(message["text"]).get("type") == "end":
                            return
                    except (ValueError, AttributeError):
                        continue  # ignore malformed control messages
        except WebSocketDisconnect:
            return

    run_task, recv_task = asyncio.create_task(runner.run()), asyncio.create_task(receive())
    try:
        await asyncio.wait({run_task, recv_task}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        recv_task.cancel()
        await runner.stop()  # idempotent: ends the session and closes the speech stream
        await asyncio.gather(run_task, recv_task, return_exceptions=True)
        usage = stack.manager.usage_for(session)
        # Counts only: no transcript text, no audio.
        logger.info("voice call ended business=%s session=%s tts_chars=%s provider_errors=%s escalated=%s",
                    business_id, session.session_id, usage.tts_characters, usage.provider_errors, session.escalation.requested)
        stack.store.discard(session)
        stack.manager.usage.pop(session.session_id, None)
        with contextlib.suppress(Exception):
            await ws.close()
