# Privacy and security risk register, provider terms review and questions for written confirmation

Prepared 2026-11-22 from the providers' public pages (links at the end). This is **not legal advice**. Nothing here is a contractual guarantee: only a signed agreement or written confirmation from the provider counts. **Rule until this register is closed: no real customer audio or real customer records go to OpenAI or ElevenLabs. Use invented or consented test data only.**

## 1. What each provider says (published pages)
| Topic | OpenAI (API) | ElevenLabs (API) |
|---|---|---|
| Training on your data | Not by default; sharing data to improve models needs explicit opt-in. | **Its privacy policy says inputs and outputs may be used to "research, build, train and improve" models, with an opt-out in account settings that applies to training after opt-out.** It is not stated whether API traffic is excluded or whether the opt-out covers API use. **Unresolved, highest risk.** |
| Default retention | Abuse-monitoring logs kept up to 30 days by default. Speech-recognition endpoints (`/v1/audio/transcriptions`) keep nothing for abuse monitoring; the realtime endpoint keeps 30 days. Some endpoints keep state until deleted (files, threads, vector stores, assistants); we use none of those. | No API-specific retention period stated. Voice-derived data kept no longer than 3 years after last interaction. |
| Zero retention | Zero Data Retention and Modified Abuse Monitoring exist per organisation or project **after OpenAI's approval and extra requirements**; most chat, responses, speech and realtime endpoints are eligible. | Zero Retention Mode is optional, separately enabled, "stricter requirements", contact the account team to confirm which models support it. Whether it covers speech-to-text and the exact terms are not stated. |
| Data residency | US or Europe processing selectable for eligible API customers on supported endpoints; eligibility criteria not stated. | Stored in the US by default. EU, India, Singapore isolated environments are **Enterprise only**, and processing may still occur outside the chosen region. |
| Subprocessors | Public sub-processor list exists. | Listed on its Trust Center; the DPA gives 30 days' notice of new ones. |
| DPA | Available on request (not stated whether automatic). | DPA published: processor role, SCCs for transfers, audit via third-party report (may include SOC 2 Type II), deletion within 30 days of contract end for **Enterprise**; **self-serve customers: no deletion obligation** (may delete after 180 days of inactivity), no fixed breach-notice time. |
| Certifications | SOC 2 Type 2, ISO 27001/27017/27018/27701 listed. | SOC 2 Type II "may" be provided. |
| Minors | | Not intended for under-18s; voice data about under-18s prohibited. |

## 2. Questions that need written answers
**ElevenLabs** (send to sales/DPO; keep the replies):
1. Is audio and text sent through the API (speech-to-text and text-to-speech) used to train or improve models? Does the account "Data use" opt-out apply to API traffic? Please confirm in the agreement.
2. Is Zero Retention Mode available for speech-to-text and text-to-speech, on which plan, at what price, and what are the "stricter requirements"?
3. What is the default retention of API audio, transcripts and generated audio, and is it configurable?
4. Can we sign the DPA on a self-serve plan, and what deletion obligation applies to us before Enterprise?
5. Which subprocessors touch API audio, and where?
6. How do we ask for deletion of specific data, and how long does it take?
7. Is processing for Ghanaian users lawful under your transfer terms without Enterprise residency?

**OpenAI:**
1. Is a DPA signed and in force for our organisation, and which entity is the processor?
2. Can we get Zero Data Retention or Modified Abuse Monitoring approved, and what are the extra requirements?
3. Which regions can we select for processing, and which models support them?
4. Confirm that API data is not used for training and that the default abuse-monitoring retention for our endpoints is 30 days.

