import asyncio
import base64
import json
import logging

import pytest
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK, InvalidStatus
from websockets.frames import Close
from websockets.datastructures import Headers
from websockets.http11 import Response

from app.core.config import Settings
from app.services.voice.errors import ProviderError
from app.services.voice.providers.elevenlabs_stt import ElevenLabsSTT, audio_format_for
from app.services.voice.schemas.transcription import STTStreamConfig

KEY = "xi-test-key-should-never-leak"


def settings(**kw) -> Settings:
    kw.setdefault("elevenlabs_api_key", KEY)
    kw.setdefault("elevenlabs_stt_final_merge_wait_seconds", 0.05)
    return Settings(_env_file=None, **kw)


def closed_ok() -> ConnectionClosedOK:
    return ConnectionClosedOK(Close(1000, ""), Close(1000, ""), True)


def closed_error() -> ConnectionClosedError:
    return ConnectionClosedError(Close(1011, "boom"), None, None)


class FakeSocket:
    """Plays back scripted server messages; records what the client sent."""

    def __init__(self, incoming=()):
        self.sent: list[str] = []
        self.closed = False
        self._q: asyncio.Queue = asyncio.Queue()
        for item in incoming:
            self.push(item)

    def push(self, item):
        self._q.put_nowait(json.dumps(item) if isinstance(item, dict) else item)

    async def send(self, message):
        self.sent.append(message)

    async def recv(self):
        item = await self._q.get()
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self):
        self.closed = True


class FakeConnector:
    def __init__(self, sockets=None, failures=()):
        self.sockets = list(sockets or [])
        self.failures = list(failures)  # consumed per attempt; None = succeed
        self.calls: list[tuple[str, dict]] = []

    async def __call__(self, url, headers):
        self.calls.append((url, headers))
        if self.failures:
            failure = self.failures.pop(0)
            if failure is not None:
                raise failure
        return self.sockets.pop(0)


def stt(sock=None, **kw) -> tuple[ElevenLabsSTT, FakeConnector]:
    connector = FakeConnector([sock or FakeSocket()], kw.pop("failures", ()))
    return ElevenLabsSTT(settings(**kw), connector, retry_backoff_seconds=0.0), connector


async def collect(stream, n):
    out = []
    async for ev in stream.events():
        out.append(ev)
        if len(out) == n:
            break
    return out


# ---------------------------------------------------------------- connection
async def test_url_and_auth_header():
    adapter, connector = stt()
    stream = await adapter.open_stream(STTStreamConfig(sample_rate_hz=16000))
    url, headers = connector.calls[0]
    assert url.startswith("wss://api.elevenlabs.io/v1/speech-to-text/realtime?")
    assert "model_id=scribe_v3_live" in url
    assert "audio_format=pcm_16000" in url
    assert "commit_strategy=turn_prediction" in url
    assert "include_language_detection=true" in url
    assert headers == {"xi-api-key": KEY}
    assert KEY not in url  # the key travels in a header only
    await stream.close()


async def test_telephony_ulaw_format_and_unsupported_format():
    assert audio_format_for(STTStreamConfig(audio_encoding="ulaw", sample_rate_hz=8000)) == "ulaw_8000"
    with pytest.raises(ValueError):
        audio_format_for(STTStreamConfig(audio_encoding="opus", sample_rate_hz=16000))


async def test_fallback_model_uses_vad_commit_strategy():
    adapter, connector = stt(failures=[RuntimeError("down")] * 3)  # primary exhausts 3 attempts
    connector.sockets = [FakeSocket()]
    stream = await adapter.open_stream(STTStreamConfig())
    assert len(connector.calls) == 4
    last_url = connector.calls[-1][0]
    assert "model_id=scribe_v2_realtime" in last_url and "commit_strategy=vad" in last_url
    await stream.close()


async def test_missing_api_key_fails_without_connecting():
    connector = FakeConnector()
    adapter = ElevenLabsSTT(Settings(_env_file=None), connector)
    with pytest.raises(ProviderError) as err:
        await adapter.open_stream(STTStreamConfig())
    assert err.value.code == "not_configured" and not err.value.recoverable
    assert connector.calls == []


