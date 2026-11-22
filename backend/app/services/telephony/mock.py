"""SIMULATED telephony for tests and demos. Results are scripted, not real: anything produced with this provider
must be labelled as simulated and must never be shown to a customer as a real transfer."""

from __future__ import annotations

from app.services.telephony.interfaces import TelephonyProvider, TransferOutcome, TransferResult, TransferTarget


class MockTelephony(TelephonyProvider):
    name = "mock"
    simulated = True

    def __init__(self, outcomes: dict[str, TransferOutcome] | None = None, default: TransferOutcome = TransferOutcome.CONFIRMED):
        self._outcomes = outcomes or {}
        self._default = default
        self.attempts: list[tuple[str, str]] = []  # (call_ref, phone)
        self.hung_up: list[str] = []

    async def transfer_call(self, call_ref: str, target: TransferTarget) -> TransferResult:
        self.attempts.append((call_ref, target.phone))
        return TransferResult(self._outcomes.get(target.phone, self._default), provider_ref=f"mock-{len(self.attempts)}")

    async def hang_up(self, call_ref: str) -> None:
        self.hung_up.append(call_ref)

    async def health_check(self) -> bool:
        return True
