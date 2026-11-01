# T2 Agentic Voice: the guide for teammates

How to add a speech-first voice agent to your own product with T2 Agentic Voice: install the
library, declare your use case, add your tools and the actions that need a spoken yes, test it
without a microphone or a key, and run it.

**Status: nothing to install yet.** The library's public API is designed, and M1 builds its
first public modules (`ports`, `groq`, `languages`, `evals` and `tracing`): the design is
[package-design.md](../design/package-design.md) (D-017, approved as amended by D-018), and its
section 3 is the contract, what the library provides and what your app must provide. The first
version is used from Python only (D-014). Each page below is written when the part it describes
lands in the library, with the milestone named in its row ([roadmap](../plans/roadmap.md)); code
samples on these pages are taken from tested files, so a page never shows code that does not
run.

## Pages

| Page | What it will cover | Lands with |
| --- | --- | --- |
| `contract.md` | What the library provides, what you must provide, and what you may provide, with the default for each | M0 (fixed then, D-018) |
| `is-this-for-you.md` | The fit check: Python version, operating system, the heavy dependencies, one process per data folder and the sidecar, network needs (UDP or TURN), Groq's published limits, the licences | M2 |
| `quickstart.md` | `examples/minimal` end to end, English first, then Saudi Arabic; a checklist for a first call that does not work | M2 (an echo agent), M5 (the final quickstart) |
| `concepts.md` | The talker, tools, actions, turns, the two-step interruption, the cancel scope, the history of what the caller heard; one turn in a diagram | M3 |
| `writing-for-voice.md` | Instructions written for speech, tool descriptions, read-backs, claim phrases, send words and spoken labels, each with a good and a bad example | M4 |
| `tools-and-actions.md` | Writing each kind, wrapping existing functions, the action lifecycle, consent, the error table, idempotency and lookups | M5 |
| `safety.md` | How the yes rule and the output guard work; what the library guarantees and what stays yours | M5 |
| `languages.md` | Language presets, the reply language, normalization, speaking numbers and IDs, spoken labels, vocabulary, pronunciation | M4 |
| `settings.md` (generated) | Every setting, with its default, unit and environment name | M2 |
| `serving.md` | The sidecar or the mount, identity and join tokens, cross-origin pages, the browser protocol | M2 |
| `browser-client.md` | The reference browser client: its events and states, tokens, consent, Stop and Esc | M2, M3 |
| `testing.md` | Text calls, the fakes, the safety suite for your actions, live scenarios, audio replay | M5 |
| [evaluation.md](evaluation.md) | The evaluation helpers; recording your own test set with consent and keeping audio out of git; writing your own spelling guide; noise and the sign test | M1 |
| `latency.md` | Where the time goes in a turn, and how to measure yours | M4 |
| `tracing-and-logs.md` | Phoenix or your own tracing, redaction, what a trace holds, the logging policy | M2 |
| `data-and-privacy.md` | What the library itself stores and sends: what a trace holds, the data folder, recording and consent | M2 |
| `audio-troubleshooting.md` | Echo on laptop speakers, Bluetooth headsets, microphone permissions, UDP and TURN failures | M3 |
| `deployment.md` | The process model, containers, TURN, drain, health, capacity | M6 |
| `runbook.md` | Rate limits and outages, a stuck write, key rotation, a deletion request | M6 |
| `providers.md` | Writing an adapter for another speech, model or voice provider | M4 |
| `cookbook/` | Worked use cases with no Ole5 code: an IT helpdesk, HR leave | M5, M7 |
| `upgrading.md` | Versions, stability levels, deprecations, behaviour changes | The first version a teammate installs |