## 3. Risk register
Scale: likelihood and impact Low/Medium/High. Status: Open, Mitigated in code, Awaiting external answer.
| # | Risk | L | I | What exists now | What is still needed | Status |
|---|---|---|---|---|---|---|
| R1 | Customer speech used for provider model training | M | H | Per-business switch to turn AI providers off; no audio stored by us | Written ElevenLabs answer (Q1); opt-out or Enterprise/ZRM; consent notice to callers | Awaiting external answer |
| R2 | Provider retention longer than customers expect | H | M | Redaction of contact details in text sent to the AI (per business setting) | Written retention terms; ZDR/ZRM where eligible; retention wording in the customer notice | Open |
| R3 | Cross-border transfer (US storage) of Ghanaian personal data | H | M | None technical | Legal review of Act 843 transfer rules; DPA with transfer clauses; consider EU/Singapore residency | Open, needs a Ghanaian professional |
| R4 | One business sees another's data | L | H | Business from session on every query; two-business tests with mutation checks, also on PostgreSQL | PostgreSQL row-level security as a second lock; periodic security test; external penetration test | Mitigated in code, not independently tested |
| R5 | AI reads arbitrary data or takes unauthorised actions | L | H | AI only calls named, validated backend tools scoped to the business; no SQL; unauthorised tool names refused | Prompt-injection tests with hostile documents and callers (not yet written) | Partly mitigated |
| R6 | Prompt injection from uploaded knowledge documents | M | M | Documents are text the business enters; retrieval returns at most 3 short passages | Treat as untrusted in the prompt; adversarial tests; document upload (not built) makes this matter more | Open |
| R7 | Secrets exposed (keys in code, logs or browser) | L | H | Server-side settings only; logs hold counts and error types; tests assert keys never appear | Secret manager in production; key rotation procedure; spend limits at providers | Mitigated in code |
| R8 | Account takeover | M | H | Argon2 hashes, server sessions, rate limits, single-use expiring reset tokens, sessions revoked on reset/disable | Email verification enforcement once email is live; two-factor sign-in; new-device notices | Partly mitigated |
| R9 | Calls recorded or transcribed without caller consent | M | H | Nothing is recorded or stored from calls | Spoken AI and recording notice and consent flow before any real calls; retention controls | Open (by design nothing stored) |
| R10 | Personal data kept too long or not deletable | M | M | Customer and case data stored until someone removes it; audit log append-only | Retention schedule, deletion and export on request, backup retention | Open |
| R11 | Sensitive categories (health, children, financial) reach the AI | M | H | Contact-detail masking only | Rules and training for what staff may enter; blocking or warning rules; legal confirmation of which categories Act 843 treats as special | Open |
| R12 | Recordings for the speech test mishandled | L | M | Evaluation protocol with consent, access, deletion; `.wav` and `eval_audio/` git-ignored | Run the protocol; delete on schedule; check ElevenLabs terms before sending | Open |
| R13 | Platform administrator misuse | L | H | Platform access by explicit user-id list; totals only, no content; every platform view or price change audited | Dual control for adding platform admins; alerting on platform access | Partly mitigated |
| R14 | Provider outage or silent failure shown as working | M | M | Provider check before live calls; live voice off unless checks configured; failures counted | Alerting; fallback to human on repeated failure (hand-over exists) | Partly mitigated |
| R15 | Cost runaway | M | M | Per-call usage and cost estimates, per-business concurrent and per-minute call limits | Per-business monthly budget caps and alerts; provider-side spend limits | Partly mitigated |

## 4. Ghana Data Protection Act, 2012 (Act 843): items for a qualified Ghanaian professional
I am not giving legal conclusions. Please have these confirmed:
1. Whether KASORA (as operator) and each customer business must register with the Data Protection Commission, and who is controller and who is processor in each case.
2. Lawful basis, purpose limitation and the notice callers must hear (that an AI answers, that data goes to foreign providers, how long it is kept).
3. Rules on transferring personal data outside Ghana and what safeguards the provider agreements must contain.
4. Which categories count as special personal data and how to prevent them reaching providers; handling of children's data.
5. Security measures and breach-notification duties and timelines.
6. Data subject rights (access, correction, deletion) and the process the platform must offer.
7. Call recording and monitoring rules, and consent wording.
8. Whether the customer businesses' contracts with KASORA need a data processing agreement and what it must say.

## 5. Gate to lift before real customer data is used
Close R1, R2, R3 and R9 (written provider answers, legal review, caller notice and consent), pass an isolation and prompt-injection test pass, enforce email verification, and set provider spend limits. Until then: invented or consented test data only.

## Sources (all read 2026-11-22)
- OpenAI, Your data: https://developers.openai.com/api/docs/guides/your-data
- OpenAI, Business data privacy, security and compliance: https://openai.com/business-data/
- OpenAI sub-processor list and DPA: https://openai.com/en-US/policies/sub-processor-list/ and https://openai.com/policies/data-processing-addendum/ (found, not read in full)
- ElevenLabs privacy policy: https://elevenlabs.io/privacy
- ElevenLabs DPA: https://elevenlabs.io/nl/dpa
- ElevenLabs data residency and zero retention: https://elevenlabs.io/docs/overview/administration/data-residency
