# Quality by layer

How good each part of the code is, measured the same way every time, so a round of cleanup can
see where it matters and whether it worked ([PRINCIPLES](PRINCIPLES.md), section 5).

`uv run poe quality` grades each layer of the package (the layers in `harness.toml`), each app as
one unit (`[[apps]]`), and `scripts/`, after a test run (`uv run poe check` writes the coverage
data it reads). A module that holds only its docstring counts in neither the size nor the
docstring share, and a layer with no other module is graded `empty`. It is not a gate.

| Signal | Measures | Weight |
| --- | --- | --- |
| Coverage | the share of the layer's statements the tests run | 40 |
| Size | the share of its modules within the size watch (below the hard limit `poe arch` enforces) | 20 |
| Suppressions | `noqa`, `type: ignore`, and `pragma: no cover` per 1,000 lines; 10 or more scores zero | 15 |
| Duplication | the pairs of places that repeat a run of code (`poe gc`'s detector) and touch the layer, per 1,000 lines; 10 or more scores zero | 15 |
| Docstrings | the share of its modules that say what they are for | 10 |

The weights and the two zero points are set in `harness.toml` (`[quality]`), and the size watch
is `[gc] size_watch`; the duplicate runs are those of `[gc] min_tokens` tokens or more, so a
recalibration of either moves the grades. A run copied in three places is three pairs, and a
pair between two units counts in both. The score is out of 100. Without coverage data, it is
out of the other signals. A grade is A from 90, B from 80, C from 70, and D below. The command
lives in `scripts/quality.py`. Every [garbage-collection round](garbage-collection.md) updates
the table below and writes each unit's gaps in words: a number shows where to look, and only a
reader knows why.

## Grades

`uv run poe gc` compares the current grades with the rows of this table, so keep each row's
first four cells in this shape: `| layer | **A** | score | coverage |`, with the letter in bold.

Graded by garbage collection round 2 (plan 008) on 2026-11-13: `uv run --offline poe quality`
at 556d255, the merge of the round's six blocks and its close, right after `uv run --offline
poe check`'s tests passed on the same code (7899 passed and 1 skipped; coverage 99.32%; its lint
step failed on one docstring line, rewrapped in 556d255 before the grading). The table is the
command's output as it printed it; its size column is the share within `[gc] size_watch` (300),
and its duplication column the pairs of places per 1,000 of the unit's lines (round 2's scale:
plan 008's decision log). Round 1's grades (2026-11-02) are in
[plan 004](../plans/completed/004-garbage-collection-1.md).

| Layer | Grade | Score | Coverage | Modules within 300 lines | Largest | Suppressions per 1,000 lines | Duplicate pairs (per 1,000 lines) | Docstrings |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| core | **B** | 90 | 100% | 94% | 392 `config.py` | 0.9 | 24 (5.3) | 100% |
| domain | **A** | 92 | 100% | 93% | 375 `yes_rule.py` | 0.2 | 23 (3.9) | 100% |
| adapters | **B** | 86 | 98% | 85% | 342 `groq_client.py` | 0.8 | 22 (6.2) | 100% |
| actions | **B** | 89 | 98% | 85% | 378 `action_job.py` | 0.4 | 10 (4.3) | 100% |
| agent | **A** | 95 | 100% | 83% | 344 `turn.py` | 0.0 | 2 (0.9) | 100% |
| voice | **A** | 91 | 99% | 77% | 395 `read_back.py` | 0.4 | 24 (2.4) | 100% |
| testing | **B** | 81 | 99% | 79% | 346 `text_call.py` | 0.0 | 76 (16.8) | 100% |
| api | **A** | 91 | 99% | 73% | 366 `protocol.py` | 0.7 | 4 (1.4) | 100% |
| ole5_voice | **B** | 81 | 99% | 81% | 395 `runs.py` | 0.3 | 457 (18.0) | 100% |
| minimal_example | **A** | 95 | 100% | 100% | 147 `callback.py` | 0.0 | 1 (3.5) | 100% |
| scripts | **A** | 96 | 97% | 92% | 358 `harness_arch.py` | 0.2 | 3 (0.7) | 100% |

## Gaps

Each unit's gaps in words, as garbage collection round 2 read them (plan 008); the next round
refreshes them. A gap the grade cannot see is named by its debt row. Module sizes near the cap
are TD-140's alone. Look-alikes the round kept, so the next need not redo them, are listed in
plan 008's "Considered and kept".

- **core** (B, 90; A at round 1, when it had no repeated run and no module above the watch): two
  modules above the watch, `config.py` (392, TD-140) and `tracing_tts.py` (351). Its 24 pairs are
  mostly kept look-alikes: `identity.py`'s signed consent beside `seal.py`'s sealed model (D-032),
  and the call report's models (`call_report.py`) that the Ole5 evals' scorers project into their
  counts; a 62-token run that `config.py` shares with `domain/declaration_errors.py` and one shared
  by `settings/server.py` and `settings/tracing.py` were not read this round. What the grade does
  not see: the variables the SDKs read whatever is passed (TD-003, TD-005) with no test recording
  them (TD-038), the clients' trust in the environment's proxy and CA (TD-004, TD-015), and the
  private provider's worker in a forked child (TD-014).
- **domain** (A, 92): `yes_rule.py` (375), `declaration.py` and `interruptions.py` above the watch.
  Its pairs are ports restated by their implementations (the outbox, the action jobs' `run`) and
  `consent_check.py` beside `uncertain_overlaps.py` (43 tokens, not read). The text rules' known
  limits are debt (TD-008, TD-009, TD-031, TD-035); the lifecycle's table lacks four endings of a
  read-back (TD-150).
- **adapters** (B, 86): three modules above the watch, the largest `groq_client.py` (342). Its
  longest runs are the two language classifiers' look-alikes (`ecapa_language.py`,
  `silero_language.py`), kept since their models' inputs differ, and the outbox's port signature.
  Also debt: the stores on a file error (TD-065's three open parts), the language form Whisper
  returns (TD-011) and the first request's platform detection (TD-012).
- **actions** (B, 89): `action_job.py` (378, TD-140) and `tools.py` above the watch. Its pairs: the
  outbox's port signature in both stores, the action jobs' `run`, and a 65-token run within
  `tools.py` (lines 210 and 260), not read. `x_groq.error` is still never read (TD-125).
- **agent** (A, 95): `turn.py` (344, from 386 with `clause_gate.py`) and `context.py` above the
  watch; 2 pairs, one within `talker.py`'s two factories. No suppression.
- **voice** (A, 91): twelve modules above the watch, after the round split six of them; the largest
  is `voice/session/read_back.py` (395), which keeps the receipt (`[[restricted]]`), and
  `interrupter.py` (376) is near the cap (TD-140). Its 24 pairs (2.4 per 1,000 lines) are runs the
  transport bridges share (`session_bridge.py`, `stt_bridge.py`, `transport.py`) and one between
  `open_reply.py` and `speaker.py`, not read. Debt: TD-055 and TD-104 (the stop path's wording),
  TD-087 (`peerLeft` unnamed).
- **testing** (B, 81): its duplication scores zero, 16.8 pairs per 1,000 lines: most are the safety
  suite's case scripts (`action_safety.py`), kept since each case scripts its own answers, and the
  rest runs the app's evals share with `timed_speech.py` and `turns.py`. Five modules above the
  watch, the largest `text_call.py` (346, from 396 with `text_side.py`'s driver). Debt: TD-117,
  TD-148, TD-149.
- **api** (A, 91): four modules above the watch, the largest `protocol.py` (366); 4 pairs, a run
  three times within `router.py` among them, not read. The package root still exports `Status` and
  `status` beyond the design's 5.1, which the owner kept on 2026-11-13 (TD-034).
- **ole5_voice** (B, 81): its duplication scores zero, 18.0 pairs per 1,000 lines, 457 of the
  repository's 603: the evals' run, card, line and history modules (`history_measures.py`, `eot.py`,
  `timing.py`, `talker_lines.py`, `scenario_run.py` the most often), whose per-run parts the round
  kept as look-alikes after E1 to E6 made the shared ones one (plan 008). 22 modules above the
  watch, `evals/runs.py` (395) and `evals/recorder_state.py` (380) near the cap (TD-140). Also debt:
  TD-021, TD-022 and TD-029.
- **minimal_example** (A, 95): the quickstart's agents; its one pair is a run its `__main__.py`
  shares with the Ole5 app's `server.py`.
- **scripts** (A, 96): measured but outside the coverage floor (`[tool.coverage.report] omit`), at
  97%. Its 3 pairs are the look-alikes round 1 kept (`arch_module.py` and `arch_public.py`;
  `harness_toml.py`'s two readers; `gc_due.py` and `gc_report.py`). ARCH-DEPS matches a namespace
  package on its top-level name (TD-036).
