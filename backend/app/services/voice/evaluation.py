"""Measuring speech recognition on our own recordings (no provider code here, so it is testable offline).

Word error rate (WER) = (substitutions + deletions + insertions) / words in the reference. It is computed on
normalised text (lower case, punctuation removed, numbers left as spoken by the provider) so formatting
differences do not count as errors. Business-term recall is the share of expected terms (place names, product
words) found in the transcript. Nothing here stores audio or transcripts; callers decide what to write down.
"""

from __future__ import annotations

import asyncio
import re
import statistics
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.services.voice.interfaces.speech_to_text import SpeechToText
from app.services.voice.schemas.transcription import STTStreamConfig

_WORD = re.compile(r"[a-z0-9']+")


def normalize(text: str) -> list[str]:
    return _WORD.findall(text.lower().replace("’", "'"))


def word_errors(reference: str, hypothesis: str) -> tuple[int, int, int, int]:
    """(substitutions, deletions, insertions, reference word count) by edit-distance alignment."""
    ref, hyp = normalize(reference), normalize(hypothesis)
    # dp[i][j] = (total errors, subs, dels, ins) aligning ref[:i] with hyp[:j]
    prev = [(j, 0, 0, j) for j in range(len(hyp) + 1)]
    for i in range(1, len(ref) + 1):
        cur = [(i, 0, i, 0)]
        for j in range(1, len(hyp) + 1):
            if ref[i - 1] == hyp[j - 1]:
                cur.append(prev[j - 1])
                continue
            s, d, n = prev[j - 1], prev[j], cur[j - 1]
            options = [(s[0] + 1, s[1] + 1, s[2], s[3]), (d[0] + 1, d[1], d[2] + 1, d[3]), (n[0] + 1, n[1], n[2], n[3] + 1)]
            cur.append(min(options, key=lambda o: o[0]))
        prev = cur
    _, subs, dels, ins = prev[len(hyp)]
    return subs, dels, ins, len(ref)


def word_error_rate(reference: str, hypothesis: str) -> float:
    subs, dels, ins, n = word_errors(reference, hypothesis)
    if n == 0:
        return 0.0 if not normalize(hypothesis) else 1.0
    return (subs + dels + ins) / n


def term_recall(terms: list[str], hypothesis: str) -> float | None:
    """Share of expected terms present as whole words (or phrases) in the transcript; None when no terms.
    Numbers, dates and prices can be written either way: give alternatives as "20/twenty"."""
    if not terms:
        return None
    hyp = f" {' '.join(normalize(hypothesis))} "
    # A term may list accepted spellings separated by "/", e.g. "20/twenty" or "GH₵50/fifty cedis".
    found = sum(1 for t in terms if any(f" {' '.join(normalize(alt))} " in hyp for alt in t.split("/") if normalize(alt)))
    return found / len(terms)


@dataclass
class Item:
    id: str
    pcm: bytes  # PCM16 little-endian mono
    reference: str
    category: str = "general"
    terms: list[str] = field(default_factory=list)
    sample_rate_hz: int = 16000


@dataclass
class ItemResult:
    id: str
    category: str
    reference: str
    transcript: str
    wer: float
    term_recall: float | None
    seconds_to_final: float | None  # from the end of the audio (silence tail excluded) to the last final transcript
    languages: list[str]
    error: str | None = None


async def run_item(stt: SpeechToText, item: Item, *, speed: float = 1.0, chunk_ms: int = 100, tail_silence_ms: int = 1500,
                   final_wait_seconds: float = 8.0, language_hint: str | None = None,
                   clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> ItemResult:
    config = STTStreamConfig(sample_rate_hz=item.sample_rate_hz, language_hint=language_hint)
    bytes_per_chunk = max(2, int(item.sample_rate_hz * chunk_ms / 1000) * 2)
    finals: list[str] = []
    langs: list[str] = []
    last_final_at: list[float | None] = [None]
    audio_end_at: list[float | None] = [None]
    try:
        stream = await stt.open_stream(config)
    except Exception as exc:
        return ItemResult(item.id, item.category, item.reference, "", 1.0, None, None, [], error=type(exc).__name__)

    async def reader() -> None:
        async for ev in stream.events():
            if ev.is_final and ev.text.strip():
                finals.append(ev.text.strip())
                last_final_at[0] = clock()
                if ev.language_code:
                    langs.append(ev.language_code)

    task = asyncio.create_task(reader())
    error: str | None = None
    try:
        silence = b"\x00" * bytes_per_chunk
        stream_chunks = [item.pcm[i:i + bytes_per_chunk] for i in range(0, len(item.pcm), bytes_per_chunk)]
        for chunk in stream_chunks:
            await stream.send_audio(chunk)
            await sleep(chunk_ms / 1000 / speed)
        audio_end_at[0] = clock()
        for _ in range(max(1, tail_silence_ms // chunk_ms)):  # silence lets the provider's voice detection close the turn
            await stream.send_audio(silence)
            await sleep(chunk_ms / 1000 / speed)
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=final_wait_seconds)
        except asyncio.TimeoutError:
            pass
    except Exception as exc:
        error = type(exc).__name__
    finally:
        await stream.close()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    transcript = " ".join(finals)
    latency = None
    if last_final_at[0] is not None and audio_end_at[0] is not None:
        latency = max(0.0, last_final_at[0] - audio_end_at[0])
    return ItemResult(item.id, item.category, item.reference, transcript, word_error_rate(item.reference, transcript),
                      term_recall(item.terms, transcript), latency, sorted(set(langs)), error)


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def summarize(results: list[ItemResult]) -> dict:
    def block(rs: list[ItemResult]) -> dict:
        ok = [r for r in rs if r.error is None]
        recalls = [r.term_recall for r in ok if r.term_recall is not None]
        lat = [r.seconds_to_final for r in ok if r.seconds_to_final is not None]
        return {
            "items": len(rs), "failed": len(rs) - len(ok),
            "mean_wer": round(statistics.fmean(r.wer for r in ok), 4) if ok else None,
            "mean_term_recall": round(statistics.fmean(recalls), 4) if recalls else None,
            "latency_p50_s": round(_percentile(lat, 0.5), 3) if lat else None,
            "latency_p95_s": round(_percentile(lat, 0.95), 3) if lat else None,
        }
    cats = sorted({r.category for r in results})
    return {"overall": block(results), "by_category": {c: block([r for r in results if r.category == c]) for c in cats}}
