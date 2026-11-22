"""One small, controlled live check of OpenAI + ElevenLabs. COSTS MONEY (a few cents at most) and is opt-in.

    cd backend
    RUN_LIVE_PROVIDER_TESTS=true python scripts/live_check.py --yes-this-costs-money

Needs these server-side settings (environment or backend/.env, which git ignores; never commit them):
    OPENAI_API_KEY, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID

It sends no customer data: one fixed sentence to OpenAI, one short fixed sentence to ElevenLabs speech, and that
generated audio back to ElevenLabs speech recognition. It prints timings and usage counts (never keys, never audio).
Costs are not computed unless you filled VOICE_PRICING from the providers' current price lists.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import Settings  # noqa: E402
from app.services.voice.evaluation import Item, run_item  # noqa: E402
from app.services.voice.interfaces.reasoning import ReasoningRequest, TextDelta, TurnCompleted  # noqa: E402
from app.services.voice.language_manager import LanguageManager  # noqa: E402
from app.services.voice.providers.elevenlabs_stt import ElevenLabsSTT  # noqa: E402
from app.services.voice.providers.elevenlabs_tts import ElevenLabsTTS  # noqa: E402
from app.services.voice.providers.openai_reasoning import OpenAIReasoning  # noqa: E402
from app.services.voice.schemas.speech_response import TTSRequest  # noqa: E402

SENTENCE = "Good morning. Our office opens at eight."


def missing(settings: Settings) -> list[str]:
    out = []
    if settings.openai_api_key is None:
        out.append("OPENAI_API_KEY")
    if settings.elevenlabs_api_key is None:
        out.append("ELEVENLABS_API_KEY")
    if not settings.elevenlabs_default_voice_id:
        out.append("ELEVENLABS_VOICE_ID")
    return out


def line(name: str, ok: bool, detail: str) -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    return ok


async def check_openai(settings: Settings, languages: LanguageManager) -> bool:
    engine = OpenAIReasoning(settings, languages)
    req = ReasoningRequest(business_id=uuid4(), session_id=uuid4(), language_code="eng",
                           business_context="Business: Demo Co (a test). Reply in one short sentence.", history=[],
                           user_text="Say hello to the customer.")
    t0, first, text, usage = time.monotonic(), None, "", None
    try:
        async for ev in engine.respond_stream(req):
            if isinstance(ev, TextDelta):
                first = first or time.monotonic() - t0
                text += ev.text
            elif isinstance(ev, TurnCompleted):
                usage = ev.usage
    except Exception as exc:
        return line("OpenAI reply", False, type(exc).__name__ + (f" ({getattr(exc, 'code', '')})" if getattr(exc, "code", None) else ""))
    return line("OpenAI reply", bool(text.strip()) and usage is not None,
                f"first text {first:.2f}s, total {time.monotonic() - t0:.2f}s, model {usage.model if usage else '?'}, "
                f"tokens in/out {usage.input_tokens if usage else '?'}/{usage.output_tokens if usage else '?'}")


async def check_tts_and_stt(settings: Settings, languages: LanguageManager) -> bool:
    tts = ElevenLabsTTS(settings)
    request = TTSRequest(voice_id=settings.elevenlabs_default_voice_id or "", language_code="eng", model_id=languages.tts_model_id("eng"))

    async def text():
        yield SENTENCE

    t0, first, audio, fmt = time.monotonic(), None, bytearray(), None
    try:
        async for chunk in tts.synthesize_stream(request, text()):
            first = first or time.monotonic() - t0
            audio += chunk.audio
            fmt = chunk.audio_format
    except Exception as exc:
        return line("ElevenLabs speech", False, type(exc).__name__)
    ok1 = line("ElevenLabs speech", len(audio) > 1000, f"first audio {first or 0:.2f}s, {len(audio)} bytes, format {fmt}, {len(SENTENCE)} characters billed")
    if not ok1 or fmt != "pcm_16000":
        line("ElevenLabs recognition", False, f"skipped (needs pcm_16000 audio, got {fmt})")
        return False
    result = await run_item(ElevenLabsSTT(settings), Item("round-trip", bytes(audio), SENTENCE), speed=1.0)
    return line("ElevenLabs recognition", result.error is None and result.wer < 0.5,
                f"WER {result.wer:.2f} on its own synthetic voice (not a Ghanaian-accent test), "
                f"final {result.seconds_to_final if result.seconds_to_final is not None else 'none'}s after audio end, error {result.error}")


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes-this-costs-money", action="store_true")
    args = ap.parse_args()
    settings = Settings()
    if not (settings.run_live_provider_tests and args.yes_this_costs_money):
        print("Refusing to run: set RUN_LIVE_PROVIDER_TESTS=true and pass --yes-this-costs-money.")
        return 2
    gaps = missing(settings)
    if gaps:
        print("Missing settings (names only): " + ", ".join(gaps))
        return 2
    languages = LanguageManager(settings)
    results = [await check_openai(settings, languages), await check_tts_and_stt(settings, languages)]
    print("All live checks passed." if all(results) else "Some live checks failed; see above. Nothing else was changed.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
