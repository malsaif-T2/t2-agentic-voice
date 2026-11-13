"""The scorer of `poe eval-languages` (D-086, run H's H1; languages_score.py): how
each turn's language was chosen, the same in every call language; the classifications in time
and late, and their times; each call language's variants whose first turn the rule changed, and
those whose turns got different languages; the paused requests judged as `poe eot` judges them;
the turns the rule reads back otherwise than the call named them; a held-out pass's aggregates
only; its history line; and condition 4, read across the passes against the two off passes."""

from __future__ import annotations

from pathlib import Path

import pytest
from ole5_voice.evals.eot_score import Judged
from ole5_voice.evals.history import append_line, read_history, render_history
from ole5_voice.evals.languages_card import (
    LanguageResult,
    LanguagesRun,
    LanguagesScorecard,
    call_code,
)
from ole5_voice.evals.languages_score import (
    card_of,
    line_of,
    load_pass,
    read_passes,
    scorecard_of,
)
from ole5_voice.evals.scorecard import EvalDataError
from pydantic import ValidationError

from tests.ole5_voice.evals.languages_support import pass_folder, result, run_info, scores, turn

ARABIC = scores(0.1)
CUT_OFF = Judged(true_end_ms=3000.0, verdict="cut_off", early=1)
TIMED = Judged(true_end_ms=2000.0, verdict="timed", early=0, delay_ms=500.0, decision_ms=300.0)


def _silero() -> tuple[LanguageResult, ...]:
    """Two English items and three Arabic ones, a paused request among them."""
    return (
        result("e1", turn(named="en"), language="english"),
        result("s1", turn(verdict=ARABIC)),
        result("e2", turn("late"), turn("short"), language="english"),
        result("s2", turn("short"), turn(named="en"), language="saudi"),
        result(
            "p1",
            turn("unsure", verdict=scores(0.6)),
            kind="paused_request",
            judged=CUT_OFF,
        ),
    )


def test_a_pass_counts_how_each_turn_was_chosen_and_its_classifications_times() -> None:
    card = card_of(_silero(), run=run_info("lid1-dev-silero"), held_out=False)
    assert (card.items, card.variants, card.turns) == (5, 5, 7)
    assert card.by == {"classified": 3, "late": 1, "short": 2, "unsure": 1}
    assert (card.in_time, card.late, card.never) == (4, 1, 0)
    # Each verdict 300 ms after its ask, the late one's 800 ms; it came 300 ms after its hold.
    assert (card.verdict_median_ms, card.verdict_p90_ms) == pytest.approx((300.0, 600.0))
    assert (card.late_median_ms, card.late_max_ms) == pytest.approx((300.0, 300.0))
    assert card.disagreements == 0


def test_each_call_language_counts_the_first_turns_the_rule_changed() -> None:
    """An English request in an Arabic call is changed; in an English call, the Arabic one; the
    ordinary call (`label`) holds each item in its own language; a short first turn keeps the
    call's, so s2's turns differ in an Arabic call."""
    card = card_of(_silero(), run=run_info("lid1-dev-silero"), held_out=False)
    arabic, english, ordinary = card.calls["ar"], card.calls["en"], card.calls["label"]
    assert (arabic.changed, arabic.mixed) == (1, 1)
    assert (english.changed, english.mixed) == (1, 0)
    assert (ordinary.changed, ordinary.mixed) == (0, 1)
    assert arabic.by_language["english"].model_dump() == {"items": 2, "variants": 2, "changed": 1}
    assert arabic.by_language["saudi"].model_dump() == {"items": 3, "variants": 3, "changed": 0}
    assert (call_code("label", "english"), call_code("label", "mixed")) == ("en", "ar")
    assert (call_code("ar", "english"), call_code("en", "none")) == ("ar", "en")


def test_the_paused_requests_are_judged_as_poe_eot_judges_them() -> None:
    results = (*_silero(), result("p2", turn(), kind="paused_request", judged=TIMED))
    paused = card_of(results, run=run_info("p"), held_out=False).paused
    assert (paused.items, paused.variants, paused.cut_offs, paused.misses) == (2, 2, 1, 0)
    assert paused.delay_median_ms == pytest.approx(500.0)