async def test_recoverable_connect_failure_is_retried_then_succeeds():
    adapter, connector = stt(failures=[OSError("x"), None])
    stream = await adapter.open_stream(STTStreamConfig())
    assert len(connector.calls) == 2
    await stream.close()


async def test_retries_are_bounded():
    adapter, connector = stt(failures=[OSError("x")] * 20, elevenlabs_max_retries=1)
    with pytest.raises(ProviderError) as err:
        await adapter.open_stream(STTStreamConfig())
    assert err.value.recoverable
    assert len(connector.calls) == 4  # 2 attempts x 2 models, then stop


async def test_bad_key_at_handshake_is_not_retried_or_fallen_back():
    response = Response(401, "Unauthorized", Headers(), b"")
    adapter, connector = stt(failures=[InvalidStatus(response)])
    with pytest.raises(ProviderError) as err:
        await adapter.open_stream(STTStreamConfig())
    assert err.value.code == "auth" and not err.value.recoverable
    assert len(connector.calls) == 1


# -------------------------------------------------------------------- sending
async def test_audio_is_sent_as_base64_input_audio_chunk():
    sock = FakeSocket()
    adapter, _ = stt(sock)
    stream = await adapter.open_stream(STTStreamConfig())
    await stream.send_audio(b"\x01\x02\x03")
    await stream.send_audio(b"")  # empty chunks are skipped
    assert [json.loads(m) for m in sock.sent] == [
        {"message_type": "input_audio_chunk", "audio_base_64": base64.b64encode(b"\x01\x02\x03").decode()}
    ]
    await stream.close()


async def test_send_after_close_raises():
    adapter, _ = stt()
    stream = await adapter.open_stream(STTStreamConfig())
    await stream.close()
    with pytest.raises(ProviderError):
        await stream.send_audio(b"x")


# ------------------------------------------------------------------ receiving
async def test_partials_then_final_with_language_from_timestamps_message():
    sock = FakeSocket(
        [
            {"message_type": "session_started", "session_id": "s", "config": {}},
            {"message_type": "partial_transcript", "text": "my app", "language_code": None},
            {"message_type": "partial_transcript", "text": "my app is not working", "language_code": "eng"},
            {"message_type": "committed_transcript", "text": "My app is not working."},
            {
                "message_type": "committed_transcript_with_timestamps",
                "text": "My app is not working.",
                "language_code": "eng",
                "words": [{"text": "My", "start": 0.4, "end": 0.6}, {"text": "working.", "start": 1.5, "end": 2.1}],
            },
        ]
    )
    adapter, _ = stt(sock)
    stream = await adapter.open_stream(STTStreamConfig())
    events = await collect(stream, 3)
    assert [(e.text, e.is_final) for e in events] == [
        ("my app", False),
        ("my app is not working", False),
        ("My app is not working.", True),
    ]
    final = events[2]
    assert final.language_code == "eng"
    assert (final.start_seconds, final.end_seconds) == (0.4, 2.1)
    assert final.language_probability is None  # the realtime API doesn't provide one
    await stream.close()


async def test_committed_language_overrides_the_last_partial():
    sock = FakeSocket(
        [
            {"message_type": "partial_transcript", "text": "bonjour", "language_code": "eng"},
            {"message_type": "committed_transcript", "text": "Bonjour."},
            {"message_type": "committed_transcript_with_timestamps", "language_code": "fra", "words": []},
        ]
    )
    adapter, _ = stt(sock)
    stream = await adapter.open_stream(STTStreamConfig())
    events = await collect(stream, 2)
    assert events[1].is_final and events[1].language_code == "fra"
    await stream.close()


async def test_final_is_emitted_even_if_the_timestamps_message_never_comes():
    sock = FakeSocket([{"message_type": "committed_transcript", "text": "Hello"}])
    adapter, _ = stt(sock)
    stream = await adapter.open_stream(STTStreamConfig())
    events = await asyncio.wait_for(collect(stream, 1), timeout=2)
    assert events[0].text == "Hello" and events[0].language_code is None
    await stream.close()


async def test_empty_final_is_ignored():
    sock = FakeSocket(
        [
            {"message_type": "committed_transcript", "text": "   "},
            {"message_type": "committed_transcript", "text": "Yes"},
        ]
    )
    adapter, _ = stt(sock)
    stream = await adapter.open_stream(STTStreamConfig())
    events = await asyncio.wait_for(collect(stream, 1), timeout=2)
    assert events[0].text == "Yes"
    await stream.close()


