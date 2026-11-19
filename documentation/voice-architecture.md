# Voice AI architecture (OpenAI + ElevenLabs)

Status: **Phases 1–4 done** (audit, design, configuration, provider-independent interfaces, language registry, cost tracking). Phases 5–10 (the real provider adapters, the conversation pipeline, business integration) are **not built yet**. Nothing here has been run against a live provider.

## 1. Audit of the existing project (2026-11-19)

| Area | Finding |
|---|---|
| Backend | A scaffold of empty modules only (`agents`, `cases`, `conversations`, `knowledge`, `workflows`, `departments`, `employees`, `authentication`, `integrations`). `main.py`, `core/security.py`, `database/connection.py` are 0 bytes. No FastAPI app, routes, models or auth exist. |
| Existing OpenAI/ElevenLabs code | None. |
| "Internal Operations Hub" | Does not exist yet. The brief assumes it; the voice engine talks to it through `BusinessToolGateway` so it can be built independently. |
| Database | `schema.sql` (nine tables) defined but not wired in; `migrations/` empty. |
| Frontend | Next.js shell built; expects `/api/v1/auth/*` and dashboard endpoints that the backend does not provide yet. |

Because nothing exists to conflict with, the voice package was added as a new `app/services/voice/` tree without touching existing code. `core/config.py` (previously empty) now holds settings.

## 2. Provider facts checked against official documentation

| Capability | Verified finding |
|---|---|
| ElevenLabs STT, realtime | `scribe_v3_live` (turn prediction, mid-sentence language switching) and `scribe_v2_realtime`. Streaming runs over WebSockets. Latency is **not stated** in the docs. |
| STT language tiers | English, French: excellent (≤5% WER). Hausa: good (>10–20% WER). **Twi/Akan, Ewe, Ga: not supported.** Responses include `language_code` (ISO 639-3) and `language_probability`. |
| ElevenLabs TTS | `eleven_flash_v2_5`: ~100 ms median, 32 languages, 40k chars. `eleven_v3`: 70+ languages incl. Hausa, 5,000 chars, not a low-latency model. `eleven_turbo_v2_5` is deprecated. |
| TTS language support | English, French: all models. Hausa: `eleven_v3` (and v4) only. **Twi, Ewe, Ga: no model.** |
| OpenAI API | Responses API (`client.responses.create`) is the documented path. Text models listed: `gpt-6.2-astra`, `gpt-6.2-sol`, `gpt-6.1-terra`, `gpt-6-luna` (tool calling, structured outputs, streaming). Realtime models (`gpt-realtime-2.1`) exist but do not fit a design where ElevenLabs supplies the voice. |

Not yet verified (needed before Phases 5–7): the exact ElevenLabs realtime STT WebSocket message format and commit settings, the TTS WebSocket/streaming API, and the official Python SDK method names. The adapters will be written against the docs for those, not from memory.

Sources: ElevenLabs docs (speech-to-text capabilities, models, supported languages) and OpenAI API docs (models, Responses API), read 2026-11-19.

## 3. Decisions (the "best options")