def test_a_turn_the_rule_reads_back_otherwise_than_the_call_named_it_is_counted() -> None:
    """The calls were held in Arabic, so the rule read back for Arabic must give what each
    request named; a record that says otherwise is a fault of the measurement."""
    wrong = (result("s1", turn(named="ar")),)  # classified English, yet named Arabic
    assert card_of(wrong, run=run_info("p"), held_out=False).disagreements == 1
    unsent = turn("session").model_copy(update={"by": None, "named": None})  # never sent
    off = (result("s1", turn("session"), unsent),)
    card = card_of(off, run=run_info("off", classifier="off"), held_out=False)
    assert (card.by, card.disagreements, card.calls["ar"].changed) == (
        {"none": 1, "session": 1},
        0,
        0,
    )
    assert (card.in_time, card.late, card.verdict_median_ms) == (0, 0, None)


def test_a_held_out_pass_keeps_aggregates_only() -> None:
    run = run_info("lid1-held-out-silero", split="held-out")
    results = tuple(r.model_copy(update={"split": "held-out"}) for r in _silero())
    card = scorecard_of(run, results, complete=True)
    assert card.variants == () and all(not c.by_language for c in card.card.calls.values())
    with pytest.raises(ValidationError, match="aggregates"):
        LanguagesScorecard.model_validate(card.model_dump() | {"variants": results})
    assert scorecard_of(run_info("d"), results, complete=True).variants == results


def test_the_history_line_holds_the_pass_numbers() -> None:
    card = scorecard_of(run_info("lid1-dev-silero", peak_mb=412.5), _silero(), complete=True)
    line = line_of(card)
    assert (line.kind, line.run, line.classifier, line.split) == (
        "languages",
        "lid1-dev-silero",
        "silero",
        "dev",
    )
    assert (line.variants, line.turns, line.in_time, line.late, line.cut_offs) == (5, 7, 4, 1, 1)
    assert line.changed == {"label": 0, "ar": 1, "en": 1} and line.mixed["ar"] == 1
    assert (line.peak_mb, line.complete, line.scorecard) == (412.5, True, "scorecard.json")


def _pass(
    name: str, ends: list[list[float]], *, classifier: str = "silero", cut_offs: int = 0
) -> tuple[LanguagesScorecard, tuple[LanguageResult, ...]]:
    """A pass whose variant n's turns end at `ends[n]`, and three paused requests, the first
    `cut_offs` of them cut off."""
    by = "session" if classifier == "off" else "short"
    results = [
        result(f"i{n}", *(turn(by, end_ms=end) for end in turn_ends))
        for n, turn_ends in enumerate(ends)
    ]
    results += [
        result(f"p{n}", kind="paused_request", judged=CUT_OFF if n < cut_offs else TIMED)
        for n in range(3)
    ]
    run = run_info(name, classifier=classifier)
    return scorecard_of(run, tuple(results), complete=True), tuple(results)


OFF_ONE = [[1000.0, 3000.0], [500.0], [700.0]]
OFF_TWO = [[1020.0, 3040.0], [500.0], [700.0, 900.0]]  # its last variant's turns differ


def test_condition_4_reads_each_classifier_pass_against_the_two_off_passes() -> None:
    """The paired differences against the off passes' mean are 90, 40 and 20 ms (median 40);
    the off passes' own, 20, 40 and 0 (median 20); a variant whose turns differ is unpaired."""
    off_one = _pass("off1", OFF_ONE, classifier="off", cut_offs=1)
    off_two = _pass("off2", OFF_TWO, classifier="off")
    near = _pass("silero", [[1100.0, 3060.0], [520.0], [700.0]], cut_offs=2)
    slow = _pass("ecapa", [[1200.0, 3200.0], [600.0], [700.0]], classifier="ecapa", cut_offs=3)
    (first, second) = read_passes([off_one, near, slow, off_two])
    assert (first.run, first.classifier, first.pairs, first.unpaired) == ("silero", "silero", 3, 1)
    assert (first.delay_ms, first.off_ms) == pytest.approx((40.0, 20.0))
    assert (first.cut_offs, first.allowed, first.holds) == (2, 2, True)
    assert second.delay_ms == pytest.approx(180.0)
    assert (second.cut_offs, second.holds) == (3, False)