async def test_garbage_and_unknown_messages_are_ignored():
    sock = FakeSocket(["not json", "[1,2]", {"no_type": 1}, {"message_type": "something_new"}, {"message_type": "committed_transcript", "text": "ok"}])
    adapter, _ = stt(sock)
    stream = await adapter.open_stream(STTStreamConfig())
    assert (await asyncio.wait_for(collect(stream, 1), timeout=2))[0].text == "ok"
    await stream.close()


# --------------------------------------------------------------------- errors
@pytest.mark.parametrize(
    "message_type,code,recoverable",
    [
        ("auth_error", "auth", False),
        ("scribeAuthError", "auth", False),
        ("quota_exceeded", "quota_exceeded", False),
        ("scribeQuotaExceededError", "quota_exceeded", False),
        ("rate_limited", "rate_limited", True),
        ("scribeRateLimitedError", "rate_limited", True),
        ("transcriber_error", "transcriber", True),
        ("scribeError", "error", True),
        ("session_time_limit_exceeded", "session_time_limit_exceeded", True),
        ("Scribe Invalid Request Error", "invalid_request", False),
    ],
)
async def test_provider_error_messages_become_provider_errors(message_type, code, recoverable):
    sock = FakeSocket([{"message_type": message_type, "error": "details"}])
    adapter, _ = stt(sock)
    stream = await adapter.open_stream(STTStreamConfig())
    with pytest.raises(ProviderError) as err:
        await asyncio.wait_for(collect(stream, 1), timeout=2)
    assert err.value.code == code and err.value.recoverable is recoverable
    await stream.close()


async def test_text_received_before_an_error_is_still_delivered():
    sock = FakeSocket(
        [
            {"message_type": "committed_transcript", "text": "Help me"},
            {"message_type": "rate_limited", "error": "slow down"},
        ]
    )
    adapter, _ = stt(sock)
    stream = await adapter.open_stream(STTStreamConfig())
    got = []
    with pytest.raises(ProviderError):
        async for ev in stream.events():
            got.append(ev.text)
    assert got == ["Help me"]
    await stream.close()


async def test_clean_close_ends_the_event_stream():
    sock = FakeSocket([{"message_type": "committed_transcript", "text": "Bye"}, closed_ok()])
    adapter, _ = stt(sock)
    stream = await adapter.open_stream(STTStreamConfig())
    assert [e.text async for e in stream.events()] == ["Bye"]
    await stream.close()


async def test_dropped_connection_is_a_recoverable_error():
    sock = FakeSocket([closed_error()])
    adapter, _ = stt(sock)
    stream = await adapter.open_stream(STTStreamConfig())
    with pytest.raises(ProviderError) as err:
        async for _ in stream.events():
            pass
    assert err.value.code == "connection_lost" and err.value.recoverable
    await stream.close()


async def test_close_is_idempotent_and_ends_a_waiting_consumer():
    sock = FakeSocket()
    adapter, _ = stt(sock)
    stream = await adapter.open_stream(STTStreamConfig())
    consumer = asyncio.create_task(collect(stream, 1))
    await asyncio.sleep(0.01)
    await stream.close()
    await stream.close()
    assert await asyncio.wait_for(consumer, timeout=1) == []
    assert sock.closed


async def test_api_key_never_appears_in_errors_or_logs(caplog):
    caplog.set_level(logging.DEBUG)
    adapter, _ = stt(failures=[OSError(f"failed with {KEY}")] * 20, elevenlabs_max_retries=0)
    with pytest.raises(ProviderError) as err:
        await adapter.open_stream(STTStreamConfig())
    assert KEY not in str(err.value) and KEY not in caplog.text


# --------------------------------------------------------------- health check
async def test_health_check_true_when_session_starts():
    sock = FakeSocket([{"message_type": "session_started", "session_id": "s", "config": {}}])
    adapter, _ = stt(sock)
    assert await adapter.health_check() is True
    assert sock.closed


async def test_health_check_false_on_failure_or_no_key():
    adapter, _ = stt(failures=[OSError("down")])
    assert await adapter.health_check() is False
    assert await ElevenLabsSTT(Settings(_env_file=None), FakeConnector()).health_check() is False
