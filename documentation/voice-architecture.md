# Voice AI architecture (OpenAI + ElevenLabs)

Status: **Phases 1–9 built and tested offline** (audit, design, configuration, interfaces, language registry, cost tracking, ElevenLabs STT, OpenAI reasoning, ElevenLabs TTS, conversation manager with barge-in and human hand-over, in-memory business gateway and session store, data-protection helpers). **140 automated tests pass with no network and no API keys.** **Nothing has been run against a live OpenAI or ElevenLabs account**, there is no telephony, and the real backend API (auth, database-backed services) does not exist yet. See "Limitations" below before describing this to a customer.

### Phase 5 notes: ElevenLabs STT adapter

Built on the raw realtime WebSocket protocol (documented in full) rather than the Python SDK, whose documented surface is callback-based and only shown for URL streaming. Verified against the API reference: endpoint, `xi-api-key` header auth, `input_audio_chunk`/`audio_base_64` messages, `session_started`/`partial_transcript`/`committed_transcript`/`committed_transcript_with_timestamps`, error message types.

Behaviour: only `is_final` transcripts should be acted on; the final language comes from `committed_transcript_with_timestamps` (the adapter waits a short, configurable time for it, then emits without); bounded connection retries with backoff; fallback from `scribe_v3_live` to `scribe_v2_realtime` if the primary cannot connect (not on a bad key); errors become provider-neutral `ProviderError`s with a `recoverable` flag so the conversation manager can retry, fall back or transfer to a human. API keys travel only in a header and are never logged.

**Unverified, to confirm in the opt-in live test:** whether `turn_prediction` is accepted for `scribe_v3_live` (the default for that model; `vad` is documented for all); the accepted format of the `language_code` hint (ISO 639-1 vs 639-3); the format of the `keyterms` parameter (not sent yet, so business vocabulary does not bias recognition yet); and whether a connect-only health check counts as a billed session. The realtime stream has **no language-confidence value**, so the low-confidence clarification rule in `LanguageManager` cannot trigger for this provider; unreliable language is instead visible as `language_code` being absent or changing.

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

### Phases 6–9 notes

**OpenAI reasoning (`providers/openai_reasoning.py`).** Responses API, streamed, function calling, `store=False`, one tool call at a time, short output cap because replies are spoken. Event and field names were read from the installed SDK's own types and are guarded by a test that fails if the SDK renames them. Tool arguments the model sends that cannot be parsed are never executed. Intent, sentiment and urgency are **not** produced yet.

**ElevenLabs TTS (`providers/elevenlabs_tts.py`).** `stream-input` WebSocket, text sent sentence by sentence with `flush`, audio decoded and forwarded in order, ends on `isFinal`. Closing the iterator or cancelling the task closes the socket (this is barge-in). Shared connection and retry code lives in `providers/elevenlabs_common.py` and the STT adapter was moved onto it with its tests re-run. **Unverified:** the server error-message shape, the list of valid `output_format` values (`pcm_16000` is the default and is configurable, use `ulaw_8000` for telephony only after testing), and whether `language_code` is accepted by each model (not sent).

**Conversation manager (`conversation_manager.py`).** One customer utterance → language decision → reasoning → tools → speech → audio sink. A new utterance or `interrupt()` cancels reasoning and speech together and records the AI turn as interrupted. At most three tool rounds. A tool the model was not offered is refused; a tool that crashes is reported to the model as failed. Any provider failure, a missing voice, or too many tool rounds triggers a human hand-over through the gateway and the session is flagged `ESCALATING` for the telephony layer. Unsupported language: never guessed, alternatives offered, hand-over after two attempts.

**Database gateway (`database_gateway.py`).** The real-database implementation of the same interface: `create_case` and `escalate_to_human`, using the same case rules as the HTTP API, scoped to the business and recorded in case history as made by the AI. It needs a caller-supplied resolver that returns a customer only when the caller is reliably identified; otherwise no case is logged and the assistant is told to offer a person. `search_knowledge` is not offered because no knowledge-base storage exists yet. Tested on SQLite and PostgreSQL; nothing wires the voice session to a real caller identity yet.

