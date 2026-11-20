"""
In-memory live-session store with tenant checks, concurrency limits and
timeouts. Suitable for one process; a multi-process deployment needs a shared
store (e.g. Redis) behind the same methods. Nothing here is persisted.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.core.config import Settings
from app.services.voice.errors import ProviderError
from app.services.voice.schemas.voice_session import SessionState, VoiceSession


class SessionLimitError(Exception):
    """Too many calls for this business right now."""


class InMemorySessionStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sessions: dict[UUID, VoiceSession] = {}
        self._starts: dict[UUID, deque[datetime]] = {}

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def active_count(self, business_id: UUID) -> int:
        return sum(
            1 for s in self._sessions.values() if s.business_id == business_id and s.state is not SessionState.ENDED
        )

    def create(self, business_id: UUID, **fields) -> VoiceSession:
        now = self._now()
        if self.active_count(business_id) >= self._settings.voice_max_concurrent_sessions_per_business:
            raise SessionLimitError("concurrent session limit reached")
        starts = self._starts.setdefault(business_id, deque())
        while starts and now - starts[0] > timedelta(minutes=1):
            starts.popleft()
        if len(starts) >= self._settings.voice_max_new_sessions_per_minute_per_business:
            raise SessionLimitError("new session rate limit reached")
        starts.append(now)
        fields.setdefault("language_code", self._settings.voice_default_language)
        session = VoiceSession(business_id=business_id, **fields)
        self._sessions[session.session_id] = session
        return session

    def get(self, business_id: UUID, session_id: UUID) -> VoiceSession | None:
        """A session is visible only to the business that owns it."""
        session = self._sessions.get(session_id)
        return session if session is not None and session.business_id == business_id else None

    def touch(self, session: VoiceSession) -> None:
        session.last_activity_at = self._now()

    def end(self, session: VoiceSession) -> None:
        session.state = SessionState.ENDED
        session.ended_at = self._now()

    def sweep(self, now: datetime | None = None) -> list[VoiceSession]:
        """End sessions that were silent too long or ran past the maximum length."""
        now = now or self._now()
        silence = timedelta(seconds=self._settings.voice_silence_timeout_seconds)
        longest = timedelta(seconds=self._settings.voice_session_max_seconds)
        ended = []
        for s in self._sessions.values():
            if s.state is SessionState.ENDED:
                continue
            if now - s.last_activity_at > silence or now - s.started_at > longest:
                self.end(s)
                ended.append(s)
        return ended

    def discard(self, session: VoiceSession) -> None:
        """Drop an ended session (and its transcript) from memory once it has been saved."""
        if session.state is SessionState.ENDED:
            self._sessions.pop(session.session_id, None)