def test_condition_4_holds_a_delay_within_the_off_passes_own() -> None:
    noisy = _pass("off2", [[1200.0, 3200.0], [600.0], [700.0]], classifier="off")
    off_one = _pass("off1", OFF_ONE, classifier="off")
    within = _pass("silero", [[1170.0, 3170.0], [620.0], [760.0]])
    (reading,) = read_passes([off_one, within, noisy])
    assert reading.delay_ms is not None and reading.delay_ms > 50
    assert reading.off_ms is not None and reading.delay_ms <= reading.off_ms
    assert reading.holds


@pytest.mark.parametrize(
    ("change", "says"),
    [
        ({"commit": "cd" * 20}, "one commit"),
        ({"split": "held-out"}, "one split"),
        ({"data_digest": "0" * 64}, "the same data"),
    ],
)
def test_passes_not_at_one_commit_split_and_data_are_refused(
    change: dict[str, str], says: str
) -> None:
    off_one = _pass("off1", OFF_ONE, classifier="off")
    off_two = _pass("off2", OFF_ONE, classifier="off")
    card, results = _pass("silero", OFF_ONE)
    other = card.model_copy(update={"run": card.run.model_copy(update=change)})
    with pytest.raises(ValueError, match=says):
        read_passes([off_one, (other, results), off_two])


def test_the_reading_needs_two_off_passes_and_complete_passes() -> None:
    off_one = _pass("off1", OFF_ONE, classifier="off")
    silero = _pass("silero", OFF_ONE)
    with pytest.raises(ValueError, match="two off passes"):
        read_passes([off_one, silero])
    card, results = _pass("off2", OFF_ONE, classifier="off")
    unfinished = card.model_copy(update={"complete": False})
    with pytest.raises(ValueError, match="complete"):
        read_passes([off_one, silero, (unfinished, results)])
    off_two = _pass("off2", OFF_ONE, classifier="off")
    fewer = _pass("silero", OFF_ONE[:2])
    with pytest.raises(ValueError, match="the same variants"):
        read_passes([off_one, fewer, off_two])


def test_a_pass_folder_reads_back_and_a_broken_one_is_refused(tmp_path: Path) -> None:
    run = run_info("lid1-dev-silero")
    folder = pass_folder(tmp_path / "lid1-dev-silero", run, _silero())
    card, results = load_pass(folder)
    assert card.run == run and results == _silero()
    (folder / "turns.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(EvalDataError, match=r"turns\.jsonl"):
        load_pass(folder)
    with pytest.raises(EvalDataError, match="scorecard"):
        load_pass(tmp_path / "none")


def test_a_run_record_refuses_a_rule_off_its_bounds() -> None:
    with pytest.raises(ValidationError):
        LanguagesRun.model_validate(run_info("x").model_dump() | {"min_share": 1.5})


def test_the_line_reads_back_from_the_history_and_renders_in_its_own_table(
    tmp_path: Path,
) -> None:
    line = line_of(
        scorecard_of(run_info("lid1-dev-silero", peak_mb=412.5), _silero(), complete=True)
    )
    path = tmp_path / "history.jsonl"
    append_line(line, path)
    assert read_history(path) == (line,)
    page = render_history([line])
    assert "Spend so far: 1 run(s), 0.0 billed seconds, $0.0000." in page
    assert "\n## Each turn's language\n" in page
    assert (
        "| 1 | 2026" in page
        and "| lid1-dev-silero |" in page
        and "| silero | dev | 5 | 7 |" in page
    )
    assert "| Turns chosen classified | 3 |" in page
    assert "| Variants changed, call ar | 1 |" in page
    assert "| Variants whose turns differ, call ar | 1 |" in page
    assert "Price per hour" not in page
