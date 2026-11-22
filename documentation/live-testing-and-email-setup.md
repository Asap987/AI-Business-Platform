# Setup: secrets, email (Resend), live provider check, speech-recognition evaluation

Nothing in this file has been run against a live account yet: it needs your keys. Everything below is covered by offline tests
(fake providers); the first real run is yours to approve.

## 1. Where secrets go
- **Server only.** Put them in the environment of the machine that runs the backend (your host's "environment variables" screen),
  or locally in `backend/.env`. `.env` is git-ignored; `backend/.env.example` lists the names with empty values.
- Never in the frontend (`NEXT_PUBLIC_*` is public), never in git, never in chat or tickets. If a key is ever exposed, revoke it
  in the provider's dashboard and create a new one.
- Give each key the least power it needs (Resend: "sending access" only).

| Setting | Used for | Where to get it |
|---|---|---|
| `OPENAI_API_KEY` | reasoning | OpenAI dashboard, API keys |
| `ELEVENLABS_API_KEY` | speech and recognition | ElevenLabs, profile, API keys |
| `ELEVENLABS_DEFAULT_VOICE_ID` | the assistant's voice | ElevenLabs voice library (copy the voice id) |
| `EMAIL_PROVIDER=resend`, `RESEND_API_KEY`, `EMAIL_FROM`, `APP_BASE_URL` | invitations, password reset, security notices | Resend |
| `VOICE_LIVE_ENABLED=true` | turns the live browser test call on | you |
| `RUN_LIVE_PROVIDER_TESTS=true` | allows the paid scripts below | you, only while testing |

## 2. Email with Resend
1. Create a Resend account, add a **sending domain** you own (use a subdomain such as `mail.yourdomain.com`), and add the DNS records
   Resend shows (SPF and DKIM; add DMARC too). Wait until Resend shows the domain as verified.
2. Create an API key with sending access only.
3. Set `EMAIL_PROVIDER=resend`, `RESEND_API_KEY`, `EMAIL_FROM="KASORA AI <no-reply@mail.yourdomain.com>"` and `APP_BASE_URL` (the public web address; email links are built from it, never from request headers).
4. Apply `backend/migrations/0007_password_resets.sql`.
5. Restart the backend. Invite someone: the dialog says "We emailed an invitation"; if sending fails it says so and the link can still be shared by hand.

Resend plan limits seen on its pricing page (2026-11-21): Free 3,000 emails/month with a 100/day cap and 3 domains; Pro from $20/month for 50,000 emails.

What exists: invitation emails, password reset emails (single use, 60 minutes by default, token hashed in the database, all sessions
signed out on reset), and a "your password was changed" security notice. Links carry tokens in the URL fragment.
**Not built yet:** email verification for self-registered owners (invited staff are already verified because the invitation went to their address),
notifications for other security events (new device, role change), delivery tracking or bounce handling. The provider sits behind
`app/services/email/base.py`, so another provider is one new adapter file.

## 3. Live provider check (OpenAI and ElevenLabs, a few cents)
```
cd backend
RUN_LIVE_PROVIDER_TESTS=true python scripts/live_check.py --yes-this-costs-money
```
It refuses to run without both opt-ins, names missing settings (never values), then does three things: one short OpenAI reply, one
short ElevenLabs speech clip (40 characters), and that clip back through ElevenLabs recognition. It prints timings and usage counts. It sends no customer data.
Run it from a machine you trust, with a spending limit set in each provider's dashboard.
It answers: do the keys work, are the model names and message formats we wrote from documentation accepted, how fast is the first word and the first sound.
Items listed as "Unverified" in `voice-architecture.md` (the `turn_prediction` option, language code format, whether a health check is billed)
are the likely first failures; fix them from the real error, not by guessing.

## 4. Speech recognition for Ghanaian English
**Do not assume** general English accuracy applies. Measure it on recordings made for this purpose.
1. **Record** at least 50 short utterances (3 to 15 seconds) per category, from at least 8 different speakers (different regions, ages, genders), with each speaker's written consent, and no real customer data:
   - `ghanaian_english`: ordinary customer requests.
   - `business_terms`: place names (Volta, Bono, Kaneshie), products, units (tonnes), staff and department names.
   - `phone_8k_upsampled`: the same sentences played or recorded through a real phone call, saved at 8 kHz then converted to 16 kHz.
   - `noisy`: market, road or office noise.
   - Optional: Twi/Ewe/Ga words mixed into English (code-switching), only to learn what happens, since those languages are unsupported.
2. **Write the manifest** (see `backend/scripts/stt_eval_manifest.example.csv`): file, exact reference text, category, expected terms separated by `|`. Audio: mono 16-bit PCM WAV.
3. **Run** `RUN_LIVE_PROVIDER_TESTS=true python scripts/stt_eval.py --manifest ... --audio-dir ... --out report.json --yes-this-costs-money`.
   It streams the audio in real time (so latency is honest) and reports word error rate, business-term recall, seconds from end of speech to final transcript (median and 95th percentile), and language codes seen, per category.
4. **Decide with the numbers.** Suggested starting thresholds (my proposal, for you to adjust): average WER on `ghanaian_english` at or under 15%, business-term recall at or over 90%, 95th-percentile final latency under about 1.5 s. If a category is clearly worse, test one alternative provider on the same files; switch only if the gain is real.
Limits: the harness cannot yet pass business keywords (keyterm prompting) to ElevenLabs, because the exact request format has not been confirmed against the live API; ElevenLabs documents up to 50 realtime keyterms at extra cost. Once confirmed, the same files can be rerun with and without keyterms.
ElevenLabs lists accuracy tiers by language (English in its top tier) but does not publish figures for Ghanaian accents or for Twi, Ewe or Ga.
The report contains transcripts: keep it private and delete the audio when finished.

## 5. Still needs your approval or input
- Telephony pilot (see `telephony-comparison.md`): no spend until you approve one provider and a monthly cap.
- Your keys, a verified email domain, and recorded consented audio.
