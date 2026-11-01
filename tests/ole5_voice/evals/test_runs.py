"""What a run produces parses strictly, and the evaluation's own rules hold in the models
themselves: a held-out run is never traced and its scorecard holds aggregates only
(evaluation.md, "Splits"), a secret setting is shown only as set or not set (docs/SECURITY.md,
invariant 5), and a variant has a verdict exactly when it was judged and answered."""

from __future__ import annotations

import json
from typing import get_args

import pytest
from ole5_voice.evals.runs import (
    Answer,
    HistoryLine,
    Metrics,
    Outcome,
    RunInfo,
    Scorecard,
    SegmentAnswer,
    VariantResult,
    Window,
    WindowMetrics,
)
from pydantic import ValidationError
from t2_agentic_voice.core.errors import PROVIDER_ERROR_KINDS

from tests.ole5_voice.evals import samples

MADE_UP_KEY = "gsk_made-up-key-for-tests-0123456789"
HELD_OUT_TEXT = "a made-up held-out transcript"
LINE: dict[str, object] = {
    "time": "2026-11-03T09:00:00Z",
    "commit": "0f44056+",
    "run": "r1",
    "answerer": "groq",
    "model": "whisper-large-v3",
    "settings": {"stt.model": "whisper-large-v3", "groq.api_key": "set"},
    "split": "dev",
    "items": 60,
    "variants": 196,
    "accuracy": 0.41,
    "violations": 0,
    "billed_seconds": 1960.0,
    "price_per_hour_usd": 0.111,
    "cost_usd": 0.06,
    "latency_median_ms": 295.0,
    "breakdowns": {"language": {"saudi": 0.3}},
    "scorecard": "scorecard.json",
    "data_digest": samples.SHA,
    "note": "the baseline, large-v3",
    "complete": True,
}


def _scorecard(**fields: object) -> dict[str, object]:
    card: dict[str, object] = {
        "run": samples.run().model_dump(mode="json"),
        "complete": True,
        "totals": Metrics(variants=1, right=1, failures=0).model_dump(),
        "breakdowns": {},
    }
    return card | fields


def _held_out(**fields: object) -> dict[str, object]:
    return samples.run().model_dump(mode="json") | {"split": "held-out"} | fields


def test_an_outcome_is_ok_stuck_or_a_provider_error_kind() -> None:
    assert set(get_args(Outcome)) == {"ok", "stuck", *PROVIDER_ERROR_KINDS}


def test_a_history_line_names_its_commit_and_its_price() -> None:
    assert HistoryLine.model_validate(LINE).commit == "0f44056+"
    for change in ({"commit": "main"}, {"price_per_hour_usd": -1}, {"price_per_hour_usd": "inf"}):
        with pytest.raises(ValidationError):
            HistoryLine.model_validate(LINE | change)


@pytest.mark.parametrize("name", ["groq.api_key", "tracing.token", "other.secret", "password"])
def test_a_secret_setting_is_shown_only_as_set_or_not_set(name: str) -> None:
    """A run's settings reach its scorecard and the committed history.jsonl."""
    for model, data in ((RunInfo, samples.run().model_dump()), (HistoryLine, LINE)):
        with pytest.raises(ValidationError) as raised:
            model.model_validate(data | {"settings": {name: MADE_UP_KEY}})
        assert MADE_UP_KEY not in str(raised.value) and MADE_UP_KEY not in repr(raised.value)
        for shown in ("set", "not set"):
            assert model.model_validate(data | {"settings": {name: shown}})
    kept = {"groq.api_key_file": "set", "stt.model": "whisper-large-v3", "monkey": "x"}
    assert RunInfo.model_validate(samples.run().model_dump() | {"settings": kept}).settings == kept


def test_a_run_has_its_price_per_hour() -> None:
    assert samples.run().price_per_hour_usd == 0.0
    for price in (-0.01, float("inf"), float("nan")):
        with pytest.raises(ValidationError):
            RunInfo.model_validate(samples.run().model_dump() | {"price_per_hour_usd": price})