**Business gateway (`business_gateway.py`) and session store (`session_store.py`).** In-memory prototype only. Tools: `search_knowledge`, `create_case`, `escalate_to_human`. Every call is scoped to the business, arguments are validated, an unknown business, disabled tool and nonexistent tool all produce the same refusal, and tests prove knowledge, cases and sessions never cross businesses. The store enforces per-business concurrent-session and new-sessions-per-minute limits and ends silent or overlong sessions. A real gateway must call the real services behind the same interface and add per-user permissions and approval for financial actions (not built).

### Data protection (priority) — what is and is not done

Done and tested: keys only in headers or `SecretStr`, never in URLs, logs or error text; provider error text is never copied into our errors; a test proves transcript text does not reach the logs; OpenAI `store=False`; recording off by default and consent required; card numbers (Luhn-checked) and spoken passwords/PINs/codes are removed before text goes to OpenAI (`privacy.py`; optional masking of emails and phone numbers via `VOICE_REDACT_CONTACT_DETAILS`); per-provider shutdown switch (`ProviderControls`), after which requests fail as non-recoverable and the call is handed to a person; `ELEVENLABS_ENABLE_LOGGING=false` sends `enable_logging=false`; ended sessions can be discarded from memory.

Verified from the ElevenLabs page (2026-11-20): Zero Retention Mode is per request via `enable_logging=false`, **enterprise-only**, and "the TTS WebSocket connection" is covered. The page does **not** confirm the parameter on the `stream-input` URL or on the realtime speech-to-text socket. Sending it on an ineligible account may be ignored or rejected: confirm with ElevenLabs in writing and test with the account before promising "zero retention" to any customer.

Not done: written confirmation of OpenAI Zero Data Retention / abuse-monitoring terms; vendor register and data-processing agreements; data classification enforced in code; the Control Center "Provider Privacy" screen; encryption, backups, row-level security and audit-log storage (no database layer exists yet); retention deletion jobs; incident-response procedure; legal review under Ghana's Data Protection Act, 2012 (Act 843). Redaction is a safety net, not a guarantee: free speech can contain identifiers the patterns miss.

### Limitations and remaining work

1. **No live testing.** Every provider claim above is from documentation or SDK types, not from a real call. First live run should be the opt-in tests (`RUN_LIVE_PROVIDER_TESTS=true`, paid).
2. **No telephony.** Nothing connects a phone call to the audio sink or STT. Provider choice (Ghana numbers, media streaming) is open.
3. **Backend only partly built.** Login, tenant-scoped dashboard endpoints and the database exist (see `frontend-api-contract.md`), but the voice gateway and session store are still in memory, nothing connects the voice code to the API, and the schema additions in section 5 (messages, usage) are unapplied.
4. **Language support is unproven** for everything except what tests can show offline; Twi, Ewe and Ga stay unsupported (Option A) and Hausa/French are prototype-only until accuracy tests pass.
5. **STT has no language-confidence value**, so the low-confidence rule cannot trigger for it.
6. **Model fallback** (`openai_fast_model`) is configured but not wired into the reasoning adapter; a failed reasoning call goes straight to a human.
7. **No model-quality testing** (prompt-injection resistance, hallucination rate): the prompt contains the rules; only the fake-model plumbing is tested.
8. Voice IDs, pricing rates and per-business context assembly are caller-supplied; no approved voices are configured.

## 5. Proposed database changes (not applied)

