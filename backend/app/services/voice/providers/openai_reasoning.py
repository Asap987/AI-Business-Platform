"""
OpenAI reasoning adapter, using the Responses API with streaming and function
calling through the official ``openai`` SDK.

Event and field names used here were read from the installed SDK's own types
(checked 2026-11-20): ``response.output_text.delta`` (``delta``),
``response.output_item.done`` with a ``function_call`` item (``call_id``,
``name``, ``arguments``), ``response.completed`` / ``response.incomplete`` /
``response.failed`` (``response``), ``error`` (``code``, ``message``), and
``response.usage.input_tokens`` / ``output_tokens``.

``store=False`` is set on every request so conversations are not kept in
OpenAI's response store by default.

Not provided yet: intent, sentiment and urgency. ``TurnCompleted`` leaves them
None; the explicit escalation tool, not a guess, is what signals a handover.
Nothing here has been run against the live service.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import openai
from openai import AsyncOpenAI

from app.core.config import Settings
from app.services.voice.errors import ProviderError
from app.services.voice.interfaces.reasoning import (
    ReasoningEngine,
    ReasoningEvent,
    ReasoningRequest,
    ReasoningUsage,
    TextDelta,
    ToolCallRequested,
    TurnCompleted,
)
from app.services.voice.language_manager import LanguageManager
from app.services.voice.privacy import ProviderControls, redact_for_provider
from app.services.voice.prompts import build_system_prompt
from app.services.voice.schemas.voice_session import Speaker

logger = logging.getLogger(__name__)
PROVIDER = "openai"


def map_openai_error(exc: Exception) -> ProviderError:
    """Provider-neutral error with a recoverable flag. Never includes the message body."""
    if isinstance(exc, ProviderError):
        return exc
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return ProviderError(PROVIDER, "auth", "OpenAI rejected the API key.", recoverable=False)
    if isinstance(exc, openai.RateLimitError):
        if getattr(exc, "code", None) == "insufficient_quota":
            return ProviderError(PROVIDER, "quota_exceeded", "OpenAI quota exhausted.", recoverable=False)
        return ProviderError(PROVIDER, "rate_limited", "OpenAI rate limit reached.", recoverable=True)
    if isinstance(exc, (openai.NotFoundError, openai.BadRequestError, openai.UnprocessableEntityError)):
        return ProviderError(PROVIDER, "invalid_request", "OpenAI rejected the request.", recoverable=False)
    if isinstance(exc, openai.APITimeoutError):
        return ProviderError(PROVIDER, "timeout", "OpenAI did not respond in time.", recoverable=True)
    if isinstance(exc, openai.APIConnectionError):
        return ProviderError(PROVIDER, "connection_failed", "Could not reach OpenAI.", recoverable=True)
    if isinstance(exc, openai.APIStatusError):
        return ProviderError(
            PROVIDER, "server_error", f"OpenAI returned status {exc.status_code}.", recoverable=exc.status_code >= 500
        )
    return ProviderError(PROVIDER, "unexpected", f"Unexpected failure ({type(exc).__name__}).", recoverable=True)


class OpenAIReasoning(ReasoningEngine):
    def __init__(
        self,
        settings: Settings,
        languages: LanguageManager,
        client: Any | None = None,
        max_output_tokens: int = 400,
        controls: ProviderControls | None = None,
    ) -> None:
        self._controls = controls
        self._settings = settings
        self._languages = languages
        self._max_output_tokens = max_output_tokens  # replies are spoken, so keep them short
        self._client = client

    def _get_client(self) -> Any:
        if self._controls is not None:
            self._controls.require(PROVIDER)
        if self._client is None:
            key = self._settings.openai_api_key
            if key is None or not key.get_secret_value():
                raise ProviderError(PROVIDER, "not_configured", "OPENAI_API_KEY is not set.", recoverable=False)
            self._client = AsyncOpenAI(
                api_key=key.get_secret_value(),
                timeout=self._settings.openai_request_timeout_seconds,
                max_retries=self._settings.openai_max_retries,
            )
        return self._client

    # ---- request building -------------------------------------------------
    def build_input(self, request: ReasoningRequest) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []

        def clean(text: str) -> str:
            return redact_for_provider(
                text,
                secrets=self._settings.voice_redact_secrets,
                contact_details=self._settings.voice_redact_contact_details,
            )

        for turn in request.history:
            if turn.speaker is Speaker.CUSTOMER:
                items.append({"role": "user", "content": clean(turn.text)})
            elif turn.speaker is Speaker.AI:
                items.append({"role": "assistant", "content": turn.text})
        items.append({"role": "user", "content": clean(request.user_text)})
        for ex in request.tool_exchanges:
            items.append(
                {
                    "type": "function_call",
                    "call_id": ex.call_id,
                    "name": ex.tool_name,
                    "arguments": json.dumps(ex.arguments),
                }
            )
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": ex.call_id,
                    "output": json.dumps(
                        {
                            "ok": ex.result.ok,
                            "summary": ex.result.summary,
                            "data": ex.result.data,
                            "requires_human_approval": ex.result.requires_human_approval,
                        }
                    ),
                }
            )
        return items

    def build_kwargs(self, request: ReasoningRequest) -> dict[str, Any]:
        language = self._languages.get(request.language_code)
        kwargs: dict[str, Any] = {
            "model": self._settings.openai_reasoning_model,
            "instructions": build_system_prompt(
                business_context=request.business_context,
                language_name=language.name if language else request.language_code,
                language_guidance=request.language_guidance,
            ),
            "input": self.build_input(request),
            "stream": True,
            "store": False,
            "max_output_tokens": self._max_output_tokens,
        }
        if request.tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                    "strict": False,  # arguments are validated by the business gateway
                }
                for t in request.tools
            ]
            kwargs["tool_choice"] = "auto"
            kwargs["parallel_tool_calls"] = False  # one confirmed action at a time
        return kwargs

    # ---- streaming --------------------------------------------------------
    def _usage(self, response: Any) -> ReasoningUsage:
        usage = getattr(response, "usage", None)
        return ReasoningUsage(
            model=self._settings.openai_reasoning_model,  # configured id, matches the pricing table
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        )

    async def respond_stream(self, request: ReasoningRequest) -> AsyncIterator[ReasoningEvent]:
        stream = None
        try:
            stream = await self._get_client().responses.create(**self.build_kwargs(request))
            async for event in stream:
                etype = getattr(event, "type", None)
                if etype == "response.output_text.delta":
                    if event.delta:
                        yield TextDelta(text=event.delta)
                elif etype == "response.output_item.done":
                    item = event.item
                    if getattr(item, "type", None) == "function_call":
                        try:
                            arguments = json.loads(item.arguments or "{}")
                            if not isinstance(arguments, dict):
                                raise ValueError("arguments must be an object")
                        except ValueError as exc:
                            # Never run a tool with arguments we could not read.
                            raise ProviderError(
                                PROVIDER, "invalid_tool_arguments", "The model sent unreadable tool arguments.",
                                recoverable=True,
                            ) from exc
                        yield ToolCallRequested(call_id=item.call_id, tool_name=item.name, arguments=arguments)
                elif etype == "response.completed":
                    yield TurnCompleted(usage=self._usage(event.response))
                    return
                elif etype == "response.incomplete":
                    # Usually the reply hit the length cap: deliver what was spoken, and record usage.
                    logger.warning("OpenAI response incomplete")
                    yield TurnCompleted(usage=self._usage(event.response))
                    return
                elif etype == "response.failed":
                    error = getattr(event.response, "error", None)
                    logger.warning("OpenAI response failed: %s", getattr(error, "code", "unknown"))
                    raise ProviderError(PROVIDER, "response_failed", "OpenAI could not complete the reply.", recoverable=True)
                elif etype == "error":
                    logger.warning("OpenAI stream error: %s", getattr(event, "code", "unknown"))
                    raise ProviderError(PROVIDER, "stream_error", "OpenAI reported an error.", recoverable=True)
            raise ProviderError(PROVIDER, "stream_ended", "The reply ended unexpectedly.", recoverable=True)
        except ProviderError:
            raise
        except Exception as exc:
            if exc.__class__.__name__ in ("CancelledError", "GeneratorExit"):
                raise
            raise map_openai_error(exc) from exc
        finally:
            if stream is not None and hasattr(stream, "close"):
                try:
                    await stream.close()
                except Exception:
                    pass

    async def health_check(self) -> bool:
        try:
            await self._get_client().models.retrieve(self._settings.openai_reasoning_model)
            return True
        except Exception:
            return False
