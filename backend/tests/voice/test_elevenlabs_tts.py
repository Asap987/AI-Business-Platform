import asyncio
import base64
import json

import pytest

from app.core.config import Settings
from app.services.voice.errors import ProviderError
from app.services.voice.providers.elevenlabs_tts import ElevenLabsTTS
from app.services.voice.schemas.speech_response import TTSRequest, VoiceSettingsOverride

KEY = "xi-test-never-leak"


def settings(**kw):
    kw.setdefault("elevenlabs_api_key", KEY)
    return Settings(_env_file=None, **kw)


def req(**kw):
    return TTSRequest(voice_id="voiceA", language_code="en", model_id="m1", **kw)


def audio(b: bytes) -> str:
    return json.dumps({"audio": base64.b64encode(b).decode()})


class FakeSocket:
    """Replies are queued up front; recv blocks when empty until closed."""

    def __init__(self, replies=(), raise_on_recv=None):
        self.sent, self.closed = [], False
        self._q: asyncio.Queue = asyncio.Queue()
        for r in replies:
            self._q.put_nowait(r)
        self._raise = raise_on_recv

    async def send(self, m):
        self.sent.append(json.loads(m))

    async def recv(self):
        if self._raise and self._q.empty():
            raise self._raise
        return await self._q.get()

    async def close(self):
        self.closed = True


class FakeConnector:
    def __init__(self, socket=None, error=None):
        self.socket, self.error, self.calls = socket, error, []

    async def __call__(self, url, headers):
        self.calls.append((url, headers))
        if self.error:
            raise self.error
        return self.socket


async def texts(*parts):
    for p in parts:
        yield p


async def collect(tts, request, parts):
    return [c async for c in tts.synthesize_stream(request, texts(*parts))]


async def test_streams_audio_in_order_and_ends_on_final_marker():
    sock = FakeSocket([audio(b"AA"), audio(b"BB"), json.dumps({"isFinal": True})])
    chunks = await collect(ElevenLabsTTS(settings(), FakeConnector(sock)), req(), ["Hello there.", "Bye."])
    assert [(c.audio, c.sequence, c.is_final) for c in chunks] == [(b"AA", 0, False), (b"BB", 1, False), (b"", 2, True)]
    assert sock.closed


async def test_messages_sent_follow_the_documented_protocol():
    sock = FakeSocket([json.dumps({"isFinal": True})])
    await collect(ElevenLabsTTS(settings(), FakeConnector(sock)), req(settings=VoiceSettingsOverride(speed=1.1)), ["One.", "  ", "Two. "])
    assert sock.sent[0] == {"text": " ", "voice_settings": {"speed": 1.1}}
    assert sock.sent[1] == {"text": "One. ", "flush": True}
    assert sock.sent[2] == {"text": "Two. ", "flush": True}  # blank chunk skipped, single trailing space
    assert sock.sent[-1] == {"text": ""}


async def test_url_uses_header_auth_and_configured_options_without_language_or_key():
    sock = FakeSocket([json.dumps({"isFinal": True})])
    conn = FakeConnector(sock)
    await collect(ElevenLabsTTS(settings(elevenlabs_tts_output_format="ulaw_8000"), conn), req(), ["Hi."])
    url, headers = conn.calls[0]
    assert url.startswith("wss://api.elevenlabs.io/v1/text-to-speech/voiceA/stream-input?")
    assert "model_id=m1" in url and "output_format=ulaw_8000" in url and "inactivity_timeout=20" in url
    assert "language_code" not in url and KEY not in url
    assert headers == {"xi-api-key": KEY}


async def test_chunks_report_the_configured_audio_format():
    sock = FakeSocket([audio(b"A"), json.dumps({"isFinal": True})])
    chunks = await collect(ElevenLabsTTS(settings(elevenlabs_tts_output_format="ulaw_8000"), FakeConnector(sock)), req(), ["Hi."])
    assert {c.audio_format for c in chunks} == {"ulaw_8000"}