The existing schema has `conversations` and `cases` but nothing to hold what was said or what a call cost. Proposed additions: `conversation_messages` (conversation_id, speaker, text, language, interrupted, created_at); `voice_usage` (business_id, conversation_id, stt_seconds, tts_characters, tokens per model, provider_errors, estimated_cost_usd, rates_used JSONB); `conversations.language_code` and `recording_consent`; `cases.status` needs a `waiting_department` value because the dashboard and the escalation flow both need it. These will be written as migrations when the backend's migration tooling exists.

## 6. What exists in code

```
backend/app/core/config.py                     settings, secrets as SecretStr, pricing table
backend/app/services/voice/
  schemas/        transcription, speech_response, voice_session
  interfaces/     speech_to_text, text_to_speech, reasoning, business_tools
  errors.py                                     provider-neutral ProviderError
  providers/elevenlabs_common.py                shared connect/retry code
  providers/elevenlabs_stt.py                   realtime speech-to-text adapter
  providers/elevenlabs_tts.py                   streaming text-to-speech adapter
  providers/openai_reasoning.py                 Responses API adapter
  prompts.py                                    system prompt and safety rules
  privacy.py                                    redaction + provider shutdown switch
  conversation_manager.py                       turn loop, barge-in, hand-over
  business_gateway.py                           in-memory tenant-scoped tools (prototype)
  session_store.py                              in-memory sessions, limits, timeouts
  language_manager.py                           registry + language decisions
  usage.py                                      usage records + cost estimate
backend/tests/voice/                            140 tests, no network, no API keys
backend/.env.example
```

Run the tests: `cd backend && pip install -r requirements.txt && python -m pytest`.

## 6b. Departmental routing (2026-11-22/23)

`TransferService` checks, in order: department exists in the same business, accepts transfers, is open (hours and time zone), has active and available staff with a number. Staff are tried by `routing_priority`; a fallback department is used if nobody can be reached (same business, never loops, at most 3 hops, 3 attempts in total). If nothing works the assistant offers a callback. Conversation context (`HandoverContext`) goes to the receiver as a briefing and onto the callback record, never into the audit trail. Only `MockTelephony` exists: results are labelled simulated and the assistant is told not to say the caller is connected. Not built: AI-to-AI hand-over between department assistants, a department switchboard model, any real provider adapter.

## 6c. Business profile in the assistant's instructions (2026-11-25)

`app/services/voice/business_context.py` builds the business information from the profile and department hours: name, industry, description, languages, hours, branches, policies, tone and greeting. Never included: staff names, extensions, customer or case data. Business contact details are left out when the business has contact masking on, and the whole text goes through the same redaction as caller speech (card numbers, passwords, optionally emails and phones) and is capped at 6000 characters. This text is sent to OpenAI on a live call, so it falls under the privacy gate: nothing is sent until the provider questions are answered and approved. Not yet verified live: how the model uses it.

## 6d. Hand-over between department assistants (2026-11-27)

Tool `hand_over_to_department_assistant` (department, reason, context). The call stays open; the session records the active department and a briefing (department description, reason, `HandoverContext`), and every later model request includes it, so the new "assistant" does not repeat questions. This is not telephony: no person is involved, and the assistant is told never to say one was connected. Limits: department must belong to the same business (otherwise "does not exist"), at most 3 hand-overs per call. The briefing lives in the live session only; the audit log gets nothing. Still the same underlying model with a different focus; separate per-department agents with their own tools or voices are not built.

## 7. Next phases

Phases 5–9 are done (offline). Remaining: opt-in live provider tests (paid, with explicit approval); the real backend API and database; telephony adapter and call lifecycle; wiring model fallback; the Control Center provider-privacy screen; accuracy tests per language.

## 8. Before connecting real phone numbers

Choose and approve a telephony provider (Ghana number availability and audio-streaming support are unverified); build the telephony adapter (inbound/outbound, transfer, status callbacks); run recorded accuracy tests with Ghanaian-accented English, French and Hausa; fill in approved voice IDs; fill `voice_pricing` from current price lists; build auth, tenant isolation and rate limiting in the API layer; legal review of call-recording consent.
