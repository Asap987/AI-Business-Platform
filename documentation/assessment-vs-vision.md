# KASORA AI: assessment against the product vision (Stage 1 and 2)

Written 2026-11-21 from the code on `feature/frontend-shell-and-voice-foundation`.
"Done" means implemented and tested offline. Nothing here has run against live OpenAI, ElevenLabs or a phone network.

## Architecture in one paragraph
Next.js 16 frontend, FastAPI backend, PostgreSQL (SQLite in tests). One shared database; every row carries a
`business_id` and the business always comes from the server-side session, never from the request. Provider code
(OpenAI reasoning, ElevenLabs speech) sits behind interfaces and runs only when `VOICE_LIVE_ENABLED=true` and keys are set.

## Status by vision section
| Vision section | Status |
|---|---|
| 3 Tenant isolation | **Done** for every endpoint, proven with two-business tests and mutation checks, also on PostgreSQL. Not done: database-level row security (isolation is in application queries), per-department permissions. |
| 4A Organisation profile | **Partial.** Name only (PATCH /business, backend done, screen pending). Missing: description, industry, contacts, website, branches, hours, languages, products, policies. |
| 4B Knowledge | **Partial.** Typed or pasted text documents, draft/published, ~700-character chunks, keyword search (no embeddings: none approved). Missing: PDF/DOCX/CSV/XLSX upload, versions, processing status, reprocess, conflict detection. |
| 4C Data and API connections | **Missing.** Only the gateway pattern exists (AI can call named, validated backend tools, never SQL). |
| 4D AI configuration | **Missing as a screen.** Defaults live in code and settings (voice id, language manager). No per-business assistant name, tone, voice, instructions. |
| 4E Testing environment | **Partial.** Browser voice test call (admin only). Missing: text test chat, scripted scenarios, routing/escalation tests. |
| 4F Overview dashboard | **Partial.** Cases, customers, departments counts. AI resolution rate and response time return null; no cost, integration or audit widgets. |
| 5 Departments and routing | **Partial.** Departments and employees CRUD, cases assignable. Missing: department AI agents, receptionist routing, AI-to-AI context handover (a `hand_over` hook exists in the conversation manager), AI-to-human transfer, callbacks, availability and hours. |
| 6 AI architecture | **Partial, correct shape.** OpenAI reasons; Kasora controls tools, tenancy and permissions. Prompt-injection protection for uploaded documents is not yet tested. |
| 7 Conversation quality | **Unverified.** Barge-in and streaming are built and tested with fakes only. Needs live trial. Ghanaian English is a language setting, not evaluated. |
| 8 Speech and telephony | **Voice done offline, telephony missing.** No telephony provider chosen or integrated; real transfers cannot be built or reported until one is. |
| 9 Privacy and security | **Partial.** Per-business AI on/off, contact-detail redaction, append-only audit log, hashed sessions and invites, nothing stored from calls. Missing: encryption at rest beyond the host, backups, retention controls, deletion/export, provider retention research, legal review (Ghana Data Protection Act 2012). |
| 10 Cost tracking | **Partial.** Per-call usage record with prices supplied by the operator (none hardcoded). Not stored per business, no reports. |
| 11 Audit and reporting | **Partial.** Audit covers privacy, invites, user changes (business rename now too). No conversation records, exports, or department reports. |
| 12 Delta Horta | **Not started as data.** Should be a configured business plus a scripted test conversation (transport vs storage, unverified capacity). |

## Real risks
1. Isolation relies on every query filtering by business. Tests catch regressions, but a new endpoint can forget. Mitigation: keep the two-business test and mutation check as a merge rule; consider PostgreSQL row-level security later.
2. Provider data handling is unresearched. Do not send real customer data to OpenAI or ElevenLabs until retention, training use and zero-data-retention eligibility are confirmed in writing.
3. Nothing proves voice quality or latency yet.
4. Forgot-password and emailed invites send nothing (no email provider).

## Decisions needed from you
1. **Telephony provider** (blocks section 5C and 8). Ghana number availability and per-minute price decide this. I will compare options with current pricing before you approve anything; I will not buy numbers.
2. **Live provider test:** approval plus an OpenAI key, an ElevenLabs key and a voice id as server settings.
3. **Email provider** for invites and password reset.
4. **Speech-to-text:** the current build uses ElevenLabs STT; confirm that is acceptable for Ghanaian English before a live trial.

## Proposed order (no new providers without your approval)
1. Profile and Business screens (finishing; backend done).
2. Organisation profile fields (hours, contacts, languages, policies) so the assistant has real business facts.
3. Knowledge upload for TXT/CSV/DOCX/PDF with versions and processing status (text extraction libraries only, no new AI provider).
4. AI configuration screen (name, tone, language, voice, instructions) feeding the prompt builder.
5. Text test chat plus Delta Horta scripted scenarios, with automated checks that unverified capacity is never confirmed.
6. Departments: routing rules, hours, escalation, callback requests recorded in-app (no telephony needed).
7. Usage and cost storage with per-business report.
8. Provider privacy research and retention/deletion controls.
9. Live trial, then telephony transfer once a provider is approved.
