import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

from app.services.voice.evaluation import Item, ItemResult, normalize, run_item, summarize, term_recall, word_error_rate, word_errors
from app.services.voice.interfaces.speech_to_text import SpeechToText, STTStream
from app.services.voice.schemas.transcription import TranscriptEvent

BACKEND = Path(__file__).resolve().parents[2]


def test_normalize_ignores_case_punctuation_and_curly_quotes():
    assert normalize("Hello, World! It’s 5 o'clock.") == ["hello", "world", "it's", "5", "o'clock"]


def test_wer_counts_substitutions_deletions_insertions():
    assert word_errors("the cat sat", "the cat sat") == (0, 0, 0, 3)
    assert word_errors("the cat sat", "the dog sat") == (1, 0, 0, 3)
    assert word_errors("the cat sat", "the sat") == (0, 1, 0, 3)
    assert word_errors("the cat sat", "the big cat sat") == (0, 0, 1, 3)
    assert word_error_rate("a b c d", "a x c") == pytest.approx(0.5)  # one substitution, one deletion
    assert word_error_rate("a b", "a x b") == pytest.approx(0.5)  # an insertion counts
    assert word_error_rate("", "") == 0.0 and word_error_rate("", "oops") == 1.0
    assert word_error_rate("Volta Region", "volta region.") == 0.0


def test_term_recall_needs_whole_words_and_phrases():
    assert term_recall(["Volta", "cold room"], "we have a cold room in Volta") == 1.0
    assert term_recall(["Bono"], "Bonomi is far") == 0.0  # not a whole word
    assert term_recall(["Bono", "Kaneshie"], "Kaneshie only") == 0.5
    assert term_recall(["20/twenty", "22 november/november 22"], "twenty tonnes by 22 November") == 1.0
    assert term_recall(["20/twenty"], "twelve tonnes") == 0.0
    assert term_recall([], "anything") is None


class FakeStream(STTStream):
    def __init__(self, text, final_after_chunks):
        self.text, self.after, self.n, self.q, self.closed = text, final_after_chunks, 0, asyncio.Queue(), False

    async def send_audio(self, chunk):
        self.n += 1
        if self.n == self.after:
            self.q.put_nowait(TranscriptEvent(text=self.text, is_final=True, language_code="eng"))
            self.q.put_nowait(None)

    async def events(self):
        while (ev := await self.q.get()) is not None:
            yield ev

    async def close(self):
        self.closed = True


class FakeSTT(SpeechToText):
    def __init__(self, text, after=6, fail=False):
        self.text, self.after, self.fail, self.streams = text, after, fail, []

    async def open_stream(self, config):
        if self.fail:
            raise RuntimeError("no")
        s = FakeStream(self.text, self.after)
        self.streams.append(s)
        return s

    async def health_check(self):
        return True


async def fast_sleep(_):
    await asyncio.sleep(0)


async def test_run_item_scores_transcript_and_closes_stream():
    stt = FakeSTT("I want twenty tonnes to Bono")
    item = Item("a.wav", b"\x01\x00" * 3200, "I want twenty tonnes of tomatoes to Bono", terms=["Bono", "tonnes"])  # 0.2 s at 16 kHz
    r = await run_item(stt, item, speed=1000, sleep=fast_sleep, final_wait_seconds=1)
    assert r.error is None and r.transcript == "I want twenty tonnes to Bono"
    assert r.wer == pytest.approx(2 / 8) and r.term_recall == 1.0 and r.languages == ["eng"]
    assert r.seconds_to_final is not None and stt.streams[0].closed


async def test_run_item_reports_provider_failure_instead_of_raising():
    r = await run_item(FakeSTT("x", fail=True), Item("a.wav", b"\x00\x00" * 1600, "hello"), sleep=fast_sleep)
    assert r.error == "RuntimeError" and r.wer == 1.0


def test_summarize_by_category_ignores_failed_items():
    rs = [ItemResult("1", "a", "x", "x", 0.0, 1.0, 0.4, ["eng"]), ItemResult("2", "a", "x", "y", 1.0, 0.0, 0.8, ["eng"]),
          ItemResult("3", "b", "x", "", 1.0, None, None, [], error="Timeout")]
    s = summarize(rs)
    assert s["by_category"]["a"]["mean_wer"] == 0.5 and s["by_category"]["a"]["mean_term_recall"] == 0.5
    assert s["by_category"]["b"] == {"items": 1, "failed": 1, "mean_wer": None, "mean_term_recall": None, "latency_p50_s": None, "latency_p95_s": None}
    assert s["overall"]["failed"] == 1


@pytest.mark.parametrize("script", ["live_check.py", "stt_eval.py"])
def test_live_scripts_refuse_without_explicit_opt_in(script):
    args = [sys.executable, str(BACKEND / "scripts" / script)] + (["--manifest", "m.csv", "--audio-dir", ".", "--out", "o.json"] if script == "stt_eval.py" else [])
    env = {"PATH": "/usr/bin:/bin", "OPENAI_API_KEY": "sk-test-not-real", "ELEVENLABS_API_KEY": "el-test-not-real"}
    out = subprocess.run(args, capture_output=True, text=True, env=env, cwd=BACKEND)
    assert out.returncode == 2 and "Refusing to run" in out.stdout
    assert "sk-test-not-real" not in out.stdout + out.stderr


def test_live_check_names_missing_settings_without_values():
    env = {"PATH": "/usr/bin:/bin", "RUN_LIVE_PROVIDER_TESTS": "true", "OPENAI_API_KEY": "sk-test-not-real"}
    out = subprocess.run([sys.executable, str(BACKEND / "scripts" / "live_check.py"), "--yes-this-costs-money"],
                         capture_output=True, text=True, env=env, cwd=BACKEND)
    assert out.returncode == 2 and "ELEVENLABS_API_KEY" in out.stdout and "ELEVENLABS_VOICE_ID" in out.stdout
    assert "OPENAI_API_KEY" not in out.stdout and "sk-test-not-real" not in out.stdout + out.stderr
