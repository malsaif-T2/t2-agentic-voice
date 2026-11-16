# Evaluation

How a measurable quality of the product is measured, and how a change to it is judged.

*Adopted* ([D-011](decisions.md), approved by the owner on 2026-11-01): speech-to-text,
turn-taking, and the talker's answers vary from run to run (a hosted model, a network, timing),
and some of them are tuned.

**Where it is built.** The kit ships the method, not the tooling. In this project, plan 002
built the tooling for speech-to-text (D-022): the scorers in the library, public through its
`evals` and `languages` modules, and Ole5's golden set in the app, with its code in
`apps/ole5-voice-agent/src/ole5_voice/evals/`, its data in `apps/ole5-voice-agent/evals/` (the
`evals/` of the paths below) and its tests in `tests/ole5_voice/evals/`, inside `poe check`.
Its commands are listed under "Running" below, and the guide's
[evaluation.md](../guide/evaluation.md) shows a team how to score its own set with the library
and measure a change with the commands. The later plans built the rest, in the same folders:
end of turn and the timing of an echo call (plan 003), the overlap replay over a reply (plan
005), the talker's runs K0, K and S, run U and the time to first audio, run T (plan 006), and
run A of the agent's actions and run H of each turn's language (plan 007); "Running" below
lists them.

## In this project

What is measured, and on what:

- **Speech-to-text:** word and character errors after Arabic normalization, recall of product
  terms and ticket numbers, and text produced from silence or from the agent's own echo; by
  language (Saudi Arabic, MSA, English, mixed) and by device (laptop speakers and microphone,
  wired headset, Bluetooth headset).
- **Turn-taking:** how often the agent replies while the user is only pausing, false and missed
  interruptions, and the time from a stop word to silence.
- **The talker and the backend:** simulated calls, each scenario repeated: the right answer,
  the right tool with the right values, the right ticket, the reply language.
- **Latency:** from the end of the user's speech to the first useful audio, by step.
- **The hard constraint:** calls in which the agent claims an action that did not happen
  ([SECURITY.md](../SECURITY.md), invariant 2). It must be zero in every run.

**Items and splits here.** An item is one scripted utterance or one call scenario; its
variants are its recordings on each device and in each session. The held-out split keeps every
recording of an item on one side (by item, as under Splits) and, where the item set allows,
also holds out whole recording sessions; if both cannot hold, which wins is the owner's call
before the first run, and for speech-to-text the owner ruled that the item wins (plan 002, Q10).
For an audio clip the reference is its transcript under the spelling guide; for a simulated
call, the expected tool calls and ticket fields. What serves as the independent check for each
is fixed in the first measurement plan's registration: for speech-to-text, the owner's listen to
every variant in `poe record`'s review mode (plan 002, Q9).

**One speaker, for Phase 0.** The only voice available is the owner's (D-006): new recordings on
each device, plus the 124 talk-over segments recorded for the prototype in October 2026
(D-011). While that holds, every result describes that one voice and is never reported as Saudi
speakers in general.

Each rule is tagged by where it applies: **[any]** any measured quality; **[noisy]** results
that vary between identical runs (a hosted model, a network, timing); **[tuned]** something is
adjusted to the results (prompts, weights, heuristics, thresholds).

## Build the measurement first [any]

The golden set and its runner are built *before* the feature they measure, and proven by a
reference answerer before the real system exists. Every later change to the feature is judged
by its scorecard: accuracy, the hard-constraint metric below, cost, latency, and breakdowns by
stratum.

## The golden set [any]

An **item** is one case the product must handle. Suggested layout: items as TOML files in
`evals/golden/`, their frozen expected answers in one JSON file beside that folder, and the
tooling in the app's own package (in this project, `ole5_voice.evals`). Each item says:

- its id, its split (dev or held-out), and **tags**: the strata it belongs to (domain, outcome
  kind, difficulty), which validation checks are honest;
- its **variants**: the same case asked in other words, formats, or languages. Variants of one
  item move together, so the item, not the variant, is the independent unit;
- **notes** that say what the item *tests*, never what the data holds (notes are not checked,
  so data facts in them go stale);
- a **reference** solution, and an independent **check** solution written another way;
- **canaries**, when the product has a hard constraint (below).