def test_a_held_out_run_is_never_traced() -> None:
    assert RunInfo.model_validate(samples.run().model_dump() | {"traced": True}).traced
    with pytest.raises(ValidationError, match="never traced"):
        RunInfo.model_validate(_held_out(traced=True))
    with pytest.raises(ValidationError, match="traced"):  # a copy skips the check; reading does not
        copied = samples.run().model_copy(update={"split": "held-out", "traced": True})
        Scorecard.model_validate(_scorecard(run=copied))


def test_a_dev_scorecard_holds_its_variants_and_one_speaker() -> None:
    card = Scorecard.model_validate(_scorecard(variants=[samples.result().model_dump()]))
    assert (len(card.variants), card.speakers) == (1, "one speaker")
    assert Scorecard.model_validate_json(card.model_dump_json()) == card


def test_a_held_out_scorecard_holds_aggregates_only() -> None:
    windows = [
        WindowMetrics(
            ms=500,
            language="english",
            clips=3,
            empty=1,
            reused=0,
            words=4,
            leading_words=2,
            reference_words=6,
            one_word_clips=1,
            holds_word=0,
        )
    ]
    card = Scorecard.model_validate(_scorecard(run=_held_out(), windows=windows))
    assert (card.variants, card.windows[0].clips) == ((), 3)
    variant = samples.result(heard=HELD_OUT_TEXT).model_dump(mode="json") | {"split": "held-out"}
    refused = _scorecard(run=_held_out(), variants=[variant])
    with pytest.raises(ValidationError, match="aggregates only") as built:
        Scorecard.model_validate(refused)
    with pytest.raises(ValidationError, match="aggregates only") as read:  # eval-compare's way
        Scorecard.model_validate_json(json.dumps(refused))
    assert HELD_OUT_TEXT not in str(built.value) + str(read.value)


def test_a_dev_scorecard_never_holds_a_held_out_variant() -> None:
    variant = samples.result().model_dump() | {"split": "held-out"}
    with pytest.raises(ValidationError, match="its own split"):
        Scorecard.model_validate(_scorecard(variants=[variant]))


def test_a_window_carries_its_measures() -> None:
    window = Window(ms=500, text="stop", empty=False, words=1, leading_words=1, holds_word=True)
    assert Window.model_validate_json(window.model_dump_json()) == window
    for bad in (
        {"empty": True, "words": 1},  # an empty window heard nothing
        {"empty": False, "words": 0},
        {"words": 1, "leading_words": 2},  # its leading words are among its words
    ):
        with pytest.raises(ValidationError):
            Window.model_validate(window.model_dump() | bad)


def test_an_answer_keeps_its_confidence_and_each_segments() -> None:
    answer = Answer(
        variant="v1",
        text="one two",
        confidence=-0.3,
        no_speech_prob=0.1,
        segments=(SegmentAnswer(text="one", confidence=-0.2), SegmentAnswer(text="two")),
    )
    assert Answer.model_validate_json(answer.model_dump_json()) == answer
    with pytest.raises(ValidationError):
        SegmentAnswer(text="x", no_speech_prob=1.5)


def test_a_result_has_a_verdict_exactly_when_judged_and_answered() -> None:
    judged = samples.result().model_dump()
    failed = judged | {"answer": {"variant": "v1", "failure": "provider"}, "right": None}
    windows_only = judged | {"answer": {"variant": "v1"}, "judged": False, "right": None}
    for kept in (judged, failed, windows_only):
        assert VariantResult.model_validate(kept)
    for refused in (
        judged | {"right": None},  # judged and answered, but no verdict
        failed | {"right": False},  # a failure is not a wrong answer
        windows_only | {"right": True},  # nothing was judged
        judged | {"answer": {"variant": "v1"}},  # a verdict on no text
    ):
        with pytest.raises(ValidationError, match="judged and answered"):
            VariantResult.model_validate(refused)


def test_a_result_carries_its_items_terms_and_want() -> None:
    result = VariantResult.model_validate(
        samples.result().model_dump() | {"terms": ["Outlook"], "want": "send"}
    )
    assert (result.terms, result.want) == (("Outlook",), "send")
