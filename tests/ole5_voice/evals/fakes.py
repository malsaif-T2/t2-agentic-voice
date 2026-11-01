"""Fakes for the golden set's tests (plan 002, Block 0). Each implements one protocol, or stands
in for one function another track builds, and nothing else, so a track builds against another
track's interface before that track merges (plans README, "Parallel tracks"):

- `FakeSpeechToText`: the library's `SpeechToText` port;
- `fake_normalize`: `normalize_arabic` and `normalize_digits` (Track A);
- `FakeMatcher`: the `Matcher` (Track D);
- `FakeScorecardWriter`: the `ScorecardWriter` (Track F);
- `FakeSignTest` and `FakeSpellingCheck`: `sign_test` and `spelling_issues` (Track A);
- `FakeTracing`: the tracing span helpers (Track C).
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from ole5_voice.evals.models import Metrics, RunInfo, Scorecard, VariantResult
from opentelemetry.trace import INVALID_SPAN, Span
from t2_agentic_voice import ProviderError
from t2_agentic_voice.languages import SpellingIssue, SpellingRule
from t2_agentic_voice.ports import AudioClip, DataFlow, Transcript
from t2_agentic_voice.tracing import SpeechToTextSpan, Tracing

FAKE_FLOW = DataFlow(
    provider="Fake", processed_in="this process", stored_in="nowhere", retention="none"
)
_NOT_WORD = re.compile(r"[^\w\s]")


class FakeSpeechToText:
    """A `SpeechToText` that answers from a script, one entry per call: a text (heard in the
    language asked for, billed as Groq bills, at least 10 s), a `Transcript`, or a
    `ProviderError` to raise. With the script used up, it hears nothing. It records each call,
    and waits `delay_s` first, so a test can cancel it mid-call."""

    name = "fake"
    data_flow = FAKE_FLOW

    def __init__(
        self, script: Sequence[str | Transcript | ProviderError] = (), *, delay_s: float = 0.0
    ) -> None:
        self.script = list(script)
        self.delay_s = delay_s
        self.calls: list[tuple[AudioClip, str | None, str | None]] = []

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript:
        self.calls.append((clip, language, prompt))
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        entry = self.script.pop(0) if self.script else ""
        if isinstance(entry, ProviderError):
            raise entry
        if isinstance(entry, Transcript):
            return entry
        return Transcript(text=entry, language=language, billed_seconds=max(10.0, clip.seconds))


def fake_normalize(text: str) -> str:
    """A stand-in for `normalize_arabic` and `normalize_digits`: lower case, punctuation
    dropped, runs of space made one. It folds no Arabic letter and reads no digit."""
    return " ".join(_NOT_WORD.sub(" ", text.casefold()).split())


class FakeMatcher:
    """A `Matcher`: right when the output equals one reference after `normalize`, with every
    space removed, as the real one compares. It records each call."""

    def __init__(self, normalize: Callable[[str], str] = fake_normalize) -> None:
        self.normalize = normalize
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def is_right(self, output: str, references: Sequence[str]) -> bool:
        self.calls.append((output, tuple(references)))
        heard = self.normalize(output).replace(" ", "")
        return any(heard == self.normalize(r).replace(" ", "") for r in references)


class FakeScorecardWriter:
    """A `ScorecardWriter` that counts only the right answers and the failures, writes the
    scorecard as `scorecard.json` into `out`, and records each call."""

    def __init__(self) -> None:
        self.calls: list[tuple[RunInfo, tuple[VariantResult, ...], bool, Path]] = []

    def __call__(
        self, run: RunInfo, results: Sequence[VariantResult], *, complete: bool, out: Path
    ) -> Scorecard:
        self.calls.append((run, tuple(results), complete, out))
        scored = [r for r in results if r.right is not None]
        right = sum(1 for r in scored if r.right)
        totals = Metrics(
            variants=len(results),
            right=right,
            failures=len(results) - len(scored),
            accuracy=right / len(scored) if scored else None,
        )
        held_out = run.split == "held-out"
        scorecard = Scorecard(
            run=run,
            complete=complete,
            totals=totals,
            breakdowns={},
            variants=() if held_out else tuple(results),
        )
        out.mkdir(parents=True, exist_ok=True)
        text = scorecard.model_dump_json(indent=2) + "\n"
        (out / "scorecard.json").write_text(text, encoding="utf-8", newline="\n")
        return scorecard


class FakeSignTest:
    """A stand-in for `sign_test`: the p-value set in advance; it records each call."""

    def __init__(self, p: float = 1.0) -> None:
        self.p = p
        self.calls: list[tuple[int, int]] = []

    def __call__(self, better: int, worse: int) -> float:
        self.calls.append((better, worse))
        return self.p


class FakeSpellingCheck:
    """A stand-in for `spelling_issues`: an issue for each avoided spelling found anywhere in
    the reference, case ignored, with no normalization and no word boundaries."""

    def __call__(self, reference: str, rules: Sequence[SpellingRule]) -> list[SpellingIssue]:
        folded = reference.casefold()
        return [
            SpellingIssue(rule=rule.id, found=spelling, write=rule.write)
            for rule in rules
            for spelling in rule.avoid
            if spelling.casefold() in folded
        ]


class FakeSpeechToTextSpan(SpeechToTextSpan):
    """What `FakeTracing.speech_to_text` yields: it keeps what is recorded."""

    def __init__(self, attributes: dict[str, object]) -> None:
        self.attributes = attributes

    def record(self, *, text: str, language: str | None, billed_seconds: float | None) -> None:
        self.attributes |= {"text": text, "language": language, "billed_seconds": billed_seconds}


class FakeTracing(Tracing):
    """A stand-in for the tracing helpers: each span is kept in `spans` as a dict, in the order
    they open, instead of being exported."""

    def __init__(self) -> None:
        self.spans: list[dict[str, object]] = []
        self.shut = False

    @property
    def dropped_spans(self) -> int:
        return 0

    @contextmanager
    def turn(self, *, session_id: str, name: str = "turn") -> Iterator[Span]:
        self.spans.append({"span": name, "session_id": session_id})
        yield INVALID_SPAN

    @contextmanager
    def speech_to_text(
        self, parent: Span, *, model: str, language: str | None, audio_seconds: float
    ) -> Iterator[SpeechToTextSpan]:
        attributes: dict[str, object] = {
            "span": "speech_to_text",
            "parent": parent,
            "model": model,
            "language_sent": language,
            "audio_seconds": audio_seconds,
        }
        self.spans.append(attributes)
        yield FakeSpeechToTextSpan(attributes)

    def shutdown(self) -> None:
        self.shut = True
