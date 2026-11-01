# Evaluation: measuring speech-to-text on your own voices

How a team measures speech-to-text on the voices it serves, with the library's evaluation
helpers: what each helper takes and gives back, how to record a golden set with every speaker's
consent and keep its audio out of git, how to write the spelling guide its references follow,
and how to tell a real change from noise with the sign test. The method itself, from the golden
set to the run history, is [evaluation.md](../design/evaluation.md); this page applies it with
the library.

**Status: provisional.** The two modules on this page, `t2_agentic_voice.languages` and
`t2_agentic_voice.evals`, are provisional (D-021): either may change in any minor release, with
the change in the changelog. They land with M1 (plan 002).

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
  `poe record`, `poe eval`, `poe eval-compare` and `poe eval-history`
  ([CLAUDE.md](../../CLAUDE.md)). It is Ole5's own code, not the library's API: copy what fits
  your set.

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

## Noise and the sign test

A hosted model does not give the same answer twice, and a seed does not make it repeatable
(evaluation.md, "Noise"), so two runs differ even when nothing changed. Two steps tell a real
change from that noise.

**1. Measure the noise first.** Before judging any change, run the same code twice on the same
set, compare the two runs variant by variant, and count the verdicts that changed and the items
they moved. From that count comes the smallest change one run can detect. Record both as a
decision and as a tech-debt row: "one run is one sample; repeated runs are the lasting fix"
(evaluation.md).

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

## The rest of the method

[evaluation.md](../design/evaluation.md) holds what this page leaves out: registering a
measurement before any result, the held-out split and why it is read only as aggregates, the
untouched slice checked before a run is read, screens, failure analysis, and the run history.
Ole5's first measurement with these helpers is plan 002.
