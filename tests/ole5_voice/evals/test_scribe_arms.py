"""Run H's Scribe arms (D-115; scribe_arms.py, scribe_arm_card.py), with made-up answers: each
arm's requests, each shared one once; each answer read with the library's rule as a turn of an
Arabic call and of an English one, `detected` keeping the detecting request's words only when the
call moves, and sending it only for a variant its gate passed, which then never moves; the truth
each turn is scored against, its kinds tied to the strata; and the scorecard's moves (right,
wrong, missed, the false moves on short replies), error rates by item language, seconds to the
transcript and the threshold table."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, get_args

import pytest
from ole5_voice.evals.items import EVALS, Strata, read_toml
from ole5_voice.evals.models import Language
from ole5_voice.evals.scribe_arm_card import (
    EXPECTED,
    QUESTION_KINDS,
    SHORT_KINDS,
    SILENT_KINDS,
    THRESHOLDS,
    ArmRun,
    moves_of,
    scorecard_of,
)
from ole5_voice.evals.scribe_arms import (
    ARM_NAMES,
    DETECTING,
    ArmAnswer,
    ArmName,
    ArmResult,
    Ask,
    asks,
    distinct_asks,
    turn_of,
    turns_of,
)

from tests.ole5_voice.evals.run_support import COMMIT
from tests.ole5_voice.evals.samples import SHA, WHEN

QUESTION = "which flights go to Dubai tomorrow"
AR_HINT, EN_HINT = (
    Ask(named="ar", others=("en",), prompt="ar"),
    Ask(named="en", others=("ar",), prompt="en"),
)


class Scorers:
    """Stands in for the `evals` scorers: the share of outputs that differ from their reference."""

    def wer(self, references: Sequence[str], outputs: Sequence[str]) -> float:
        return sum(r != o for r, o in zip(references, outputs, strict=True)) / len(references)

    def cer(self, references: Sequence[str], outputs: Sequence[str]) -> float:
        return self.wer(references, outputs) / 2


def _answer(ask: Ask, heard: str | None, probability: float | None, **more: Any) -> ArmAnswer:
    fields: dict[str, Any] = {"text": QUESTION, "heard": heard, "probability": probability}
    return ArmAnswer.model_validate(
        {"ask": ask, "seconds": 0.5, "billed_seconds": 2.0} | fields | more
    )


def _result(
    *answers: ArmAnswer, language: Language = "english", kind: str = "request", item: str = "e1"
) -> ArmResult:
    return ArmResult(
        item=item,
        variant=f"{item}-v1",
        kind=kind,
        language=language,
        device="laptop",
        reference=QUESTION,
        answers=answers,
    )


def _hinted(
    heard_in_ar: str, p_ar: float, heard_in_en: str, p_en: float, **result: Any
) -> ArmResult:
    return _result(
        _answer(AR_HINT, heard_in_ar, p_ar), _answer(EN_HINT, heard_in_en, p_en), **result
    )


def test_each_arm_shapes_its_requests_and_sends_a_shared_one_once() -> None:
    assert ARM_NAMES == ("hinted", "secondary", "none", "detected", "single")
    assert asks("hinted", "ar") == (AR_HINT,) and asks("hinted", "en") == (EN_HINT,)
    assert asks("secondary", "en") == (Ask(named=None, others=("ar", "en"), prompt="en"),)
    assert asks("none", "ar") == (Ask(named=None, prompt="ar"),)
    assert asks("detected", "ar") == (Ask(named="ar", prompt="ar"), DETECTING)
    assert Ask(named=None) == DETECTING and DETECTING not in asks("none", "ar")
    counts = {arm: len(distinct_asks(arm)) for arm in ARM_NAMES}
    assert counts == {"hinted": 2, "secondary": 2, "none": 2, "detected": 3, "single": 2}
    assert asks("detected", "en", detects=False) == (Ask(named="en", prompt="en"),)
    gated = {arm: len(distinct_asks(arm, detects=False)) for arm in ARM_NAMES}
    assert gated == {"hinted": 2, "secondary": 2, "none": 2, "detected": 2, "single": 2}


def test_the_truth_covers_every_language_and_every_kind_of_the_strata_once() -> None:
    assert set(EXPECTED) == set(get_args(Language))
    kinds = set(read_toml(EVALS / "strata.toml", Strata).items.kind)
    assert kinds == QUESTION_KINDS | SHORT_KINDS | SILENT_KINDS
    assert not (QUESTION_KINDS & SHORT_KINDS or QUESTION_KINDS & SILENT_KINDS)
    assert not SHORT_KINDS & SILENT_KINDS


def test_a_hinted_answer_moves_the_call_at_its_threshold_and_never_on_a_short_reply() -> None:
    english = _hinted("en", 0.9, "en", 0.99)
    assert turn_of("hinted", english, "ar", threshold=0.8).moved == "en"
    assert turn_of("hinted", english, "ar", threshold=0.95).moved is None
    assert turn_of("hinted", english, "en", threshold=0.5).moved is None  # its own language
    short = _result(_answer(AR_HINT, "en", 0.99, text="okay thanks"), _answer(EN_HINT, "en", 0.9))
    assert turn_of("hinted", short, "ar", threshold=0.5).moved is None
    failed = _result(
        _answer(AR_HINT, None, None, text=None, failure="timeout"), _answer(EN_HINT, "en", 0.9)
    )
    turn = turn_of("hinted", failed, "ar", threshold=0.5)
    assert (turn.moved, turn.text, turn.seconds) == (None, None, 0.5)
    with pytest.raises(ValueError, match="threshold"):
        turn_of("none", english, "ar", threshold=None)


def test_detected_keeps_the_detecting_words_only_when_the_call_moves() -> None:
    named = _answer(Ask(named="ar", prompt="ar"), "en", 0.9, text="translated words", seconds=0.4)
    other = _answer(Ask(named="en", prompt="en"), "en", 0.9, seconds=0.3)
    detecting = _answer(Ask(named=None), "en", 0.7, seconds=0.6)
    result = _result(named, other, detecting)
    moved = turn_of("detected", result, "ar", threshold=None)
    assert (moved.moved, moved.text, moved.seconds) == ("en", QUESTION, 0.6)  # the slower of two
    assert turn_of("detected", result, "ar", threshold=0.75).moved is None  # 0.7 under it
    stays = turn_of("detected", result, "en", threshold=None)
    assert (stays.moved, stays.text) == (None, QUESTION)


def test_a_detected_variant_its_gate_did_not_pass_keeps_its_named_answer_and_never_moves() -> None:
    named = _answer(Ask(named="ar", prompt="ar"), "en", 0.99, text="translated words", seconds=0.4)
    other = _answer(Ask(named="en", prompt="en"), "en", 0.99, seconds=0.3)
    gated = _result(named, other).model_copy(update={"detects": False})  # no DETECTING sent
    for threshold in (None, 0.5):
        turn = turn_of("detected", gated, "ar", threshold=threshold)
        assert (turn.moved, turn.text, turn.seconds, turn.read) == (
            None,
            "translated words",
            0.4,
            named,
        )
    card = scorecard_of(_run("detected"), [gated], complete=True, scorers=Scorers())
    assert (card.both.moves.due, card.both.moves.missed, card.both.moves.wrong) == (1, 1, 0)
    assert all(row.moves.right == 0 for row in card.thresholds)
    assert {record.detects for record in card.turns} == {False}
    with pytest.raises(KeyError):  # a passed variant whose detecting answer is missing
        turn_of("detected", gated.model_copy(update={"detects": True}), "ar", threshold=None)


def _run(arm: ArmName = "hinted") -> ArmRun:
    return ArmRun(
        name="sa-dev-hinted",
        started_at=WHEN,
        commit=COMMIT,
        split="dev",
        arm=arm,
        settings={"stt.provider": "elevenlabs"},
        data_digest=SHA,
        min_probability=0.8,
        note="a made-up pass",
        price_per_hour_usd=0.25,
    )


def test_the_scorecard_counts_right_wrong_missed_and_short_false_moves() -> None:
    results = [
        _hinted("en", 0.9, "en", 0.9),  # English question: right in the Arabic call
        _hinted("ar", 0.9, "ar", 0.6, item="s1", language="saudi"),  # missed in the English call
        _hinted("ar", 0.9, "en", 0.85, item="m1", language="mixed"),  # heard English: missed
        _result(
            _answer(AR_HINT, "en", 0.95, text="that one sounds right to me"),
            _answer(EN_HINT, "en", 0.9),
            item="y1",
            kind="confirmation",
        ),  # a short reply that moves the Arabic call: wrong, short_false
    ]
    card = scorecard_of(_run(), results, complete=True, scorers=Scorers())
    moves = card.both.moves
    assert (moves.due, moves.right, moves.missed) == (3, 1, 2)
    assert (moves.wrong, moves.short_false) == (1, 1)
    assert card.calls["ar"].moves.right == 1 and card.calls["en"].moves.due == 2
    assert [row.threshold for row in card.thresholds] == list(THRESHOLDS)
    assert THRESHOLDS[0] == 0.5 and THRESHOLDS[-1] == 0.95 and len(THRESHOLDS) == 10
    at_half = card.thresholds[0].moves
    assert (at_half.right, at_half.wrong) == (2, 1)  # s1 moves the English call at 0.6
    assert card.both.seconds_p50 == 0.5 and card.both.turns == 8 and card.both.failed == 0
    assert set(card.both.errors) == {"english", "saudi", "mixed"}
    assert card.both.errors["english"].wer == 0.25 and card.both.errors["saudi"].wer == 0.0
    assert card.variants == tuple(results)
    records = {(r.item, r.call): r for r in card.turns}
    assert len(card.turns) == 8
    first = records[("e1", "ar")]
    assert (first.heard, first.probability, first.due, first.moved, first.wer) == (
        "en",
        0.9,
        True,
        "en",
        0.0,
    )
    assert records[("y1", "ar")].wer == 1.0 and not records[("y1", "ar")].due


def test_a_turn_with_no_speech_never_counts_an_error_and_any_move_is_wrong() -> None:
    noise = _hinted("en", 0.99, "ar", 0.99, item="n1", language="none", kind="noise")
    turns = turns_of("hinted", [noise], threshold=0.8)
    assert [turn.moved for turn in turns] == ["en", "ar"]
    moves = moves_of(turns)
    assert (moves.due, moves.wrong, moves.short_false) == (0, 2, 0)
    card = scorecard_of(_run(), [noise], complete=True, scorers=Scorers())
    assert card.both.errors == {}
