# Speech-to-text evaluation protocol (ElevenLabs first, alternatives only if needed)

Status: **framework built and tested offline; no recordings exist yet, so no accuracy result exists.** Do not quote any accuracy figure for Ghanaian English until this has been run.

## What is measured (`backend/scripts/stt_eval.py`)
Word error rate against human-verified reference text, business-term recall, seconds from end of speech to the final transcript (median, 95th percentile), language codes returned, per category:
`ghanaian_english` (different speaking styles and regions), `business_terms` (places, products, staff and department names), `numbers_dates`, `prices`, `quantities`, `english_with_local_expressions`, `phone_8k_upsampled` (real phone-quality audio), `noisy`.
Numbers, dates and prices can be written as digits or words, so list accepted forms in the manifest `terms` column as `20/twenty`. WER counts a digit-versus-word difference as an error, so compare WER only between runs with the same reference style, and rely on term recall for numbers.
Consistency: run each file twice and compare; large differences mean the result is unstable.

## Recordings: consent and protection
1. **Consent:** every speaker signs a short written consent saying: the recordings are used only for this speech-recognition test, are sent to ElevenLabs for processing, will be deleted by a stated date, and the speaker may withdraw before then. Keep the signed forms separately from the audio.
2. **Minimise:** scripted sentences, invented names and numbers, no real customer or staff details, no national ID, bank or health information. Name files `speaker07_utt012.wav`, never with real names.
3. **Access:** a named person or two holds the files on an encrypted drive or private folder; not in git (the repo ignores `*.wav` in `eval_audio/`), not in chat, not on shared drives.
4. **No reuse:** not used to train or tune anything, not shared with other projects or vendors, not used for demos.
5. **Provider terms:** before the run, read and record ElevenLabs' current data-handling terms for the speech-to-text API (retention, training use, zero-retention eligibility) and note the date in this file. Not yet checked; do not send consented audio until this is done.
6. **Retention and deletion:** audio is deleted within 30 days of the final report (or the consent form's date, whichever is sooner); the report contains transcripts, so it is kept private and deleted with the audio unless the speakers agreed otherwise. Record the deletion date here.
7. **Speaker withdrawal:** delete that speaker's files and re-run the summary without them.

## Decision rule (proposed, you can change it)
Keep ElevenLabs if, on `ghanaian_english`, average WER is at most 15%, business-term recall is at least 90%, and 95th-percentile latency is under about 1.5 s. If any category is clearly worse, test one alternative on the identical files before recommending a change. Telephone audio will usually be worse than studio audio; judge `phone_8k_upsampled` separately.

## Known limits
- Keyterm biasing (sending business words to the recogniser) is not sent yet: the request format is not confirmed against the live API.
- Telephone audio arrives as 8 kHz; the pipeline expects 16 kHz, so a real telephony adapter must resample, and that path is untested.
- Twi, Ewe and Ga are unsupported; the `english_with_local_expressions` category only shows what happens to familiar words inside English.
