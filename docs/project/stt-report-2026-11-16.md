# Speech-to-text comparison, 2026-11-16

A results report for the owner, plan 010's first pass of its speech-to-text bake-off (Phase 4),
asked for on 2026-11-16: "I want you to test them and provide me with all the information I
need to choose one over the other." Speech-to-text (STT) is the part that writes down what the
caller said; every later step (the answer, the action, the language) reads what it wrote.

## What was compared

- **Seven ways to hear a caller:** today's Whisper large-v3 on Groq with its vocabulary prompt
  (W1), and six candidates on the owner's keys: ElevenLabs Scribe v3, Speechmatics' Arabic-English
  pack (`ar_en`, enhanced), Cohere Transcribe Arabic, Nabrah's Saudi model, and HUMAIN's Arabic
  engine reached through Telnyx (`humain/realtime`). Soniox was not tested (no key). HUMAIN's own
  API was not reached: it publishes no API reference.
- **The test:** the golden set's dev split, 98 items in 292 recordings of the owner's voice (one
  speaker, D-006): Saudi Arabic, MSA, English, mixed sentences, short replies, pauses mid-request,
  ticket numbers, silence and coughs, on a laptop's microphone, a wired headset and a Bluetooth
  one. Each recording went once, as a live call sends a finished turn (one request), with the
  call's language named, from this laptop in Riyadh.
- **The measures:** *right*, the turn heard right by the golden set's rule; *WER* and *CER*, the
  share of words and of characters written wrong (lower is better); *terms*, the product terms
  caught (Ole5, OTP and the like); *IDs*, ticket numbers' digits caught; *text from silence*,
  characters written for silence, a cough or noise; *time*, each request's time from this laptop
  (median and the slowest 10%); *cost*, at the rate each run was given.
- **Sources:** each run's line in [the run history](../generated/eval-history.md) (from
  `apps/ole5-voice-agent/evals/history.jsonl`), by its name: `b0-groq`, `el-dev`, `sm-dev`,
  `co-dev`, `nb-dev`, `tx-dev`. The first three ran at commit `dc9c37d`, Cohere at `3d5dd4b` and
  the last two at `5a0a7a0`: the speech-to-text code is the same in all three, but the project's
  compare command refuses runs at different commits, so the item-by-item tests below for Cohere,
  Nabrah and Telnyx were computed by the same sign test outside it (for ElevenLabs and
  Speechmatics, `poe eval-compare` gave the same counts).

## Results

**Overall** (292 recordings):

| Provider and model | Right | WER | CER | Terms | IDs | Text from silence | Time, median / slowest 10% | Cost of this test |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Whisper large-v3 (Groq), today | 129 (44%) | 0.22 | 0.10 | 33% | 57% | 156 characters | **259 / 317 ms** | $0.09 |
| **ElevenLabs Scribe v3** | **209 (72%)** | **0.11** | 0.06 | **90%** | **90%** | 10 | 514 / 669 ms | $0.08 |
| Speechmatics `ar_en` | 183 (63%) | 0.15 | **0.06** | 30% | 52% | **4** | 1,982 / 3,017 ms | $0.25 |
| Cohere Transcribe Arabic | 165 (57%) | 0.18 | 0.10 | 33% | 48% | 306 | 565 / 798 ms | $0.003 (trial) |
| Nabrah Saudi model | 141 (48%) | 0.21 | 0.10 | 17% | 19% | 30 | 1,062 / 1,525 ms | $0.38 |
| HUMAIN's engine (via Telnyx) | 137 (48%), 8 failed | 0.31 | 0.26 | 13% | 24% | 24 | 6,367 / 7,994 ms | $0.22 |

**By language** (share of recordings heard right):

| Provider | Saudi (128) | MSA (51) | English (75) | Mixed (26) | Silence and noise (12) |
| --- | --- | --- | --- | --- | --- |
| Whisper, today | 43% | 24% | 80% | 8% | 0% |
| ElevenLabs | **64%** | **73%** | **89%** | **50%** | 83% |
| Speechmatics | 57% | **73%** | 75% | 23% | **92%** |
| Cohere | 53% | 69% | 75% | 19% | 8% |
| Nabrah | 62% | 53% | 33% | 15% | 42% |
| HUMAIN via Telnyx | 51% | 49% | 56% | 8% | 57% |

**Against today's Whisper, item by item** (the sign test by item: an item is better when more of
its recordings were heard right; p below 0.05 is beyond what chance explains):