1. **Composed pipeline, not an all-in-one voice agent.** Customer audio → Scribe → our conversation manager → OpenAI (+ tools via our backend) → ElevenLabs TTS. This follows the brief ("OpenAI is the brain, ElevenLabs the ears and voice"), keeps business rules and tenant isolation in our code, and lets either speech provider be replaced alone. Cost: we own latency tuning.
2. **Models are configuration.** Defaults: STT `scribe_v3_live` (fallback `scribe_v2_realtime`), TTS `eleven_flash_v2_5` (English/French), `eleven_v3` only for Hausa, reasoning `gpt-6.1-terra` (fast tier, tool calling), `gpt-6-luna` for cheap classification/summaries. Pricing and latency of these OpenAI models must be checked before launch; none is assumed.
3. **Latency design.** Stream audio in; act only on `is_final` transcripts; stream the model's text out and flush it to TTS at sentence/clause boundaries so the first audio plays before the reply is complete.
4. **Interruptions (barge-in).** While the session is `SPEAKING`, detected customer speech cancels the TTS task, flushes audio queued at the telephony layer, and marks that AI turn `interrupted`. Cancelling the consumer of `synthesize_stream` must stop generation (part of the interface contract).
5. **Language registry, conservative by default.** Provider support comes from the docs above; every language starts `NOT_TESTED`, which makes it a *prototype* language: usable outside production only, never in production until tested with real Ghanaian speakers. Unsupported or low-confidence speech is never guessed or silently translated: the AI asks for clarification, offers supported languages, then escalates to a human after repeated attempts.
6. **Live state vs permanent records.** Live call state (`VoiceSession`) sits behind a session-store interface (in-memory for the prototype, Redis when running more than one instance). Permanent data goes to the existing `conversations` and `cases` tables.
7. **Business actions only through `BusinessToolGateway`.** Every call carries `business_id`; implementations must enforce that business's permissions. The AI may only state what a `ToolResult` confirms, and `requires_human_approval` blocks refunds and adjustments.
8. **Costs are never assumed.** `voice_pricing` has no default rates. Estimates list the rate and date used, and report missing rates as gaps.
9. **Recording off by default**, consent required, retention configurable.

## 4. DECISION NEEDED: Twi, Ewe and Ga

ElevenLabs supports none of these for speech recognition or speech generation. Twi is the most widely spoken language in Ghana, so this affects the product, not just the roadmap. Options:

- **A. Launch with English, French and (experimental) Hausa. Twi/Ewe/Ga callers are told honestly and transferred to a person.** Works today, no new provider. *This is what the code currently does.*
- **B. Add a second speech provider for Ghanaian languages.** Your brief forbids this without approval. It needs a evaluation of which providers actually cover Twi/Ewe/Ga, with recorded tests, before any commitment.
- **C. Support Ghanaian languages by text only** (SMS/WhatsApp, where OpenAI handles the language) while voice stays on A.

My recommendation: ship A now, and run a small provider evaluation for B in parallel. Please confirm.

## 5. Proposed database changes (not applied)

The existing schema has `conversations` and `cases` but nothing to hold what was said or what a call cost. Proposed additions: `conversation_messages` (conversation_id, speaker, text, language, interrupted, created_at); `voice_usage` (business_id, conversation_id, stt_seconds, tts_characters, tokens per model, provider_errors, estimated_cost_usd, rates_used JSONB); `conversations.language_code` and `recording_consent`; `cases.status` needs a `waiting_department` value because the dashboard and the escalation flow both need it. These will be written as migrations when the backend's migration tooling exists.

## 6. What exists in code

```
backend/app/core/config.py                     settings, secrets as SecretStr, pricing table
backend/app/services/voice/
  schemas/        transcription, speech_response, voice_session
  interfaces/     speech_to_text, text_to_speech, reasoning, business_tools
  language_manager.py                           registry + language decisions
  usage.py                                      usage records + cost estimate
backend/tests/voice/                            27 tests, no network, no API keys
backend/.env.example
```

Run the tests: `cd backend && pip install -r requirements.txt && python -m pytest`.

## 7. Next phases

5. ElevenLabs STT adapter (after verifying the realtime protocol), with a mocked-socket test suite.
6. OpenAI reasoning adapter (Responses API streaming + function calling; system prompt that forbids inventing policy or claiming unconfirmed outcomes).
7. ElevenLabs TTS adapter (streaming, cancellation).
8. Conversation manager and session store: turn-taking, barge-in, timeouts, graceful failure → human transfer.
9. Business gateway implementation once the knowledge, cases and departments services exist.
10. Test matrix from the brief, opt-in live tests (`RUN_LIVE_PROVIDER_TESTS=true`, clearly marked as paid).

## 8. Before connecting real phone numbers

Choose and approve a telephony provider (Ghana number availability and audio-streaming support are unverified); build the telephony adapter (inbound/outbound, transfer, status callbacks); run recorded accuracy tests with Ghanaian-accented English, French and Hausa; fill in approved voice IDs; fill `voice_pricing` from current price lists; build auth, tenant isolation and rate limiting in the API layer; legal review of call-recording consent.
