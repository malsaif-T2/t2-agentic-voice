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

Graded by garbage collection round 1 (plan 004) on 2026-11-02: `uv run --offline poe quality`
at 8b85b29, whose code is that of the merge of the round's code blocks (5cbf520), right after
`uv run --offline poe check` passed (1377 tests passed and 1 skipped; the product packages'
coverage 100%). The table is the command's output as it printed it; its size column is the
share within `[gc] size_watch` (300).

| Layer | Grade | Score | Coverage | Modules within 300 lines | Largest | Suppressions per 1,000 lines | Duplicate runs | Docstrings |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| core | **A** | 98 | 100% | 100% | 254 `config.py` | 1.0 | 0 | 100% |
| domain | **A** | 98 | 100% | 100% | 134 `scoring.py` | 0.0 | 1 | 100% |
| adapters | **C** | 76 | 100% | 0% | 338 `groq_stt.py` | 0.0 | 3 | 100% |
| actions | empty | - | - | - | - | - | - | - |
| agent | empty | - | - | - | - | - | - | - |
| voice | empty | - | - | - | - | - | - | - |
| testing | **A** | 100 | 100% | 100% | 61 `scorers.py` | 0.0 | 0 | 100% |
| api | **A** | 100 | 100% | 100% | 34 `status.py` | 0.0 | 0 | 100% |
| ole5_voice | **B** | 80 | 100% | 70% | 380 `answerers.py` | 0.2 | 9 | 100% |
| minimal_example | **A** | 100 | 100% | 100% | 15 `__init__.py` | 0.0 | 0 | 100% |
| scripts | **A** | 94 | 97% | 100% | 267 `check_docs.py` | 0.3 | 3 | 100% |

## Gaps

Each unit's gaps in words, as garbage collection round 1 read them (plan 004); the next round
refreshes them. A gap the grade cannot see is named by its debt row.

- **core** (A): the one suppression is the `type: ignore[override]` on the exporter session's
  `request` (`core/tracing_export.py`). What the grade does not see: a few variables the SDKs read
  whatever is passed (TD-003, TD-005), with no test recording them (TD-038); the clients trust the
  environment's proxy and CA (TD-004 with TD-015, for the deployment's plan); and the private
  provider's worker is not restarted in a forked child (TD-014).
- **domain** (A): its one duplicate run is the speech-to-text port's `transcribe` signature,
  which `GroqSTT` restates as a protocol's implementation must (`adapters/groq_stt.py`, line
  144, and `domain/ports/speech_to_text.py`, line 73). The text rules' known limits are debt:
  presentation and format characters (TD-008), a prefix on a Latin or digit token in the recall
  scorers (TD-009), the number words `normalize_digits` does not read (TD-031), and the spelling
  check reading letters, not meaning (TD-035).
- **adapters** (C): its one module, `groq_stt.py`, is 338 lines, above the watch, so the size
  share is 0%; by the plans README's size rule, the next plan that grows it names its split. Its
  3 duplicate runs are expected: the port's signature (above), and the segment's
  `no_speech_prob` bounds, which the app's `runs.py` copies twice (lines 115 and 129) and
  `tests/ole5_voice/evals/test_library_copies.py` ties to the library's (the owner's ruling of
  2026-11-02). Also debt: the language form Whisper returns is unverified (TD-011), and the
  first request detects the platform (TD-012), both for M2.
- **actions**, **agent**, **voice**: empty, no module yet; the milestones that build them are
  in the roadmap.
- **testing** (A): `wer` and `cer` only; the testing kit (the fakes, text calls) comes later
  (D-019).
- **api** (A): one module, `status.py`; the rule that production never runs with DEBUG logs is
  checked only when `status()` is called (plan 004's inventory leaves it to M2's plan), and the
  package root exports `Status` and `status` beyond the design's 5.1 (TD-034).
- **ole5_voice** (B): 8 of its modules are above the watch: `answerers.py` 380 (split since:
  each answerer has its own module, and `answerers.py` is 80 lines, `groq_answerer.py` 291),
  `recorder_state.py` 379, `runs.py` 367, `scorecard.py` 333, `golden.py` 331,
  `run_parts.py` 324, `run.py` 315 and `import_talkover.py` 314. Its 9 duplicate runs
  appeared when the round lowered `[gc] min_tokens` to 25, after the read. Two are the
  `no_speech_prob` copies tied by test (above); the other 7 are not read yet: `Answer` and
  `SegmentAnswer`'s shared fields (`runs.py`, lines 114 and 127), three between
  `import_recordings.py` and `import_talkover.py`, `golden.py` against `recorder.py` and
  against `split.py`, and one within the `groq` answerer (`groq_answerer.py`, lines 157 and
  175, since the split). The one suppression is the `noqa: S603` on the git call in
  `worktree.py`. Its tests near the hard limit are
  `test_scorecard.py` (389), `test_recorder_security.py` (384) and `test_held_out_groups.py`
  (381). Also debt: TD-021, TD-022 and TD-029.
- **minimal_example** (A): the quickstart's two agents, the helper (the talker with one read
  tool) and the echo.
- **scripts** (A): the scripts are measured but outside the coverage floor (`[tool.coverage.report]
  omit`), at 97%. Its 3 duplicate runs are the look-alikes the round kept, whose inputs differ
  (`arch_module.py`, line 57, and `arch_public.py`, line 34; `harness_toml.py`, lines 86 and 93;
  `gc_due.py`, line 200, and `gc_report.py`, line 221). The one suppression is the
  `noqa: S603` on the git call in `gc_due.py`. ARCH-DEPS matches a namespace package on its
  top-level name (TD-036).
