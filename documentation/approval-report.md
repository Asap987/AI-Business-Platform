# Report before further financial commitments (2026-11-22)

Legend: **Implemented and tested** = automated tests pass (offline). **Simulated** = fake provider, not a real service. **Awaiting credentials / approval** = cannot proceed without you. Nothing below has run against a live provider; no number was bought and no paid service was activated.

## 1. Telephony comparison (Telnyx, Africa's Talking, Twilio) — `telephony-comparison.md`
Published pricing and requirements only; the written answers you authorised me to obtain have **not** been requested yet (I cannot contact vendors from here; the three questions are in that document).
| | Telnyx | Africa's Talking | Twilio |
|---|---|---|---|
| Ghana number | local from $30/month; needs company registration certificate (mobile) or letter of intent plus recent proof of address | GHS 500 + 15% VAT setup, GHS 300 + 15% VAT per month | mobile $27/month; Ghana business registration, local address, signed letter of authorization |
| Inbound / outbound per minute | Ghana rates not published on the pages read | GHS 0.009 inbound (looks too low, verify), GHS 0.20 outbound | $0.1355 inbound, about $0.49 to $0.53 outbound |
| Real-time AI audio | WebSocket streaming $0.0035/min | **not stated** | Media Streams exist, price not checked |
| Transfers | $0.10 per transfer; SIP trunking priced | transfer to number/agent mentioned, no price | Dial transfer (not checked in detail) |
| Recording, webhooks, concurrency, latency, regulatory lead time | not verified | not verified | not verified |

## 2. Recommendation (provisional, not an approval request)
Shortlist **Telnyx** (streaming and transfer are priced and documented, Ghana per-minute rate and lead time unknown) with **Twilio** as the safe but costlier alternative, and keep **Africa's Talking** as the cheapest option only if it confirms real-time audio in writing. Reason: a transfer or AI call is only possible with real-time audio plus provider-confirmed outcomes, which only Telnyx and Twilio clearly document. A **permanent choice should wait** for the written answers; until then no spend is needed because the call logic is provider-independent.

## 3. OpenAI and ElevenLabs readiness
| Item | Status |
|---|---|
| Keys read only from server settings (`OPENAI_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`; the old name also works); never in the frontend, logs or git | Implemented and tested |
| `POST /voice/provider-check` validates each provider (model lookup, recognition connection, speech key) before a live call, reports ok/fail and time only, audited, rate limited | Implemented and tested with fakes; **awaiting credentials** for the real result |
| `scripts/live_check.py` controlled test, double opt-in | Implemented and tested (refusal paths); **not run** |
| Error handling: provider errors become provider-neutral errors, mid-call speech failure hands over to a person | Implemented and tested |
| Usage and cost monitoring | **Partly:** per-call counts are measured and logged (characters, errors) and cost uses operator-supplied prices; **not yet stored per business or reported**. Next item. |
| Live voice behaviour (latency, barge-in on real audio, voice quality) | **Unverified** |

## 4. Resend and domain verification
- Service, templates, invitation, password reset, email verification, security notice: **implemented and tested** with fake transport (including Chromium end to end with a fake provider).
- **Nothing is sent** until `EMAIL_PROVIDER=resend`, `RESEND_API_KEY`, `EMAIL_FROM` **and `EMAIL_DOMAIN_VERIFIED=true`** are set; the last is a human step you take after Resend shows your domain verified. Until then email reports itself as off and the invite dialog tells the administrator to share the link by hand. **Email delivery is not operational.**
- Resend itself: **awaiting your domain, key and the first live send**.

## 5. Ghanaian-English speech-to-text — `stt-evaluation-protocol.md`
Methodology, scoring harness (WER, term recall with digit/word alternatives, latency percentiles) and data-protection procedure are written and tested offline. **No recordings exist, so there are no accuracy results.** Needs: consent forms, recordings, and a check of ElevenLabs' STT data-handling terms.

## 6. Provider-independent telephony and transfers
Interface, simulated provider and a transfer service are **implemented and tested** (8 tests, mutation-checked): the department is looked up inside the caller's business, only active staff with a phone are dialled (up to 3), success is reported only on provider confirmation (an unanswered or unconfirmed attempt is never a success), and the audit entry holds no names or numbers. **Simulated only.** Not built: a real provider adapter, department opening hours and extensions, AI-to-AI agent handover wiring, callback request records, and connecting the AI to the transfer tool.

## 7. Expected cost of the controlled live test (list prices read from ElevenLabs' pricing page on 2026-11-22; taxes excluded; OpenAI price not checked)
- `live_check.py`: about 40 speech characters (about $0.0016 at $0.04 per 1,000 for Flash/Turbo), a few seconds of recognition (realtime recognition $0.22 per hour, so about $0.0002), and a few hundred OpenAI tokens (cost depends on the model price, check before running). Under a few cents in total.
- Speech-to-text evaluation: audio seconds streamed multiplied by $0.22 per hour. Example: 400 recordings of 8 seconds is 3,200 seconds, about $0.20.
- Telephony: none until you approve a pilot.
Set a spending limit in each provider dashboard first.

## 8. Security, privacy and compliance concerns
1. **Provider data handling is not settled.** ElevenLabs' page says data is stored in the US by default, zero-retention mode is optional with stricter requirements, residency in the EU, India or Singapore is Enterprise-only, and it does not state default retention periods or whether speech-to-text data is used for training. OpenAI not yet reviewed. **Do not send real customer audio or records until confirmed in writing**; use synthetic or consented data.
2. Ghana Data Protection Act, 2012 (Act 843): no legal review yet; likely needs registration with the Data Protection Commission, a lawful basis, notices to callers about AI and recording, and cross-border transfer safeguards. Needs a Ghanaian lawyer.
3. Recording callers is not implemented and nothing is stored from calls; if you add recordings you need consent prompts and retention rules first.
4. Isolation is enforced in application queries, tested with two businesses and mutation checks; PostgreSQL row-level security is not used.
5. Self-registered accounts are not blocked while unverified (blocking would lock everyone out while email is off); the banner and `EMAIL_DOMAIN_VERIFIED` switch exist, enforcement can be added when email is live.
6. Secrets: stored only in server settings; if a key leaks, revoke it at the provider.

## 9. Outstanding blockers
- You: OpenAI and ElevenLabs keys as server settings; Resend domain verified and key; consented recordings; approval of any telephony pilot and its spending cap.
- Written vendor answers (telephony quotes, ElevenLabs/OpenAI retention terms). I cannot send these myself.
- Legal review.

## 10. What I am doing next without waiting
Per-business usage and cost storage with a report; department hours and a callback-request record; the Profile and Business screens; the organisation profile fields; document upload.
