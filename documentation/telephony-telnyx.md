# Telnyx adapter (transfers only) — status and setup

Written 2026-11-27 from Telnyx's public documentation. **Never run against a Telnyx account. No call has been placed, no number bought, no credential used.** Everything is OFF by default and the assistant keeps telling callers transfers are simulated until all switches below are on.

## What exists
- `app/services/telephony/telnyx.py`: `TelnyxTelephony` implements the provider-independent `TelephonyProvider` interface.
  - Sends `POST https://api.telnyx.com/v2/calls/{call_control_id}/actions/transfer` (bearer key, `to`, `timeout_secs`, `command_id` as idempotency key, `client_state` and `target_leg_client_state` carrying a per-attempt marker, optional `from`, extension as `send_digits_on_answer`).
  - HTTP 200 only means Telnyx accepted the command. **Confirmed only when a signed `call.bridged` event carrying the attempt marker arrives.** `call.hangup` with the marker means no answer / busy / failed. No final event in time = unconfirmed (never success). `call.answered` alone is not success.
  - A 4xx reply = failed (not accepted). A network error or 5xx = unconfirmed (it may have been accepted).
  - Numbers must be E.164 and extensions digits, `*` or `#`; otherwise the attempt fails before anything is sent.
- `app/api/v1/telephony_webhooks.py`: `POST /api/v1/telephony/telnyx/webhook`. 404 unless live telephony is fully configured. Rejects (400) anything without a valid Ed25519 signature over `{timestamp}|{raw body}` or older than 5 minutes; 413 over 64 KB. Only events for attempts this system started are acted on; nothing is stored or logged. Duplicate event ids are ignored.
- `app/services/telephony/factory.py`: returns the simulator unless **all** of the following are set.

| Setting | Purpose |
|---|---|
| `TELEPHONY_PROVIDER=telnyx` | choose the adapter |
| `TELEPHONY_LIVE_APPROVED=true` | deliberate second switch, set only after written approval |
| `TELNYX_API_KEY` | server-side secret; never in chat, frontend, logs or Git |
| `TELNYX_PUBLIC_KEY` | base64 key from the Telnyx portal, verifies webhooks |
| `TELNYX_FROM_NUMBER` (optional) | caller ID; must be a number the account owns |
| `TELNYX_TRANSFER_TIMEOUT_SECONDS` (optional, 5–60, default 25) | ring time |

## What is NOT built
- Answering inbound calls, streaming call audio to speech services (`tel.audio`), buying numbers (`tel.numbers`), outbound calling. The transfer needs a live inbound call to exist first, so **real transfers cannot happen yet**.
- Shared state across several server processes: the event registry is in-memory, so run one worker, or move it to a shared store (e.g. Redis) first.
- A business-level setting for the caller ID / switchboard number.

## Unverified assumptions (check on a Telnyx test account before relying on them)
1. Webhook signature format (`timestamp|body`, base64 key) comes from Telnyx's SDK docs and a third-party guide; confirm with a real event.
2. That `target_leg_client_state` appears as `client_state` on events for the new leg, and which leg's `call.bridged` we receive.
3. The `hangup_cause` names (`timeout`, `user_busy`, ...). Unknown causes are treated as failed, which is the safe direction.
4. Whether Telnyx can provide a Ghana number and carry transfers to Ghanaian mobiles: still needs written confirmation (see `telephony-comparison.md`).

## Steps for the owner (nothing here is done by Claude)
1. Decide and approve the provider in writing; create the Telnyx account yourself and complete any identity or business checks.
2. Put the API key in the server environment only. Copy the public key from the portal into `TELNYX_PUBLIC_KEY`.
3. Point the Call Control application's webhook URL at `https://<your-api-host>/api/v1/telephony/telnyx/webhook`.
4. Before any real call: confirm consent and call-recording rules and complete the Ghanaian legal and data-protection review; record this in `privacy-risk-register.md`.
5. Only then set `TELEPHONY_LIVE_APPROVED=true`, and test with your own phones first.

## Desktop software
The transfer target is any phone number, so a staff softphone on Windows or Mac could be an endpoint later (for example through Telnyx's WebRTC/SIP clients). That is separate work from packaging KASORA AI itself as a desktop app, and neither is started.