async def test_barge_in_closing_the_iterator_closes_the_socket_and_stops_sending():
    sock = FakeSocket([audio(b"AA")])  # never sends a final marker
    gen = ElevenLabsTTS(settings(), FakeConnector(sock)).synthesize_stream(req(), texts("Hi."))
    first = await gen.__anext__()
    assert first.audio == b"AA"
    await gen.aclose()
    assert sock.closed


async def test_cancelling_the_consumer_closes_the_socket():
    sock = FakeSocket()  # no replies: waits forever
    tts = ElevenLabsTTS(settings(), FakeConnector(sock))
    task = asyncio.create_task(collect(tts, req(), ["Hi."]))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sock.closed


async def test_server_error_message_becomes_provider_error_without_copying_text():
    sock = FakeSocket([json.dumps({"error": "secret detail", "message": "secret detail"})])
    with pytest.raises(ProviderError) as err:
        await collect(ElevenLabsTTS(settings(), FakeConnector(sock)), req(), ["Hi."])
    assert err.value.code == "tts_error" and "secret" not in str(err.value)
    assert sock.closed


async def test_undecodable_audio_is_an_error():
    sock = FakeSocket([json.dumps({"audio": "!!!not base64!!!"})])
    with pytest.raises(ProviderError) as err:
        await collect(ElevenLabsTTS(settings(), FakeConnector(sock)), req(), ["Hi."])
    assert err.value.code == "bad_audio"


async def test_non_json_and_unrelated_messages_are_ignored():
    sock = FakeSocket(["not json", json.dumps({"alignment": {}}), audio(b"A"), json.dumps({"isFinal": True})])
    chunks = await collect(ElevenLabsTTS(settings(), FakeConnector(sock)), req(), ["Hi."])
    assert [c.audio for c in chunks] == [b"A", b""]


async def test_connection_loss_is_recoverable():
    from websockets.exceptions import ConnectionClosedError

    sock = FakeSocket(raise_on_recv=ConnectionClosedError(None, None))
    with pytest.raises(ProviderError) as err:
        await collect(ElevenLabsTTS(settings(), FakeConnector(sock)), req(), ["Hi."])
    assert (err.value.code, err.value.recoverable) == ("connection_lost", True)


async def test_failure_while_sending_text_surfaces_and_closes():
    class BadSend(FakeSocket):
        async def send(self, m):
            if len(self.sent) >= 1:
                raise OSError("boom")
            await super().send(m)

    sock = BadSend()
    with pytest.raises(ProviderError) as err:
        await collect(ElevenLabsTTS(settings(), FakeConnector(sock)), req(), ["Hi."])
    assert err.value.code == "send_failed" and sock.closed


async def test_missing_key_fails_before_connecting():
    conn = FakeConnector(FakeSocket())
    with pytest.raises(ProviderError) as err:
        await collect(ElevenLabsTTS(Settings(_env_file=None), conn), req(), ["Hi."])
    assert err.value.code == "not_configured" and not err.value.recoverable and conn.calls == []


async def test_connect_retries_are_bounded_and_auth_is_not_retried():
    conn = FakeConnector(error=OSError("down"))
    with pytest.raises(ProviderError) as err:
        await collect(ElevenLabsTTS(settings(elevenlabs_max_retries=2), conn, retry_backoff_seconds=0), req(), ["Hi."])
    assert err.value.code == "connect_failed" and len(conn.calls) == 3

    class Auth(Exception):
        response = type("R", (), {"status_code": 401})()

    conn = FakeConnector(error=Auth())
    with pytest.raises(ProviderError) as err:
        await collect(ElevenLabsTTS(settings(), conn, retry_backoff_seconds=0), req(), ["Hi."])
    assert err.value.code == "auth" and len(conn.calls) == 1


async def test_health_check():
    assert await ElevenLabsTTS(settings()).health_check() is True
    assert await ElevenLabsTTS(Settings(_env_file=None)).health_check() is False
    sock = FakeSocket()
    ok = ElevenLabsTTS(settings(elevenlabs_tts_health_voice_id="v"), FakeConnector(sock))
    assert await ok.health_check() is True and sock.closed
    bad = ElevenLabsTTS(settings(elevenlabs_tts_health_voice_id="v", elevenlabs_max_retries=0), FakeConnector(error=OSError()))
    assert await bad.health_check() is False
