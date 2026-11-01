"""The fakes (tests/ole5_voice/evals/fakes.py) implement their protocols, so the tracks that
build against them build against the real interfaces."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ole5_voice.evals import history, items, split
from ole5_voice.evals.models import SplitFile
from ole5_voice.evals.runs import (
    SCORECARD_FILE,
    Answer,
    HistoryLine,
    Matcher,
    RunInfo,
    Scorecard,
    ScorecardWriter,
    VariantResult,
)
from t2_agentic_voice import ProviderError, evals
from t2_agentic_voice.evals import Recall
from t2_agentic_voice.languages import SpellingRule
from t2_agentic_voice.ports import AudioClip, SpeechToText, Transcript
from t2_agentic_voice.tracing import Tracing

from tests.ole5_voice.evals import samples
from tests.ole5_voice.evals.fakes import (
    FakeGoldenSet,
    FakeHistory,
    FakeMatcher,
    FakeScorecardWriter,
    FakeScorers,
    FakeSignTest,
    FakeSpeechToText,
    FakeSpellingCheck,
    FakeTracing,
    fake_normalize,
)

CLIP = AudioClip(pcm16=b"\x00\x00" * 16_000)
RUN = RunInfo(
    name="r1",
    started_at=datetime(2026, 11, 3, 9, 0, tzinfo=UTC),
    commit="0f44056",
    answerer="reference",
    split="dev",
    settings={},
    price_per_hour_usd=0.0,
    data_digest="0" * 64,
    note="a test run",
)


def _result(variant: str, right: bool | None) -> VariantResult:
    answer = Answer(variant=variant, text="x", failure=None if right is not None else "provider")
    return VariantResult(
        item="i1",
        variant=variant,
        split="dev",
        kind="request",
        language="english",
        device="laptop",
        reference="x",
        answer=answer,
        right=right,
    )


def test_the_fake_speech_to_text_answers_from_its_script() -> None:
    script: list[str | Transcript | ProviderError] = [
        "stop",
        Transcript(text="hi", language="en"),
        ProviderError("timeout", True),
    ]
    fake = FakeSpeechToText(script)
    stt: SpeechToText = fake

    async def three() -> list[str]:
        heard = [await stt.transcribe(CLIP, language="en", prompt=None) for _ in range(2)]
        with pytest.raises(ProviderError):
            await stt.transcribe(CLIP, language="en", prompt=None)
        heard.append(await stt.transcribe(CLIP, language=None, prompt="p"))
        return [h.text for h in heard] + [str(heard[0].billed_seconds)]

    assert asyncio.run(three()) == ["stop", "hi", "", "10.0"]
    assert [(language, prompt) for _, language, prompt in fake.calls][-1] == (None, "p")


def test_the_fake_speech_to_text_can_be_cancelled_mid_call() -> None:
    stt = FakeSpeechToText(["late"], delay_s=10)

    async def cancelled() -> None:
        await asyncio.wait_for(stt.transcribe(CLIP, language="ar", prompt=None), timeout=0.01)

    with pytest.raises(TimeoutError):
        asyncio.run(cancelled())


def test_the_fake_matcher_compares_normalized_text_without_spaces() -> None:
    matcher: Matcher = FakeMatcher()
    assert fake_normalize("Stop,  NOW!") == "stop now"
    assert matcher.is_right("Stop now.", ["stopnow"])
    assert not matcher.is_right("stop", ["go", "wait"])


def test_the_fake_scorecard_writer_writes_a_scorecard(tmp_path: Path) -> None:
    fake = FakeScorecardWriter()
    writer: ScorecardWriter = fake
    unjudged = VariantResult.model_validate(
        _result("v4", True).model_dump()
        | {"answer": {"variant": "v4"}, "judged": False, "right": None}
    )
    results = [_result("v1", True), _result("v2", False), _result("v3", None), unjudged]
    card = writer(RUN, results, complete=True, out=tmp_path / "run")
    assert (card.totals.right, card.totals.failures, card.totals.accuracy) == (1, 1, 0.5)
    written = (tmp_path / "run" / SCORECARD_FILE).read_text(encoding="utf-8")
    assert Scorecard.model_validate_json(written) == card
    held_out = writer(
        RUN.model_copy(update={"split": "held-out"}), results, complete=False, out=tmp_path
    )
    assert (held_out.variants, held_out.speakers) == ((), "one speaker")
    assert len(fake.calls) == 2


def test_the_fake_golden_set_gives_its_items_and_split(tmp_path: Path) -> None:
    fake = FakeGoldenSet([samples.item()], SplitFile(salt="m1", items={"i1": "dev"}))
    load_items: Callable[[Path], tuple[object, ...]] = items.load_items
    load_split: Callable[[Path], SplitFile] = split.load_split
    load_items, load_split = fake.load_items, fake.load_split  # the real ones' shapes
    assert load_items(tmp_path / "golden") == (samples.item(),)
    assert load_split(tmp_path / "split.json").items == {"i1": "dev"}
    assert fake.read == [tmp_path / "golden", tmp_path / "split.json"]


def test_the_fake_history_appends_lines_with_lf_endings(tmp_path: Path) -> None:
    fake = FakeHistory()
    append: Callable[[HistoryLine, Path], None] = history.append_line
    append = fake
    file = tmp_path / "history.jsonl"
    append(samples.history_line("r1"), file)
    append(samples.history_line("r2"), file)
    data = file.read_bytes()
    assert b"\r" not in data and data.count(b"\n") == 2
    assert [HistoryLine.model_validate_json(raw).run for raw in data.splitlines()] == ["r1", "r2"]
    assert [line.run for line in fake.lines] == ["r1", "r2"]


def test_the_fake_scorers_give_their_set_values_with_the_real_shapes() -> None:
    fake = FakeScorers(rate=0.25, recall=Recall(expected=2, found=1), silence=3)
    wer: Callable[[Sequence[str], Sequence[str]], float] = evals.wer
    cer: Callable[[Sequence[str], Sequence[str]], float] = evals.cer
    term_recall: Callable[[str, str, Sequence[str]], Recall] = evals.term_recall
    id_recall: Callable[[str, str], Recall] = evals.id_recall
    silence_output: Callable[[str], int] = evals.silence_output
    wer, cer, term_recall = fake.wer, fake.cer, fake.term_recall
    id_recall, silence_output = fake.id_recall, fake.silence_output
    assert (wer(["a b"], ["a"]), cer(["ab"], ["a"])) == (0.25, 0.25)
    assert term_recall("open Outlook", "open outlook", ["Outlook"]) == Recall(expected=2, found=1)
    assert (id_recall("1234", "1234").found, silence_output("thanks")) == (1, 3)
    assert [name for name, _ in fake.calls] == [
        "wer",
        "cer",
        "term_recall",
        "id_recall",
        "silence_output",
    ]
    assert FakeScorers().recall == Recall(expected=0, found=0)


def test_the_fake_sign_test_and_spelling_check() -> None:
    sign_test = FakeSignTest(p=0.03125)
    assert (sign_test(6, 0), sign_test.calls) == (0.03125, [(6, 0)])
    rule = SpellingRule.model_validate(
        {"id": "outlook", "avoid": ["اوتلوك"], "write": "Outlook", "said": "x", "on": "2026-11-01"}
    )
    issues = FakeSpellingCheck()("افتح اوتلوك", [rule])
    assert [(i.rule, i.found, i.write) for i in issues] == [("outlook", "اوتلوك", "Outlook")]
    assert FakeSpellingCheck()("open Outlook", [rule]) == []


def test_the_fake_tracing_keeps_its_spans() -> None:
    fake = FakeTracing()
    tracing: Tracing = fake
    with (
        tracing.turn(session_id="r1") as turn,
        tracing.speech_to_text(
            turn, model="whisper-large-v3", language="ar", audio_seconds=1.0
        ) as stt,
    ):
        stt.record(text="نعم", language="ar", billed_seconds=10.0)
    tracing.shutdown()
    assert fake.spans[0] == {"span": "turn", "session_id": "r1"}
    assert (fake.spans[1]["model"], fake.spans[1]["text"]) == ("whisper-large-v3", "نعم")
    assert (tracing.dropped_spans, fake.shut) == (0, True)
