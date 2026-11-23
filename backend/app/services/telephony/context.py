"""What a customer has already told us, carried to whoever takes over (a person, another department, a callback).

Customer details live only in business-owned records (the callback request, the case) and in the reply to the assistant;
they are never copied into the audit log.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class HandoverContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str = Field(default="", max_length=200)           # why the customer called
    summary: str = Field(default="", max_length=1000)         # the conversation so far, in a few sentences
    collected: dict[str, str] = Field(default_factory=dict)   # facts already given, e.g. {"order": "A123"}
    done: list[str] = Field(default_factory=list, max_length=10)            # actions already completed
    open_questions: list[str] = Field(default_factory=list, max_length=10)  # still unanswered

    def model_post_init(self, _ctx) -> None:
        if len(self.collected) > 20 or any(len(k) > 60 or len(v) > 200 for k, v in self.collected.items()):
            raise ValueError("collected facts are too long")
        if any(len(x) > 200 for x in self.done + self.open_questions):
            raise ValueError("list entries are too long")

    def briefing(self) -> str:
        """Plain text for the receiving person or agent."""
        lines = []
        if self.intent:
            lines.append(f"Reason for the call: {self.intent}")
        if self.summary:
            lines.append(f"So far: {self.summary}")
        if self.collected:
            lines.append("Already given: " + "; ".join(f"{k}: {v}" for k, v in self.collected.items()))
        if self.done:
            lines.append("Already done: " + "; ".join(self.done))
        if self.open_questions:
            lines.append("Still open: " + "; ".join(self.open_questions))
        return "\n".join(lines)
