"""The pieces of a `poe eval` run (`run.py`): the `Parts` it is built from, each replaceable by
a test's fake; its `Plan`, the golden set's checked variants of its split (those the owner has
confirmed, as `poe golden` accepts them), each with the request its answerer is handed and its
audio checked against its manifest's hash, the smoke test's variant,
and the digest of the data, so `eval-compare` refuses runs on other data; the clip answers a
windows run takes from the same model's first dev run (`--clips-from`); and its `Progress`, the
results kept as each variant finishes.

Every refusal comes before anything is sent, and names counts and audio roots, never a variant,
so a held-out run's refusal says nothing of its items. A held-out run's progress lines are counts
only; a dev run's carry identifiers, verdicts and timings, never a transcript.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from t2_agentic_voice import VoiceSettings, get_logger
from t2_agentic_voice.ports import SpeechToText
from t2_agentic_voice.tracing import Tracing

from ole5_voice.evals import cli, history, items, matcher, scorecard, split
from ole5_voice.evals.answerers import adapter
from ole5_voice.evals.audio import AudioFormatError, read_wav, sha256_file
from ole5_voice.evals.files import read_lines
from ole5_voice.evals.groq_answerer import Clock, Sleep
from ole5_voice.evals.models import Item, Split, SplitFile, Variant
from ole5_voice.evals.runs import (
    Answer,
    AnswerRequest,
    HistoryLine,
    Matcher,
    Scorecard,
    ScorecardWriter,
    VariantResult,
)
from ole5_voice.evals.worktree import Git, refused, run_git

DATA = Path("apps", "ole5-voice-agent", "evals")  # the golden set's files, below a worktree's top
log = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


def _here() -> Path:
    return Path(__file__).resolve().parent


@dataclass(frozen=True)
class Parts:
    """What a run is built from, each replaceable by a test's fake: the folder whose checkout
    runs, `git`, the golden set's loaders (`items.py`, `split.py`, `matcher.py`), the scorecard
    writer and the history, the speech-to-text adapter, tracing, the normalizer a window's words
    are counted after (the scorers' form, `matcher.normalize`) and the clocks."""

    folder: Path = field(default_factory=_here)
    git: Git = run_git
    load_items: Callable[[Path], tuple[Item, ...]] = items.load_items
    load_split: Callable[[Path], SplitFile] = split.load_split
    load_matcher: Callable[[Path], Matcher] = matcher.load_matcher
    write_scorecard: ScorecardWriter = scorecard.write_scorecard
    append_line: Callable[[HistoryLine, Path], None] = history.append_line
    speech_to_text: Callable[[VoiceSettings], SpeechToText] = adapter
    tracing: Callable[[VoiceSettings], Tracing] = Tracing.from_settings
    normalize: Callable[[str], str] = matcher.normalize
    now: Callable[[], datetime] = _now
    clock: Clock = time.perf_counter  # monotonic; 15.6 ms steps for time.monotonic on Windows
    sleep: Sleep = asyncio.sleep


def audio_roots(values: Sequence[str]) -> dict[str, Path]:
    """`--audio ROOT=FOLDER`, each root once (`cli.audio_roots`), or the run's refusal."""
    try:
        roots = cli.audio_roots(cli.audio_root(value) for value in values)
    except ValueError as error:
        problem = str(error)
    else:
        return roots
    raise refused(f"--audio: {problem}", "give each root once, as --audio ROOT=FOLDER")


@dataclass(frozen=True)
class Choice:
    """What the command line chose: the split; a windows run's lengths, which take the split's
    talk-over clips only (the registration's "Windows"); a dev screen file; the language hint,
    from the item's label (`label`) or none (`auto`); the audio roots; and whether the answerer
    reads the audio, which is then checked."""

    split: Split
    windows_ms: tuple[int, ...] = ()
    questions: Path | None = None
    hint: str = "label"
    roots: Mapping[str, Path] = field(default_factory=dict)
    needs_audio: bool = False


@dataclass(frozen=True)
class Todo:
    """One variant to answer: its item, and the request its answerer is handed."""

    item: Item
    variant: Variant
    request: AnswerRequest

    def result(self, answer: Answer, judge: Matcher, side: Split, judged: bool) -> VariantResult:
        """The variant scored on `answer`: right when the matcher takes it for the reference or
        an accepted alternative; no verdict for a failure, or in a run of windows only."""
        item, variant = self.item, self.variant
        right = None
        if judged and answer.failure is None:
            right = judge.is_right(answer.text or "", items.references(item, variant))
        return VariantResult(
            item=item.id,
            variant=variant.id,
            split=side,
            kind=item.kind,
            language=item.language,
            device=variant.device,
            want=item.want,
            tags=variant.tags,
            reference=variant.reference,
            alternatives=item.alternatives,
            terms=item.terms,
            answer=answer,
            judged=judged,
            right=right,
        )


@dataclass(frozen=True)
class Plan:
    """What a run answers, its smoke test's variant, its data's digest and its matcher."""

    todo: tuple[Todo, ...]
    smoke: Todo
    digest: str
    matcher: Matcher


def load_plan(data: Path, choice: Choice, parts: Parts) -> Plan:
    """The plan of a run on the golden set in `data`: only the variants the owner has checked
    (`items.unchecked`, the rule `poe golden` accepts a variant by, so a run is scored on the set
    `frozen.json` lists as accepted); the others are left out, logged as a count, and listed by
    `frozen.json`. The smoke test's variant is the run's first, or for a held-out run the first
    checked dev variant, so it never reads a held-out answer. The digest covers the run's
    variants, the committed split and the spelling guide."""
    try:
        golden = parts.load_items(data / items.GOLDEN_DIR)
        committed = parts.load_split(data / items.SPLIT_FILE)
        judge = parts.load_matcher(data / items.SPELLING_FILE)
        spelling = sha256_file(data / items.SPELLING_FILE)
    except (OSError, ValueError):  # a pydantic ValidationError is a ValueError
        raise refused("the golden set's files do not load", "run `poe golden`") from None
    sides = committed.items
    if {item.id for item in golden} != set(sides):
        raise refused(
            "the committed split does not hold exactly the golden set's items",
            "write the split again (`python -m ole5_voice.evals.split`) and commit it",
        )
    talkover_only = bool(choice.windows_ms)
    named = [
        (item, variant)
        for item in golden
        if sides[item.id] == choice.split and (item.source == "talkover" or not talkover_only)
        for variant in item.variants
    ]
    if choice.questions is not None:
        named = _screened(named, choice.questions)
    pairs = [(item, variant) for item, variant in named if items.unchecked(variant) is None]
    dev = [
        (item, variant)
        for item in golden
        if sides[item.id] == "dev"
        for variant in item.variants
        if items.unchecked(variant) is None
    ]
    log.info("unchecked_left_out", variants=len(named) - len(pairs), of=len(named))
    if named and not pairs:
        raise refused(
            "the run has no variant the owner has checked",
            "confirm the takes in the recorder's review mode, import them, and run `poe golden`",
        )
    first = pairs[:1] if choice.split == "dev" else dev[:1]
    if not pairs or not first:
        raise refused(
            "the run has no variant, or no dev variant for its smoke test",
            "check --split, --questions and the committed split",
        )
    todo = tuple(Todo(i, v, _request(i, v, choice, choice.windows_ms)) for i, v in pairs)
    smoke = Todo(*first[0], _request(*first[0], choice, ()))
    body = {
        "variants": [
            [item.model_dump(mode="json", exclude={"variants"}), variant.model_dump(mode="json")]
            for item, variant in pairs
        ],
        "split": committed.model_dump(mode="json"),
        "spelling": spelling,
    }
    text = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return Plan(todo, smoke, hashlib.sha256(text.encode()).hexdigest(), judge)


def _screened(pairs: list[tuple[Item, Variant]], path: Path) -> list[tuple[Item, Variant]]:
    """Only the variants a screen file names, one `item/variant` a line, blank lines and `#`
    comments skipped (evaluation.md, "Screens"); refused when it names one the run's split does
    not hold."""
    lines = read_lines(path)
    if lines is None:
        raise refused("--questions cannot be read", "give a UTF-8 file")
    wanted = set(lines)
    unknown = wanted - {f"{item.id}/{variant.id}" for item, variant in pairs}
    if unknown:
        raise refused(
            f"--questions names {len(unknown)} variant(s) the run's split does not hold",
            "name each as item/variant, from the dev split",
        )
    return [(i, v) for i, v in pairs if f"{i.id}/{v.id}" in wanted]


def _request(
    item: Item, variant: Variant, choice: Choice, windows_ms: tuple[int, ...]
) -> AnswerRequest:
    """A variant's request: its segments' files, each read and checked against its manifest's
    hash when the answerer reads audio (otherwise only named, never opened)."""
    paths: list[Path] = []
    for ref in variant.segments:
        if not choice.needs_audio:
            paths.append(Path(ref.root, ref.path))
            continue
        if ref.root not in choice.roots:
            raise refused(
                f"the audio root {ref.root!r} has no --audio", f"pass --audio {ref.root}=<folder>"
            )
        path = choice.roots[ref.root] / ref.path
        try:
            same = read_wav(path).sha256 == ref.sha256
        except (OSError, AudioFormatError):
            same = False
        if not same:
            raise refused(
                f"an audio file below the root {ref.root!r} is missing, not 16 kHz mono 16-bit "
                "WAV, or not the file its manifest hashed",
                f"run `poe golden --audio {ref.root}=<folder>`, which names it",
            )
        paths.append(path)
    language = None if choice.hint == "auto" else "en" if item.language == "english" else "ar"
    return AnswerRequest(segments=tuple(paths), language=language, windows_ms=windows_ms)


def clip_answers(
    path: Path | None, todo: Sequence[Todo], *, commit: str, model: str
) -> dict[Variant, str]:
    """`--clips-from` (a run's `--out` folder, or its scorecard): the clip answers of the same
    model's first dev run at this commit, which serve the windows as long as their clip, not
    sent again (the registration's "Windows"); for a take of two segments, its first segment's,
    which the window is cut from."""
    if path is None:
        return {}
    try:
        card: Scorecard | None = scorecard.load_scorecard(path)
    except scorecard.EvalDataError:
        card = None
    if card is None:  # raised outside the handler, and naming no field of the file
        raise refused("--clips-from is not a scorecard", "give a dev run's scorecard.json")
    if (card.run.split, card.run.model, card.run.commit) != ("dev", model, commit):
        raise refused(
            "--clips-from is not a dev run of this model at this commit",
            "give the model's first dev run at the measurement commit",
        )
    known = {(r.item, r.variant): r.answer for r in card.variants if r.answer.text is not None}
    found: dict[Variant, str] = {}
    for t in todo:
        if (answer := known.get((t.item.id, t.variant.id))) is not None:
            found[t.variant] = answer.segments[0].text if answer.segments else answer.text or ""
    return found


@dataclass
class Progress:
    """What a run has measured so far, kept as each variant finishes: a dev run's result is
    appended to its `results_file` and logged with its identifiers, verdict and timings; a
    held-out run's line is a count."""

    total: int
    results_file: Path | None  # None for a held-out run
    clock: Clock
    began: float
    results: list[VariantResult] = field(default_factory=list)
    smoke_passed: bool = False
    capped: bool = False
    interrupted: bool = False

    def add(self, result: VariantResult) -> None:
        self.results.append(result)
        done, elapsed = len(self.results), round(self.clock() - self.began, 1)
        if self.results_file is None:
            log.info("progress", done=done, of=self.total, elapsed_s=elapsed)
            return
        with self.results_file.open("a", encoding="utf-8", newline="\n") as file:
            file.write(result.model_dump_json() + "\n")
        requests = result.answer.requests
        verdict = result.answer.failure or (
            "unjudged" if result.right is None else "right" if result.right else "wrong"
        )
        log.info(
            "variant_done",
            done=done,
            of=self.total,
            item=result.item,
            variant=result.variant,
            verdict=verdict,
            requests=len(requests),
            retries=sum(r.attempt > 1 for r in requests),
            latency_ms=round(sum(r.latency_ms for r in requests)),
            elapsed_s=elapsed,
        )