| Provider | All 98 items | Saudi | MSA | English |
| --- | --- | --- | --- | --- |
| ElevenLabs | 47 better, 7 worse, p < 0.0001 | 20 / 5, p = 0.004 | 11 / 0, p = 0.001 | 7 / 1, p = 0.07 |
| Speechmatics | 38 better, 13 worse, p = 0.0006 | 16 / 7, p = 0.09 | 12 / 0, p = 0.0005 | 3 / 5, p = 0.73 |
| Cohere | 33 better, 11 worse, p = 0.001 | 17 / 7, p = 0.06 | 11 / 1, p = 0.006 | 2 / 3, p = 1.0 |
| Nabrah | 35 better, 19 worse, p = 0.04 | 20 / 1, p < 0.0001 | 11 / 1, p = 0.006 | 0 / 16, p < 0.0001 (worse) |
| HUMAIN via Telnyx | 29 better, 23 worse, p = 0.49 | 16 / 11, p = 0.44 | 8 / 1, p = 0.04 | 1 / 10, p = 0.01 (worse) |

**The kinds a call depends on** (share heard right):

| Provider | Confirmations | Pauses mid-request | Ticket numbers | Stop words |
| --- | --- | --- | --- | --- |
| Whisper, today | 78% | 24% | 48% | 92% |
| ElevenLabs | 78% | **80%** | **81%** | **97%** |
| Speechmatics | 67% | 57% | 52% | **97%** |
| Cohere | 56% | 61% | 43% | 95% |
| Nabrah | 78% | 39% | 10% | 95% |
| HUMAIN via Telnyx | 67% | 48% | 19% | 77% |

## What each gives beyond hearing

| Provider | Tells us the language it heard | Takes our vocabulary | Streaming offered | Notes |
| --- | --- | --- | --- | --- |
| Whisper (Groq) | yes, when told none (no score) | a prompt (W1) | no | the fastest here; the language switch uses its detection (D-103) |
| ElevenLabs | **yes, with a probability** | yes (keyterms) | yes (Scribe v3 Live) | the same account has voices for the voice bake-off |
| Speechmatics | no | yes | yes | its EU region; batch is too slow for a live turn |
| Cohere | no | no | no | trial key: 5 requests a minute |
| Nabrah | no | yes (priority words) | yes | Arabic only; the same key has Saudi voices |
| HUMAIN via Telnyx | no (a confidence only) | no | only streaming | the same Telnyx key has Arabic voices and chat models |

## The agent's reading

*This section is the agent's reading, not a measurement.*

- **ElevenLabs Scribe v3 is the clear leader on this voice:** best or level-best in every
  language and in every kind a call depends on (pauses, ticket numbers, product terms), it
  invents almost nothing from silence, and it is the one candidate that reports the language it
  heard with a score, which the language switch can use. Its cost is time: about 255 ms more per
  turn than Whisper (514 against 259 ms at the median), most likely the trip to its servers.
  Scribe v3 Live (its streaming version) would hide most of that, since words arrive while the
  caller speaks.
- **Nabrah is the best on Saudi speech after ElevenLabs** (20 items better and 1 worse than
  Whisper), but it is Arabic only: English is much worse (33% right). It would fit an
  Arabic-only call, not ours.
- **Speechmatics** is strong on MSA and silence, but its batch mode takes about 2 s a turn; only
  its streaming mode could serve a live call.
- **Cohere** hears MSA well but writes text from silence and coughs (306 characters) and misses
  ticket numbers; its trial key's limit also makes it hard to use live.
- **HUMAIN's engine, as reached here, is not better than Whisper** overall, and worse in English.
  This reading is the weakest of all: the engine only takes streamed audio, so our turn-by-turn
  connection sends each turn at twice real time with extra silence, and that setup, not the
  engine, may cost it words. Its accuracy deserves a second look on a streaming connection; its
  time (6.4 s here) says nothing about the engine itself.
- **Whisper stays the fastest.** Every candidate trades time for accuracy.

## What is not measured yet

- **One speaker.** Every number is the owner's voice. The recording session (plan 010's 0.6) and
  testers' calls are needed before a choice holds for other callers.
- **Once each, on dev only.** The registered rule asks for two runs of each candidate and of
  Whisper, then one read of the held-out split; none was made yet.
- **ElevenLabs' language score for the switch.** Its run was stopped to free the laptop and runs
  next.
- **Flight-booking words** (city and airport names, dates, numbers of travellers): not in the
  golden set yet; the recording session adds them.
- **Soniox** (no key) and **HUMAIN's own API** (no public API reference).

## Decisions for the owner

1. **Which speech-to-text the flight agent and Ole5 use by default.** Plan 010's registered rule
   keeps a candidate only when it is better beyond the noise twice and no slower than Whisper
   plus its spread. ElevenLabs passes on accuracy, but it is about 255 ms slower a turn, so the
   rule alone keeps Whisper. The agent's recommendation: make ElevenLabs Scribe v3 the default
   once its second run and the held-out read confirm it, accepting the extra quarter second for
   now, and move to its streaming version to win the time back. Until then, every provider can be
   tried live in the dev console, one call at a time (D-104).
2. **HUMAIN directly:** send its API reference, or approve adding its Python package (a download
   and a new dependency), to test its engine on its own connection.
3. **Soniox:** a key, if you want it in the next pass.