**Proven twice.** The reference and the check must agree before an item is accepted.
`poe golden` validates every item and freezes the expected answers; changing an item means
running it again and reviewing the diff of the frozen answers like code. Inside `poe check`, a
`reference` answerer, which returns each item's reference solution, must score 100% with zero
violations: the harness checking itself.

**What counts as right** lives in one matcher module: tolerances for numbers, whether order
matters, which parts of an answer are optional. Each ruling on an edge case cites the owner's
words and their date.

**Writing items:**
- realistic: in the user's words, never the system's internal names;
- unambiguous: the period, unit, rounding, and tie rule are stated or implied by the data;
- small answers, so a mismatch is easy to read;
- difficulty measures the reasoning needed, not the length of the input;
- strata in fixed proportions, which a test enforces.

## Hard constraints [any]

If the product has an invariant (no data the user may not see, no unsafe action, no personal
data in output), it is counted apart from accuracy and must be zero in every run, whatever the
accuracy. **Canaries** make it measurable: values the system must never output for an item.
Validation checks that each canary exists in the underlying data and is absent from the
expected answer. A run with any violation fails.

## Splits [tuned]

- About 30% of the items are **held out**, stratified by the strata above, and split by item, so
  all variants of an item land on one side. The split is deterministic (a salted order), made
  by a script with a `--check` mode, and a test fails when the committed split is stale.
