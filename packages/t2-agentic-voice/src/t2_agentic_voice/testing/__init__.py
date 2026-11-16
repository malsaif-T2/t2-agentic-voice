"""testing: what a team tests and measures its voice agent with: calls held in text
(`TextCall`) and replayed from audio (`AudioCall`, the turn and echo timings) on the real
session, the fake chat models and knowledge base, the adversarial suite of an action
(`ActionSafetySuite`), the scorers (word and character error rates, on jiwer), and what every
app's measurement runs that spend share: the paced, capped chat model and its spend, the day's
requests of one key over every app's run history, and the checks before a run. Public through
the `evals` facade.

It sits beside api, above voice: it may import voice and every layer below it, but never
adapters (it reaches a provider only through a port a test passes in) and never api, so a team's
tests need no HTTP stack (harness.toml [layers], D-019); it is the only layer that may import
jiwer. ARCHITECTURE.md's "Layers" maps the layers and what each owns; each module's docstring
says what it holds.
"""
