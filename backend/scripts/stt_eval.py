"""Measure ElevenLabs speech recognition on YOUR recordings (Ghanaian English, business terms, phone quality).

Costs money (ElevenLabs bills the audio streamed) and sends the audio files to ElevenLabs. Use only recordings made
with the speaker's consent, with no real customer secrets. Nothing is stored by this script except the report you
ask for (--out), which contains the reference and recognised text, so keep it private.

    cd backend
    RUN_LIVE_PROVIDER_TESTS=true ELEVENLABS_API_KEY=... python scripts/stt_eval.py \
        --manifest my_set/manifest.csv --audio-dir my_set --out my_set/report.json --yes-this-costs-money

Manifest columns: file,reference,category,terms   (terms are separated by | ; category examples: ghanaian_english,
phone_8k_upsampled, noisy, business_terms). Audio: WAV, mono, 16-bit PCM, 16000 Hz (or 8000/24000/44100/48000).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import Settings  # noqa: E402
from app.services.voice.evaluation import Item, run_item, summarize  # noqa: E402
from app.services.voice.providers.elevenlabs_stt import ElevenLabsSTT  # noqa: E402


def read_wav(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise SystemExit(f"{path.name}: must be mono 16-bit PCM WAV")
        return w.readframes(w.getnframes()), w.getframerate()


def load_items(manifest: Path, audio_dir: Path) -> list[Item]:
    items = []
    with manifest.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            pcm, rate = read_wav(audio_dir / row["file"])
            items.append(Item(id=row["file"], pcm=pcm, reference=row["reference"], category=(row.get("category") or "general"),
                              terms=[t for t in (row.get("terms") or "").split("|") if t.strip()], sample_rate_hz=rate))
    return items


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--audio-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--speed", type=float, default=1.0, help="1.0 = real-time (needed for honest latency); higher is faster but latency is not meaningful")
    ap.add_argument("--language-hint", default=None)
    ap.add_argument("--yes-this-costs-money", action="store_true")
    args = ap.parse_args()

    settings = Settings()
    if not (settings.run_live_provider_tests and args.yes_this_costs_money):
        print("Refusing to run: set RUN_LIVE_PROVIDER_TESTS=true and pass --yes-this-costs-money (this bills ElevenLabs).")
        return 2
    if settings.elevenlabs_api_key is None:
        print("Missing setting: ELEVENLABS_API_KEY")
        return 2
    items = load_items(args.manifest, args.audio_dir)
    seconds = sum(len(i.pcm) / 2 / i.sample_rate_hz for i in items)
    print(f"{len(items)} recordings, {seconds:.0f} s of audio will be streamed to ElevenLabs.")
    stt = ElevenLabsSTT(settings)
    results = []
    for n, item in enumerate(items, 1):
        r = await run_item(stt, item, speed=args.speed, language_hint=args.language_hint)
        results.append(r)
        print(f"[{n}/{len(items)}] {item.id}: WER {r.wer:.2f}" + (f" ERROR {r.error}" if r.error else ""))
    report = {"settings": {"stt_model": settings.elevenlabs_stt_model, "speed": args.speed, "language_hint": args.language_hint},
              "summary": summarize(results), "items": [r.__dict__ for r in results]}
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report written to {args.out} (contains transcripts; keep private).")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