- **Tune on dev only.** Held-out measures; it is never used to choose a change.
- **Held-out is read only as aggregates.** A run that includes held-out items writes a scorecard
  without per-item verdicts or outputs, and is never traced, so no one reads a held-out answer
  item by item. Nor is a held-out group shown that covers too few items: wherever a held-out
  run's numbers are broken down (by stratum, by window group, in the history and in a
  comparison), every group of fewer answered items than the plan registers (3 in plan 002),
  counted as items rather than variants and without an item whose every variant failed, is
  pooled into one group, `other`, itself left out when it too is that small. Within a group
  shown, a rate taken over fewer items (WER and CER, term and ID recall, text from silence, a
  window group's one-word clips) is left out, and so is such a rate of the totals, which cover
  every item. A
  comparison sets two runs' groups side by side only where both cover the same items with no
  failure, and refuses two held-out runs that cover different variants. A held-out run is made
  only at a milestone's checkpoints, and the plan caps how many times, so the milestone does not
  pick changes by held-out noise.
- **Learning on dev.** When something is learned or auto-tuned from dev results, cut dev into
  committed *learn* and *check* halves (by item, stratified), learn on one and measure on the
  other only. A screen rule scales down with the smaller set.

## No item in the product [tuned]

Prompts, examples, and code are written for a pattern, in their own words, never copied from
an item, dev or held-out. A pasted item makes the dev score measure memory and hides the
overfitting held-out exists to show. A test fails if any item's text or reference solution
appears in a package's source (with a self-test proving the search finds pasted text). If items share
fixtures with the product's tests, the product also names no distinctive identifier from those
fixtures, since held-out cannot catch tuning to the data's own names.

## Noise [noisy]

Measure the noise before tuning anything: run the same code twice and count the verdicts that
change. From that, derive the smallest change one run can detect, and record both as a decision
and a tech-debt row ("one run is one sample; repeated runs are the lasting fix"). A seed does
not make a hosted model repeatable.

## Judging a change [noisy]

- **Paired, against the last kept run.** `poe eval-compare A B` compares two scorecards
  variant by variant: fixed, broken, and net. Its verdict is a two-sided **sign test by item**:
  each item's net over its variants counts it as better, worse, or unchanged; with `b` better
  and `w` worse items, `p = min(1, 2 · Σ_{i ≤ min(b, w)} C(b + w, i) / 2^(b + w))`.
  p < 0.05 is beyond the noise.
- **Same conditions.** A candidate is compared only with a baseline run at the same commit,
  settings, and data, each run alone on the machine ([working rules](../../WORKING-RULES.md)).
- **Check an untouched slice first.** Before reading a run, look at a slice the change cannot
  affect (a stratum, a language, a feature it never reaches). If that slice moved beyond the
  noise, the run is unreliable: say so, and do not read its other differences.
- **Focus, but judge the whole.** A change aimed at a kind of failure names its target items
  before its run (`--focus`), and they are shown apart. The verdict is still every item's net:
  items chosen for failing in the last run come right by noise alone (regression to the mean),
  while the rest go wrong more often.
- **Infrastructure failures are not answers.** A case the provider turns away (rate limit,
  server error, lost connection) waits and is asked again, so the score does not depend on the
  number of workers. One still turned away after every wait is marked a provider failure, left
  out of both runs in a comparison, and listed.
- **Held-out runs** are compared by aggregates only.

## Registering a measurement [any]

A plan that measures has a section `## The measurement, registered before any result`
([plans README](../plans/README.md)), written before any run:
- the arms, each at one commit, each run alone, with its exact settings;
- the data or subset, and the metric;
- the keep and reject rule, and the expected outcomes with their sizes;
- the cost and time; a run that spends money is put to the owner, with its estimate and a
  budget cap, before it starts;
- every open question, marked "the owner's call before the run", settled before the run.

An amendment is dated and made before the result it affects. Any departure from the protocol is
logged as a `Deviation:` line in the progress log.

## Screens [noisy] [tuned]

When a full run is expensive, screen ideas first:
- **The screen set:** the stable failures (wrong in two runs of the same code; a failure in one
  run is noise), plus an equal number of stable-right controls drawn in proportion to the
  strata, committed as a file (`evals/screens/<name>.txt`, one `item/variant` per line, blank
  lines and `#` comments skipped) that `poe eval --questions FILE` reads.
- **A plain rerun** at the same commit on the screen set measures how many failures recover by
  chance.
- **The rule, fixed before any screen runs:** a net of at least +k against the rerun, with at
  most m controls broken beyond the rerun's, where k and m follow from the set's size and the
  measured noise. Only ideas that pass go to a full run. Whether an idea fixed what it targets
  is read as a check, not a gate.

## Failure analysis [noisy]

Analyze before improving. Take the stable failures only, build a dossier per failure, and label
each from a fixed list of root causes, with evidence. A label that excuses the system (a wrong
reference, an ambiguous item, a matcher too strict) counts only after a skeptic, an agent told to
refute it, fails to; a critic re-judges a sample of the rest. The next change is chosen by the
size of the cause it fixes, not from a list of techniques.

## Fitted, then fresh [tuned]

A rule fitted on recorded results (a selection rule, a threshold) is in-sample: confirm it on a
fresh run before believing it. Scorecards keep every per-item intermediate needed to re-score
such rules offline, without running the system again.

## Variants behind settings [any]

New behavior that changes a measured outcome lands behind a setting, whatever its result, and a
characterization test proves the default path unchanged. The default changes only on a
registered measurement: a gain beyond the noise and no harm elsewhere. One exception: a
reliability fix whose mechanism is measured directly (the failure it fixes falls) is kept when
accuracy shows no harm beyond the noise.

## Run history [any]

Every run appends one summary line to a committed `evals/history.jsonl` (LF endings): the time;
the commit, with `+` when the tree was dirty; the answerer and its model or settings; the split;
items and variants; accuracy; violations; cost; median latency; the breakdowns; the scorecard's
file name; a digest of any config or data the run depended on; and a note saying *why* the run
was made. A generated doc renders it (see [generated](../generated/README.md)), with its
freshness test. Full scorecards stay in the git-ignored `var/`. Every attempt is recorded,
kept or not.

## Running [any]

A measurement run is a script, not a sequence typed by hand:
- it refuses the main checkout, and needs a clean linked worktree;
- it pins every setting and data path on the command line (environment variables override
  `.env`, which may point elsewhere), and checks the resolved paths without printing `.env`;
- it runs a one-item smoke test first, which must pass with no failed, retried, or refused
  calls before any spend;
- it writes per-item results as they finish, with a progress line per item and a wall-clock
  limit per item (a stuck item scores as an infrastructure failure), so an interrupted run
  keeps what it measured;
- it copies its scorecards out of the worktree before the worktree is removed.

The [working rules](../../WORKING-RULES.md) cover the machine: runs alone, history lines
committed apart from candidate code.

**Where the commands live, in this project.** The commands are this repository's poe tasks,
defined in the root `pyproject.toml` and listed in [CLAUDE.md](../../CLAUDE.md). Each runs a
module of the Ole5 app's evaluation package, `ole5_voice.evals`
(`apps/ole5-voice-agent/src/ole5_voice/evals/`), with `python -m`, and passes on the arguments
given after the task's name:
- `uv run poe golden` (`golden.py`) validates every item and freezes the expected answers into
  `evals/frozen.json`; with `--audio <root>=<folder>` it also checks every audio file's hash and
  format against its manifest, and `--check` fails when the frozen answers are stale;
- `uv run poe record` (`recorder.py`) records the new takes, each speaker's consent first, on a
  page served on 127.0.0.1, and its review mode is where the owner confirms each variant, the
  independent check;
- `uv run poe eval` (`run.py`) is the run this section describes: it refuses the main checkout
  and a dirty tree, writes its scorecard into a new `--out` folder outside the worktree, which
  git ignores, so no copy is needed, and, when it called a provider, appends its line to
  `evals/history.jsonl` (a `reference` run, which sends nothing, appends none);
- `uv run poe eval-compare A B` (`compare.py`) judges run B against run A, as "Judging a change"
  says;
- `uv run poe eval` also runs plan 007's run H's H2 (D-086): `--language-hint en` sends every
  variant as English (baseline (c), as `ar` sends every one as Arabic), and `--language-from
  <H1 pass>` (`language_arms.py`) sends each variant whole in the language the pass's rule named
  for its first turn in the call language the hint names (`label`, `ar` or `en`), refusing a
  pass at another commit, on other data or with no classifier; with `--language-base <run>`, the
  baseline of that call language, a dev run sends only the variants whose language the rule
  changed and takes every other answer from the baseline, unsent, and is read against it with
  `poe eval-compare BASE ARM --allow-setting run.language_from`;
- `uv run poe eval-history` (`history.py`) renders `evals/history.jsonl` into the generated
  [eval-history.md](../generated/eval-history.md);
- `uv run poe eot` (`eot.py`) measures end of turn on the paused requests with the reference
  answerer or the file-fed pipeline, appending an end-of-turn line for a pipeline run;
- `uv run poe eval-timing` (`timing.py`) times each step of an echo call and appends a timing
  line; it refuses any `stt.live_language` but `session`, as a run of `poe overlap` does;
- `uv run poe eval-languages` (`languages_run.py`) is plan 007's run H's H1: every checked
  variant of a split through the file-fed pipeline at real-time pace, with no spend, Ole5's two
  languages and a speech-to-text that answers at once, `--classifier off`, `silero` or `ecapa`
  at the registered rule (`stt.classifier_from_s` 2.0, `stt.classifier_min_share` 0.7, 2
  threads; others refused), the classifier's files in `--classifier-dir`; or `--classifier
  groq`, `elevenlabs` or `soniox`, a speech-to-text provider's own language (D-100,
  `provider_language.py`): each classified turn's first 2 s sent to it with no language named,
  its language and score (ElevenLabs') read as the turn's scores, a score below an even share
  leaving the turn unsure rather than handing it to the other language, which spends, so it takes
  `--price-per-hour` and `--cap-usd`, logs the most it can send and cost before any clip and
  stops there with `--estimate-only` (no key needed), its line recording its price and what it
  sent at the most; each turn's
  classification, decision and end kept in the pass's `turns.jsonl` (a held-out pass's whole,
  once complete, never shown by variant), its scorecard by `languages_score.py`, and a
  languages line appended (it refuses the main checkout; `--smoke-only` feeds one dev variant
  and appends none); `--read <passes>` logs condition 4 for each classifier pass against the
  two off passes, writing nothing;
- `uv run poe overlap` (`overlap.py`) replays the overlap clips over a reply (plan 005's arm O)
  with the reference answerer, which scores every verdict right and 0 ms inside `poe check`, or
  the file-fed pipeline's `AudioCall`, which spends, paced at 10 Whisper requests a minute and
  held under its cap, appending an overlap line for a pipeline run. A run of the pipeline plays
  its smoke test first (the plan's smoke variant over a reply, a dev variant even for held-out,
  as `poe eval`'s) and stops before any further spend if it failed, was retried or refused; a
  clip whose last attempt is still rate-limited stops the run as `rate_limited`, its scorecard
  and history line written as at the cap, rather than being scored as the rule's verdict; and a
  variant whose deciding request failed is an infrastructure failure, not an answer: counted
  apart and left out of the rates, in dev and in held-out aggregates;
- `uv run poe knowledge-depth` (`knowledge_depth.py`) is plan 006's run K0, the passages' depth:
  each answerable dev variant's raw words searched once in the knowledge base with a limit of 8
  and no chat model, the share of expected points found at each k and the k kept, appending a
  knowledge-depth line (dev only; refuses the main checkout);
- `uv run poe eval-talker` (`talker_run.py`) is plan 006's run K: one arm of the talker over
  one split of the knowledge set, each variant one text call with the real model and knowledge
  base, judged, paced under the key's limits and its cap, a stopped dev run resumed with
  `--resume`, appending a talker line each session (it spends; refuses the main checkout);
- `uv run poe eval-talker-compare A B` (`talker_compare.py`) judges two dev runs of K by item,
  with the variants whose verdict differs between an arm's two runs counted as its noise;
- `uv run poe eval-talker-keep` (`talker_keep.py`) applies K's keep rule to each arm's two dev
  runs, reading the model's own time to the first clause (the tools' time taken out) beside the
  wall clock's;
- `uv run poe judge-check` (`judge_check.py`) draws 24 judged answers of a dev run of K for the
  owner's check of the judge, or reads the filled sheet back;
- `uv run poe eval-scenarios` (`scenario_run.py`) is run S: the scripted calls with the kept arm,
  each played three times and checked turn by turn, appending a scenario line each session (it
  spends; refuses the main checkout);
- `uv run poe eval-actions` (`action_run.py`) is plan 007's run A: the scripted calls in which
  the agent acts, over one split, each played three times against the mock ticket system and
  checked turn by turn, one violation of the hard constraint (no unrecorded claim, no action
  without a yes) failing the run, in any play, the smoke test's and one with no result included
  (a stuck play checked on the turns said before it stuck), appending an action line each
  session (it spends, refused past its cap by a dry estimate; refuses the main checkout, and a
  held-out run unless named, or once one is complete);
- `uv run poe uncertain` (`uncertain.py`) is run U: a model's verdict on the overlaps the rule
  left uncertain in a stored dev overlap run, against the rule's, appending an uncertain line (it
  spends);
- `uv run poe first-audio` (`first_audio.py`) is run T: the recorded requests replayed through
  `AudioCall` as calls of the agent, its time to first audio by path, appending a first-audio
  line (it spends). With `--clause-cache on` (off by default; dev only) it is plan 007's run I:
  `tts.cache_clauses` on, the clause cache new in the run's folder (`<out>/clauses`) over the
  replay's counting voice, cleared once the smoke call has passed so the first measured call
  starts cold; each call's look-ups counted, a recording replayed after a rate limit apart and
  left out of the shares; and the scorecard and the line holding the hits in each item's first
  variant and in the rest, each look-up's time, the requests per call minute with and without
  the hits, the takes, and the keep rule's first four conditions (`first_audio_cache.py`, D-087);
- `uv run poe first-audio-listen` (`first_audio_listen.py`) writes ten of a T1 run's reply
  openings and a sheet for the owner's listen, or reads the marked sheet back.

The split has no task: `python -m ole5_voice.evals.split` writes it (with `--keep`, new items
placed and every committed item keeping its side), and a test inside `poe check` fails when the
committed split is stale. Nor do the calls' manifests:
`python -m ole5_voice.evals.call_manifests` writes each recorded call's manifest under
`evals/calls/`, and `python -m ole5_voice.evals.import_calls` imports the overlaps of the
recorded calls the owner labelled as items (the labels in `evals/calls/labels.toml`, an overlap
the owner left out named there with why), checking each call's alignment first (TD-070). The scores these commands give come from
the library's scorers, imported from its public `t2_agentic_voice.evals` facade (and the
normalizers from `t2_agentic_voice.languages`), never from its layers (ARCH-PUBLIC, D-021,
D-022). A team with its own golden set writes its own commands around the same scorers, as the
guide's [evaluation.md](../guide/evaluation.md) shows.

## Closing at a plateau [tuned]

When an iteration no longer beats the last one beyond the noise: report the plateau with its
numbers, write the remaining ideas into the plan as `## Future improvements` ordered by
expected value (with a pointer from the roadmap's "Planned later"), run held-out once for the
report, and close the milestone instead of tuning further.

## External benchmarks [noisy]

If the project adopts a public benchmark: read its numbers with their caveats (the model may
have seen the benchmark in training; the gold answers have errors; a dev set is not a
leaderboard's test set). Its dev and test sets only measure; tuning happens on its training
set. A corrected ("accepted") score may sit beside the official one, never replace it: its
corrections are frozen before any new run, come from adversarially checked labels, and cut both
ways (an answer that matched a wrong gold counts as wrong).
