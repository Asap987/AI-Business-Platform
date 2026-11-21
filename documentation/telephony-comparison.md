# Telephony provider comparison for KASORA AI (Ghana)

Researched 2026-11-21 from the providers' own pages. **No number has been bought and no provider is committed.**
Prices are quoted in each provider's own currency. Convert with the rate on the day you decide; none is assumed here.
"Not stated" means the page did not say, not that the feature is absent. Every figure must be re-checked on the
provider's page and with their sales team before any purchase.

## What KASORA needs from a provider
1. A Ghana (+233) number callers can dial (inbound).
2. Real-time two-way audio to our server (WebSocket media stream), because the voice pipeline is streaming speech in and out.
3. Transfer of a live call to a human number or extension, with the provider confirming the outcome.
4. Outbound calling (callbacks), SIP, enough simultaneous calls, per-minute prices that fit the plans.

## Findings
| | Twilio | Telnyx | Africa's Talking | Arkesel | Plivo |
|---|---|---|---|---|---|
| Ghana inbound number | Mobile number **$27.00/month** | Local numbers **from $30/month** | Regular or toll-free: **GHS 500 + 15% VAT setup, GHS 300 + 15% VAT/month** | Not stated | Not stated |
| Inbound per minute | **$0.1355** (mobile number) | Not stated for Ghana (rate sheet needed) | **GHS 0.009** (looks very low, verify); toll-free GHS 0.20 | Not stated | **Not supported** |
| Outbound per minute | **$0.4915** (to Ghana); **$0.5318** to Ghana mobile | Not stated for Ghana | **GHS 0.20** | **GHS 0.15**, but for voice broadcasts to answered calls | $0.4210 |
| Real-time audio to our server | Page not checked in this research (Twilio Media Streams exist; confirm price and Ghana support) | **Media streaming over WebSockets: $0.0035/min** | **Not stated** (only Say/Play of hosted audio) | Not stated | Not checked |
| Call transfer | Not checked here (standard Dial feature; confirm) | **$0.10 per invocation** | "Send a caller to another phone number or agent" (no price stated) | Not stated | Not checked |
| SIP | Not checked here | SIP trunking from about $0.0032/min inbound, $0.005/min outbound (calculator figures), plus $0.002/min | SIP agent outgoing GHS 0.03/min; SIP trunk rates not stated for Ghana | Not stated | Not checked |
| Buying requirements | Business only; Ghana business registration certificate, Ghana address, signed letter of authorization | Mobile: company registration certificate; National: letter of intent and proof of address under 3 months old | Not stated; "bring your own carrier" is offered | Not stated | Not stated |
| Lead time | Not stated | Not stated | Not stated | Not stated | Not stated |
| Fit for an AI receptionist | Likely technical fit, highest per-minute cost | Likely technical fit (streaming and transfer priced); Ghana per-minute rate unknown | Cheapest stated Ghana rates; real-time audio unconfirmed | Outbound broadcast only. Not a fit | Inbound unsupported. Not a fit |

Arkesel's page also lists "Call Centre & IVR" and "Developer APIs" without describing them; ask them whether they offer inbound calls with real-time audio.

## Illustrative monthly cost for 1,000 inbound minutes (number plus calls only)
- **Twilio:** $27.00 + 1,000 x $0.1355 = **$162.50**, before any media-stream, transfer or outbound callback charges.
- **Africa's Talking:** GHS 300 + 15% VAT = GHS 345 for the number, plus 1,000 x GHS 0.009 = GHS 9; about **GHS 354** (one-off setup GHS 575 with VAT). If the GHS 0.009 rate is right, calls are almost free; the number rental dominates.
- **Telnyx:** at least $30 for the number, plus streaming 1,000 x $0.0035 = $3.50, plus $0.10 per transfer; **inbound call charge unknown**, so no total can honestly be given yet.
- Not included for any option: OpenAI and ElevenLabs usage (priced separately; operator supplies those rates in settings), VAT/taxes on foreign providers, bank fees, exchange rate.

## Recommendation (not an approval request yet)
1. **Do not choose on price alone.** The decisive requirement is real-time two-way audio plus confirmed transfers. Of the five, only Telnyx (priced) and Twilio (known feature, unchecked here) clearly offer it; Africa's Talking must confirm in writing.
2. **Before spending anything**, send three questions:
   - Telnyx: the Ghana inbound and outbound per-minute rates, and lead time for a Ghana number.
   - Africa's Talking: does Voice support bidirectional real-time audio (WebSocket) with an external AI service? Is GHS 0.009/min inbound correct?
   - Twilio: the Media Streams price and lead time for a Ghana mobile number.
3. **Likely shortlist:** Telnyx or Twilio for the first live pilot (technically safest); Africa's Talking if it confirms streaming, because it could be the cheapest for Ghanaian callers.
4. **Pilot plan, no Ghana number needed first:** use a provider trial or a single low-cost number to prove the audio path and transfer outcome; only then request Ghana business documents (registration certificate, authorization letter) for a +233 number.
5. **Integration stays provider-independent:** KASORA will define one telephony interface (answer call, stream audio in and out, transfer, hang up, report outcome) and keep each provider in its own adapter, so changing provider does not touch the call logic. A transfer is reported successful only when the provider confirms it.

## Decision needed from you before any spend
Approve one provider for a **pilot** and its monthly cap, after the three answers above come back. Until then nothing is bought.

## Sources
- Twilio Ghana voice pricing: https://www.twilio.com/en-us/voice/pricing/gh (page says current as of October 2026)
- Twilio Ghana number requirements: https://www.twilio.com/en-us/guidelines/gh/regulatory
- Telnyx voice API pricing: https://telnyx.com/pricing/voice-api
- Telnyx Ghana numbers: https://telnyx.com/phone-numbers/ghana
- Telnyx Ghana requirements: https://support.telnyx.com/en/articles/5466525-ghana-did-requirements
- Africa's Talking voice: https://africastalking.com/voice and https://africastalking.com/pricing
- Arkesel voice: https://arkesel.com/voice-sms/
- Plivo Ghana: https://www.plivo.com/voice/pricing/gh/
