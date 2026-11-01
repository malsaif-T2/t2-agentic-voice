# Evaluation: measuring speech-to-text on your own voices

How a team measures speech-to-text on the voices it serves, with the library's evaluation
helpers: what each helper takes and gives back, how to record a golden set with every speaker's
consent and keep its audio out of git, how to write the spelling guide its references follow,
how to make a registered run and read its scorecard, and how to tell a real change from noise
with the sign test. The method itself, from the golden set to the run history, is
[evaluation.md](../design/evaluation.md); this page applies it with the library, and with Ole5's
golden-set commands as the worked example.

**Status: provisional.** The two modules on this page, `t2_agentic_voice.languages` and
`t2_agentic_voice.evals`, are provisional (D-021): either may change in any minor release, with
the change in the changelog. They landed with M1 (plan 002), whose runs are this page's
examples. Every number from those runs describes one speaker, Ole5's owner (D-006).

## What the library gives you, and what stays yours

- **The library** holds the scorers (D-022): text normalization and the spelling-guide check in
  `t2_agentic_voice.languages`; the error rates, the recall counts, text from silence and the
  sign test in `t2_agentic_voice.evals`. Each is a function of what it is given alone: no key,
  no file and no network.
- **Your repository** holds your golden set and the commands around it: the items and their
  references, the manifests of the recordings, the split, the runner and the run history (the
  design's 9.7). The library publishes no golden data, and a `t2v eval` command comes when a
  second team records a golden set (D-022).
- **A worked example** is Ole5's golden set, built in this repository on the same public API:
  its code in [ole5_voice/evals/](../../apps/ole5-voice-agent/src/ole5_voice/evals/), its data
  in `apps/ole5-voice-agent/evals/`, its tests in
  [tests/ole5_voice/evals/](../../tests/ole5_voice/evals/), and its commands `poe golden`,
  `poe record`, `poe eval`, `poe eval-compare` and `poe eval-history` (below, "The commands").
  It is Ole5's own code, not the library's API: copy what fits your set.

## The evaluation helpers

An app imports each name from the module in its row, never from the layers inside the library
(ARCH-PUBLIC); [test_facades.py](../../tests/t2_agentic_voice/test_facades.py) holds each
module's names.

| Name | Module | What it gives |
| --- | --- | --- |
| `normalize_arabic(text)` | `languages` | `text` in one canonical form for comparison: no diacritics and no tatweel; the alef, hamza, teh marbuta and alef maksura forms folded; Latin letters in lower case; punctuation, symbols, emoji and an underscore read as spaces (`Outlook.PDF` is two words); runs of space made one |
| `normalize_digits(text)` | `languages` | `text` with every digit as 0 to 9: Arabic-Indic and Persian digits, and digits spelled out one word each, in Arabic or in English; a run of single digits with only spaces between them becomes one number (`4 5 2 1` reads `4521`) |
| `spelling_issues(reference, rules)` | `languages` | A `SpellingIssue` (`rule`, `found`, `write`) for each spelling one of your `SpellingRule`s avoids that `reference` holds, however often, as a whole word or phrase, both compared after `normalize_arabic` (so a spelling with an Arabic prefix written onto it, such as ال or و, is not found); empty when it follows them all |
| `wer(references, outputs)` | `evals` | The word error rate, pair by pair and pooled: substitutions, deletions and insertions over all the references' words, both sides normalized |
| `cer(references, outputs)` | `evals` | The character error rate, pooled as `wer` is, with every space removed first, so a word split differently is not counted twice |
| `term_recall(reference, output, terms)` | `evals` | A `Recall`: of the `terms` (your product terms) that `reference` holds, how many `output` holds too, each as a whole word or phrase, both texts normalized |
| `id_recall(reference, output)` | `evals` | A `Recall`: of the IDs `reference` holds (its runs of digits in the scored form: `normalize_arabic`, then `normalize_digits`), how many `output` holds too, as a run of digits or as words made only of digits next to each other, with no other word between them, whose digits joined in order are the ID. Every punctuation mark reads as a space, so `48 21`, `48-21`, `4,821`, `48.21` and `48/21` all hold 4821, while `21 48` does not, and neither does `t48 21` or `و48 21`, since a group with a letter written onto it joins no neighbour. An ID the reference holds twice is found as often as the output holds it, up to that; found is the most IDs one reading of the output finds, no digit of the output counting for two, so never fewer than comparing whole runs gives |
| `silence_output(output)` | `evals` | How much text a provider produced where nothing was said (silence, a noise, or only the agent's own echo): the characters of `output` after `normalize_arabic`, spaces removed, so a digit's name counts its letters; 0 when it produced none |
| `sign_test(better, worse)` | `evals` | The two-sided p-value of `better` items better and `worse` items worse, unchanged items left out (below) |

Using them:

- **Pool, then divide.** A stratum's rate (a language's, a device's) is the errors of all its
  pairs over the words, or characters, of all its references, so `wer` and `cer` take every
  pair of the stratum at once; one pair is a list of one. A `Recall` is two counts, `expected`
  and `found`: add them up over the stratum before dividing.
- **No reference, no error rate.** `wer` and `cer` raise `ValueError` when a reference is empty
  after normalization, or when the two sequences differ in length: score a clip in which
  nothing is said with `silence_output`. They and `term_recall` raise `TypeError` when given a
  bare `str` where a sequence belongs, which would otherwise be scored letter by letter.
- **What counts as right is yours.** The helpers measure; your matcher rules which outputs are
  right. Ole5's counts a variant right when its output, normalized and with every space
  removed, equals its reference, normalized the same way, or does so with its spaces removed
  before its digits are read (plan 002), and reports WER and CER beside that verdict.

## Recording your own set, with consent

Ole5's set holds one speaker, its owner (D-006); yours may hold more. For every speaker:

- **Ask first, and keep the answer with the recordings.** Before a speaker records, they agree,
  in their own words, that their recordings are used in your golden set. Record who spoke, that
  they agreed, the date and their words, in the manifest of their recordings.
- **How Ole5 keeps it.** `poe record` asks for the speaker's consent at the start of each
  session and writes it as that session's `session.json`; Ole5's import copies it into the
  manifest and refuses a session that has none.
- **Record where your callers are.** Ole5 records each new item on each device its callers
  use: the laptop's speakers and microphone, a wired headset and a Bluetooth headset (plan 002),
  as 16 kHz mono 16-bit WAV with the browser's echo cancellation, noise suppression and gain
  control on.
- **Check every take by listening.** A variant counts only once its reference and an
  independent check agree (evaluation.md, "Proven twice"). Ole5's check is its owner's listen:
  in `poe record`'s review mode the owner hears each variant beside its reference and confirms
  it, or types what it says, which becomes its reference and is confirmed again in a later
  pass. `poe golden` accepts only the variants so checked, and a run scores only those. A take
  confirmed by mistake is corrected from the review page's "Confirmed" section: typed again, its
  confirmation no longer counts, and it comes back for its own check in the next pass, as one of
  M1's takes did. Leaving a clip out is the owner's call: M1 left out two talk-over clips cut off
  at their start, whose typed text the script's list of listening sounds refuses.
- **Say how many voices.** While a set holds one voice, every number from it describes that
  voice alone, and is never reported as Saudi speakers in general (D-006). Ole5's scorecards say
  "one speaker" in a field that can hold nothing else.

A manifest with its speaker's consent, from
[test_models.py](../../tests/ole5_voice/evals/test_models.py)
(`test_a_manifest_holds_its_consent_and_files`), where `SHA` is a made-up SHA-256:

```python
manifest = Manifest.model_validate(
    {
        "root": "owner",
        "consent": {
            "speaker": "the owner",
            "agreed": True,
            "on": "2026-11-02",
            "words": "I agree to these recordings' use in this golden set.",
        },
        "files": [
            {
                "path": "laptop/take-01.wav",
                "sha256": SHA,
                "seconds": 2.5,
                "sample_rate": 16000,
                "device": "laptop",
                "session": "laptop-1",
            }
        ],
    }
)
```

`agreed` holds only `True`: the same test shows a record whose `agreed` is false refused as it
is read.

## Keeping audio out of git

- **Commit the manifests, never the audio.** A manifest names each audio file by its root, its
  path below that root, its SHA-256, its length, its sample rate, its device and its session
  (the sample above). A path is relative, with `/` and no `..`, and refused otherwise as it is
  read, so a manifest names no file outside its root.
- **Keep the audio under the git-ignored `var/`, or in a private store** (D-022), and name its
  folder at run time: Ole5's `poe golden --audio <root>=<folder>` checks every file's hash and
  format against its manifest.
- **Let a test fail on a stray file.** Ole5's
  [test_no_audio.py](../../tests/ole5_voice/evals/test_no_audio.py), inside `poe check`, fails when
  an audio file sits under `apps/`, `packages/`, `examples/`, `docs/` or `tests/`; and this
  repository's [.gitattributes](../../.gitattributes) marks the audio types binary, so one that
  slips in is never converted.
- **Whoever reads the repository never gets the voices.** Whatever channel the library ships
  through, the golden set's audio is never in git (the design's 15).

## Writing your own spelling guide

A reference is what a clip says, written one way. The same words can be written in several
ways (a product term in Arabic or in Latin script, a number in digits or in words), and a
reference written one way against an output written the other counts as an error nobody made.
A spelling guide settles each such choice once, before the references are written.

- **Rule once, as data.** Each ruling names the spellings a reference must not use and what to
  write instead, quotes the words of whoever ruled, and gives the day. The library never holds a
  team's guide: `spelling_issues` takes the rulings you pass, as `SpellingRule`s.
- **Leave the letter forms to the normalizer.** What `normalize_arabic` and `normalize_digits`
  fold (the table above) needs no ruling, since both sides are normalized before they are
  compared. A ruling covers what normalization cannot decide, such as the script a product term
  is written in.
- **Check every reference whenever the set changes.** Ole5's `poe golden` names every
  reference that breaks its guide.

A ruling as a team writes it, from
[test_rulings.py](../../tests/t2_agentic_voice/domain/test_rulings.py) (`RULING`):

```python
RULING = {
    "id": "product-term-outlook",
    "avoid": ["اوتلوك", "أوتلوك"],
    "write": "Outlook",
    "said": "Use these rules",
    "on": "2026-11-01",
}
```

`SpellingRule.model_validate(RULING)` reads it. A ruling is refused when its `id` is not a
lower-case name, when it avoids no spelling, quotes no one or gives a date that is no date, or
when it holds a field the model does not know (the same file).

**Ole5's guide, as an example:** [spelling.toml](../../apps/ole5-voice-agent/evals/spelling.toml).
Its owner chose its rules on 2026-11-01 ("Use these rules", plan 002's Q8):

- both texts are normalized before they are compared: the Arabic letter forms folded as the
  prototype did, no diacritics and no tatweel, Arabic-Indic digits read as 0 to 9, English in
  lower case, punctuation ignored, and spaces ignored in the verdict, so two words written as
  one still count;
- product terms are written in Latin script, as the product writes them (Outlook, PDF, Word);
- numbers are written as digits, and digits said one by one count as those digits;
- English contractions are written as said;
- listening sounds come from a fixed list that comes with the script.

## The commands

Ole5's golden-set commands are this repository's poe tasks, run as `uv run poe <task>`. Each runs
a module of the app's [ole5_voice/evals/](../../apps/ole5-voice-agent/src/ole5_voice/evals/)
with `python -m`, passes on the arguments after the task's name, and prints its flags with
`--help` (GP-17).

| Command | What it does |
| --- | --- |
| `poe golden` | Validates every item and freezes the expected answers into `frozen.json`; with `--audio <root>=<folder>` it also reads every audio file of that root and checks its hash and format against its manifest; `--check` fails when `frozen.json` is stale |
| `poe record` | Serves the recorder on 127.0.0.1: each speaker's consent, the takes on each device, and the review mode in which every variant is checked |
| `poe eval` | Runs an answerer over one split into a new `--out` folder: `reference` gives each variant its own reference and sends nothing, `groq` asks Groq's Whisper |
| `poe eval-compare A B` | Judges run B against run A, the baseline, each given as its `--out` folder or its `scorecard.json` |
| `poe eval-history` | Renders the run history into [eval-history.md](../generated/eval-history.md) |

Two steps have no task: `python -m ole5_voice.evals.split` writes the held-out split (`--check`
only checks it), and `python -m ole5_voice.evals.import_recordings --takes <folder>` turns the
recorder's takes into items and manifests, reading no audio. Inside `poe check`, tests fail when
the committed split or the frozen answers are stale, and the `reference` answerer must score
100%.

## Making a registered run

A run that spends money or judges a change is registered first: the plan that measures holds a
section `## The measurement, registered before any result`, with the arms, the data, the metric,
the keep and reject rule, the cost and a budget cap the owner approves, all written before any
run (evaluation.md, "Registering a measurement"). Then:

1. **Put the change behind a setting.** The arms of a comparison run one commit and differ only
   in what their command lines set (evaluation.md, "Variants behind settings" and "Same
   conditions"). `poe eval` takes the model (`--model`), the timeout (`--timeout-s`), Groq's
   address (`--base-url`) and the language hint (`--language-hint`) on its command line, and
   records the settings it shows in the run's scorecard and history line. A change behind
   another setting is measured once `poe eval` takes that setting as a flag too, and shows it,
   at the measurement commit: until then a run's settings do not say which arm it was.
   `eval-compare` refuses two runs whose commits, data digests or splits differ, and lists any
   other setting that differs without refusing (TD-026).
2. **The measurement commit and its worktree.** The commit that holds the code and data every
   arm runs on is the measurement commit. Make a linked worktree at it (`git worktree add`):
   every run of the measurement starts there, whatever the main branch gains meanwhile.
   `poe eval` refuses the main checkout and a worktree with changes (`git status` not empty).
   M1's measurement commit was 1c3c4dc, and all 13 of its runs were made in one worktree there.
3. **Name every flag.** Every run needs `--answerer`, `--split`, `--out` and `--note`, and a
   `groq` run also `--model`, `--timeout-s`, `--price-per-hour` and `--cap-usd`; a run missing
   one is refused before anything is sent.

   | Flag | What it sets |
   | --- | --- |
   | `--answerer` | `groq`, or `reference`, which sends nothing |
   | `--split` | `dev` or `held-out`: a run covers one split, all of it |
   | `--model` | `stt.model`: `whisper-large-v3` or `whisper-large-v3-turbo` |
   | `--timeout-s` | `stt.timeout_s`, in seconds |
   | `--base-url` | Groq's address; left out, the SDK's own `https://api.groq.com`, whatever the environment or the env file holds |
   | `--language-hint` | the language sent: `label`, unless given, sends the item's label's (`ar`, or `en` for English); `auto` sends none |
   | `--price-per-hour` | USD an hour of billed audio, for the cost and the cap |
   | `--cap-usd` | the most this run may spend |
   | `--max-rpm`, `--max-attempts`, `--variant-timeout-s` | requests a minute, the attempts of each request, and each variant's limit in seconds: 20, 4 and 120 unless given |
   | `--audio <root>=<folder>` | the folder of each audio root the manifests name, once per root |
   | `--env-file` | the `.env` the settings load from, the key among them; never printed |
   | `--out` | a new folder outside the worktree that git ignores (under the main checkout's `var/`, or outside the repository); its name, lowercase letters, digits, `.`, `_` or `-`, is the run's |
   | `--note` | why the run is made, kept in its history line |

   M1's runs gave `--timeout-s 6`, `--price-per-hour 0.111` for large-v3 and `0.04` for turbo,
   `--max-rpm 10` (the owner's call: something else might use the key), `--max-attempts 4`,
   `--variant-timeout-s 120`, the `label` hint, both audio roots (`talkover` and `owner`), and
   an `--out` under the main checkout's `var/runs/` named after the run, such as `r1-large-v3`.
4. **`--show-settings` first.** The run's whole command line with `--show-settings` added sends
   nothing: it logs each setting as the run would use it (a secret only as `set` or `not set`),
   the worktree (`ready`, or why it is refused), each data and audio path (`exists` or
   `missing`) and the `--out` folder (`new`, or why it is refused). With R1's command line it
   showed every setting as registered, the key set, the worktree ready, both audio roots found
   and the `--out` folder new.
5. **The smoke test.** Every run first sends one dev variant, a held-out run's too, so that it
   reads no held-out answer. It must pass with no failed, retried or refused request; otherwise
   the run stops there, incomplete. `--smoke-only` sends it alone: M1's tracing check, run P,
   was one, traced with `--tracing-endpoint` (dev runs only) to a Phoenix listening on
   127.0.0.1 only (`Get-NetTCPConnection -LocalPort <port> -State Listen` shows the address).
   A Phoenix listening on every interface lets anyone on the same network read its traces, with
   no login; M1 found the prototype's Phoenix listening so, and ran its own on other ports.
6. **The cap.** Before each request a `groq` run is charged what Groq bills for it, at least
   10 s of audio a request at `--price-per-hour`, and a request that would take the run past
   `--cap-usd` is never sent: the run ends there, incomplete. The plan's cap covers all its runs
   together, so before each run the spend so far (the history's) plus the run's estimate is
   compared with the cap, and the run is given what is left: M1's cap was $5, R1 was given
   `--cap-usd 4.9996` after run P, and the 13 runs spent $0.3645 in all.
7. **While it runs.** Nothing else runs on the machine
   ([working rules](../../WORKING-RULES.md), "Measurement runs"). Each variant's result is
   written as it finishes (a dev run's `results.jsonl`), with a progress line of identifiers,
   verdicts and timings, never a transcript, so an interrupted dev run keeps what it measured.
   `poe eval` exits 0 when the run is complete, 1 when it is not (a failed smoke test, the cap,
   an interrupt) and 2 when it was refused before anything was sent.
8. **Carry the history line over.** A run that called a provider appends its line to the
   worktree's `apps/ole5-voice-agent/evals/history.jsonl` and copies it beside its scorecard.
   The line goes to the main branch in its own commit, with `poe eval-history` run in the same
   commit (GP-11); then the run worktree's file is reset
   (`git checkout -- apps/ole5-voice-agent/evals/history.jsonl`), so the next run starts clean at
   the measurement commit. M1 carried each of its 13 lines so (`Plan 002: history, run R1` and
   the like).

## Reading a scorecard

A run writes `scorecard.json` into its `--out` folder, labelled `"speakers": "one speaker"`:

- `run`: the run's name, commit, answerer, model and split, its settings as `--show-settings`
  shows them, the price, the data digest (over the run's variants, the split and the spelling
  guide), the note, and whether it was traced.
- `complete`: false after a failed smoke test, the cap or an interrupt.
- `totals`, and `breakdowns` by `language`, `device`, `kind` and `split`, each with the same
  numbers:
  - `right` and `accuracy`: the verdict, the share of the judged variants whose output matches
    the reference (above, "What counts as right is yours");
  - `wer` and `cer`, pooled over the variants whose reference is not empty;
  - `term_recall` and `id_recall`, pooled over the variants with a product term and those of
    the `ticket_number` kind;
  - `silence_share` and `silence_chars`: the share of the variants with an empty reference
    (silence, a noise, the agent's own echo) that produced any text, and the characters they
    produced;
  - `failures`, `requests`, `retries`, the latency per answered request (`latency_median_ms`,
    `latency_p90_ms`), `billed_seconds` and `cost_usd`.

  A rate is `null` where nothing counts: the `none` language holds the empty-reference items, so
  it has no WER and is read by its text from silence. Every rate leaves out the infrastructure
  failures.
- `windows`: a window run's measures (below, "Window runs").
- `violations`: 0, with the reason: no hard constraint applies to speech-to-text.
- `variants`: in a dev run, each variant's result: its item, language, device and kind, its
  reference, the answer (its text; Whisper's `language`, `confidence` and `no_speech_prob`; each
  request's attempt, latency, billed seconds and outcome; any failure) and the verdict. A
  held-out scorecard holds none (below, "Held-out runs").

M1's R1, large-v3 on dev (231 variants of 66 items): 99 right (0.429), WER 0.250, CER 0.103,
term recall 0.333, ID recall 0.571, and text from every one of the 9 empty-reference variants
(silence share 1.0). By language: English 0.847, Saudi 0.370, MSA 0.256, mixed 0.050. A
scorecard's requests, billed seconds and cost leave out the smoke test, while its history line's
billed seconds and cost are the run's whole spend: R1's scorecard says 236 requests, 2,427.5 s
and $0.0748, its history line 2,437.5 s and $0.0752.

## Noise and the sign test

A hosted model need not give the same answer twice, and a seed does not make it repeatable
(evaluation.md, "Noise"), so two runs may differ even when nothing changed. How much they differ
is measured, never assumed. Two steps tell a real change from that noise.

**1. Measure the noise first.** Before judging any change, run the same code twice on the same
set, compare the two runs variant by variant, and count the verdicts that changed and the items
they moved. From that count comes the smallest change one run can detect. Record both as a
decision and as a tech-debt row: "one run is one sample; repeated runs are the lasting fix"
(evaluation.md).

M1 ran each model twice on dev with the same code, R1 and R3 for large-v3 and R2 and R4 for
turbo: in each pair no variant of the 231 changed its verdict and none of the 66 items moved
(p = 1.0), and the transcripts were the same for every variant under large-v3 and for 230 of
231 under turbo.
So the noise moved d = 0 items, and one run detects a change of 6 items (D-024). Those pairs were
made on one evening with one key, and another day may differ (TD-032).

**2. Judge by item, with the sign test.** Compare the candidate's run with the last kept run
variant by variant (fixed, broken, net), then count each item, by its net over its variants,
as better, worse or unchanged: the item is the unit, since its variants move together. With
`b` items better and `w` worse:

p = min(1, 2 · Σ_{i ≤ min(b, w)} C(b + w, i) / 2^(b + w))

`sign_test(b, w)` gives p, and p < 0.05 is beyond the noise (evaluation.md, "Judging a
change"). Worked from the formula:

| Better (b) | Worse (w) | p |
| --- | --- | --- |
| 6 | 0 | 2/64 = 0.03125 |
| 5 | 0 | 2/32 = 0.0625 |
| any | the same as b | 1 |

So with no noise at all, the smallest gain one run can show is six items better and none worse.
With noise, it takes more: in Ole5's rule (plan 002's registration), the smallest change one
run can detect is the smallest number c of items that, added on one side to the d items the
noise changed, split evenly (b = c + ⌊d/2⌋, w = ⌈d/2⌉), gives p < 0.05.

Ole5 takes both steps with `poe eval-compare A B`, on two runs of the same code for the noise
and on a candidate against the last kept run for a change: fixed, broken and net per variant,
the sign test by item, provider failures left out of both runs and listed, and held-out runs
compared by aggregates only.

### Reading `eval-compare`

`poe eval-compare A B` prints a Markdown report of B judged against A:

- **The header:** both runs, their commit and data digest, and a line "Settings that differ".
  Two runs whose commits, data digests or splits differ are refused, the difference named. Any
  other setting that differs is only listed (TD-026), so that line says whether the runs differ
  in their arm alone: in M1's model comparisons, only `stt.model` and `run.cap_usd` differed.
- **Variant by variant:** fixed (wrong in A, right in B), broken (right in A, wrong in B), the
  net and the unchanged, each fixed and broken variant named by its ID, and the variants left
  out of both runs (a failure in either, or in one run only), listed.
- **The sign test by item:** the items better, worse and unchanged by their net, and p; below
  0.05 is beyond the noise.
- **The noise line:** for two runs of the same code, the items the noise changed and the
  smallest change one run can detect. Between two arms it measures nothing: for turbo against
  large-v3 it says 13 items.
- **The stratum guard:** the same sign test for each language, over its items with each item's
  net over all its variants, and for each device, over the items with a variant on that device
  with each item's net over those variants only. A value with fewer than 6 changed items cannot
  reach p < 0.05 and reads "too small to guard"; any other reads "within the noise", or "worse
  in B beyond the noise" or "better in B beyond the noise".
- **The aggregates:** each run's totals and accuracy by stratum value, side by side, with B - A.
- **`--focus FILE`:** the items a change aims at, one item ID a line, written before B ran, are
  shown apart; the verdict is still every item's.

M1's baseline, R2 (turbo) judged against R1 (large-v3): 231 variants compared, 6 fixed and 35
broken (net -29); 2 items better, 18 worse and 46 unchanged, p = 0.0004, beyond the noise. The
guard read turbo worse beyond the noise on Saudi Arabic (2 better, 12 worse, p = 0.0129), the
laptop (3 and 16, p = 0.0044) and the wired headset (1 and 8, p = 0.0391), and every other value
too small to guard. R4 against R3 gave the same. By the registered rule, `stt.model` stays
`whisper-large-v3` (D-025). A model change reaches every clip, so no slice was left untouched to
check first (evaluation.md, "Check an untouched slice first"): the identical runs of each model
took its place.

## Held-out runs

Held-out measures; it never chooses a change, and tuning uses dev alone (evaluation.md,
"Splits"). In Ole5:

- **A held-out run covers its whole split, untraced.** `poe eval --split held-out` refuses
  `--questions`, `--smoke-only` and `--tracing-endpoint`. Its progress lines hold counts only,
  it writes no `results.jsonl` and its scorecard holds no variant; one that does not finish keeps
  no result and is run again whole.
- **Groups of fewer than 3 items are pooled.** Wherever a held-out run's numbers are broken down
  (its scorecard's breakdowns and window groups, its history line, the rendered history and
  `eval-compare`), every value that covers fewer than 3 answered items is pooled into one group,
  `other`, itself left out when it too covers fewer than 3. Items are counted, not variants, and
  an item whose every variant failed is not counted.
- **Rates over fewer than 3 items are left out.** In a group shown, and in the totals, a rate
  taken over fewer than 3 items is left out: WER and CER, term recall, ID recall, text from
  silence, and a window group's one-word clips. A rate left out reads `null`, and
  `silence_chars` then reads 0.
- **Compared by aggregates only.** `eval-compare` of two held-out runs names no variant and no
  item, and shows a stratum value only where both runs hold it over the same number of items,
  at least 3, with no failure; it refuses two held-out runs that cover different numbers of
  variants, and `--focus`.
- **Read as written.** A held-out scorecard or history line holding a smaller group is refused
  as it is read, and no kind may be named `other`. The rule limits what is shown, not what can
  be worked out: a left-out `other` group's counts are the totals minus the values shown
  (TD-029).
- **Capped by the plan.** The plan caps how many held-out runs a milestone makes, so that it
  does not pick changes by held-out noise (evaluation.md, "Splits"): M1 made two, H1 and H2, once
  each, after every dev run.

M1's held-out runs, 106 variants of 29 items: large-v3 (H1) 41 right (0.387), WER 0.266, CER
0.127, term recall 0.722; turbo (H2) 22 right (0.208), WER 0.397, CER 0.221, term recall 0.611.
ID recall and text from silence were left out of both, each taken over fewer than 3 held-out
items. The kinds of fewer than 3 items were pooled as `other` (6 items), and the `none`
language's 2 items, pooled into an `other` of 2, were left out. Held-out agrees with dev:
large-v3 0.387 against turbo 0.208, as 0.429 against 0.303 on dev.

## Window runs

A window run measures what the first part of each clip lets a model hear, the data M3 chooses
its window from.

- **`--windows-ms`** (one length or several) sends only the leading window of each talk-over
  clip of the split, cut from the start of the variant's first segment file. That file begins
  with the detector's 300 ms of padding before speech, so a 500 ms window holds about 200 ms of
  speech. A window run gives no verdict: its accuracy reads `null`, and "—" in the history.
- **What is kept.** Each window's transcript is kept in the variant's `answer.windows`, with
  whether it is empty, the words heard after normalization, how many of them match the
  reference's first words in order, and, for a reference of one word, whether the window holds
  it (the matcher's call). The scorecard's `windows` sums them by length, language and the
  clip's `want` label: `clips`, `empty`, `reused`, `words`, `leading_words`, `reference_words`,
  `one_word_clips` and `holds_word`.
- **`--clips-from`** takes the same model's first dev run's `scorecard.json`, the file itself,
  not its folder. A window at least as long as its clip is then not sent again: the clip's
  answer from that scorecard is used, marked `reused`. A scorecard that is not a dev run of the
  same model at the same commit is refused; without `--clips-from`, such a window sends the
  whole clip, marked not reused. M1's first try at W1 named R1's folder, and was refused before
  anything was sent.

M1's window runs, W1 to W6: 500, 750 and 1000 ms of the 90 dev talk-over clips (33 items), each
model at each length, the models alternating; at 1000 ms, 2 clips no longer than that reused
their answers from R1 and R2. The one-word clips whose window held their word:

| Clips (how many) | large-v3 at 500, 750, 1000 ms | turbo at 500, 750, 1000 ms |
| --- | --- | --- |
| English listening sounds (5) | 5, 5, 5 | 5, 5, 5 |
| English, a word asking the agent to pause (2) | 2, 2, 2 | 1, 2, 2 |
| MSA, a one-word confirmation (2) | 2, 2, 2 | 2, 2, 2 |
| Saudi listening sounds (12) | 2, 4, 3 | 2, 0, 2 |
| Saudi, a word asking it to halt (4) | 0, 2, 2 | 0, 1, 1 |
| Saudi, a word asking it to pause (3) | 2, 3, 2 | 1, 2, 1 |

A longer window does not always hold more: large-v3 held 4 Saudi listening sounds at 750 ms and
3 at 1000 ms. A window chosen from these numbers is fitted to them, and is confirmed on a fresh
run before it is believed (evaluation.md, "Fitted, then fresh").

## The run history

- **The file.** `apps/ole5-voice-agent/evals/history.jsonl` holds one line per `poe eval` run
  that called a provider, kept or not, a failed smoke test's included; a `reference` run and a
  run refused before anything was sent append none. A line holds the time, the commit, the run's
  name, answerer, model and settings, the split, items and variants, accuracy, violations, the
  billed seconds, price and cost of the run's whole spend, the median latency, items and
  accuracy by stratum value, the scorecard's file name, the data digest, the note and whether
  the run is complete. The file is read strictly: every line a valid history line with an LF
  ending.
- **The page.** `uv run poe eval-history` renders it into
  [eval-history.md](../generated/eval-history.md): a table of the runs, each run's settings and
  strata, and the spend so far (after M1's 13 runs, 17,369.7 billed seconds and $0.3645). The
  page is never edited by hand, and a freshness test fails when it is stale (GP-11), so a line
  and the page reach the main branch in one commit.
- **The scorecards.** Full scorecards stay out of git, in each run's `--out` folder (M1's in the
  main checkout's `var/runs/`): a summary line alone cannot be compared item by item.

## The rest of the method

[evaluation.md](../design/evaluation.md) holds what this page leaves out: why a measurement is
registered before any result and why held-out is read only as aggregates, the untouched slice
checked before a run is read, screens (`poe eval --questions FILE`, dev only), failure analysis,
fitted rules confirmed on a fresh run, and closing at a plateau. Ole5's first measurement with
these helpers is plan 002.
