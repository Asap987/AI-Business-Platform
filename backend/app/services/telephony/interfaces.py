"""Provider-independent telephony contract. Twilio, Telnyx, Africa's Talking or any other carrier is one adapter
implementing ``TelephonyProvider``; the call logic never imports a provider.

No adapter exists yet: no provider is approved and no number is bought. ``mock.MockTelephony`` is a SIMULATION
for tests and demos and says so in its ``simulated`` flag.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class TransferOutcome(str, Enum):
    CONFIRMED = "confirmed"      # the provider reported the other party answered and the legs are bridged
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    FAILED = "failed"            # the provider rejected or errored
    UNCONFIRMED = "unconfirmed"  # the provider gave no final answer in time; NEVER treat this as success


@dataclass(frozen=True)
class TransferTarget:
    phone: str  # E.164, e.g. +233...
    label: str  # for people reading logs (a name or department), never used for routing
    extension: str | None = None  # dialled after connecting when the carrier reaches a switchboard


@dataclass(frozen=True)
class TransferResult:
    outcome: TransferOutcome
    provider_ref: str | None = None  # the provider's own id for the attempt, for support


class TelephonyProvider(ABC):
    name: str
    simulated: bool = False

    @abstractmethod
    async def transfer_call(self, call_ref: str, target: TransferTarget) -> TransferResult:
        """Hand a live call to ``target`` and report what the provider says happened."""

    @abstractmethod
    async def hang_up(self, call_ref: str) -> None: ...

    @abstractmethod
    async def health_check(self) -> bool: ...
