"""What run K0 produces (knowledge_depth_card.py, Q20): the numbers at each k by item, each item
weighing its variants' share once; the keep rule, reckoned exactly at its margin; failures left
out; no k kept by a run that did not finish; and its history line, a kind of its own, read back
and rendered by `poe eval-history` with no price and no cost."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

import pytest
from ole5_voice.evals.history import append_line, read_history, render_history
from ole5_voice.evals.knowledge_depth_card import (
    DepthLine,
    DepthRecord,
    DepthRun,
    depth_line,
    scorecard,
)
from ole5_voice.evals.run_folder import history_accepts, requests_today
from pydantic import ValidationError

from tests.ole5_voice.evals import samples
from tests.ole5_voice.evals.test_history_measures import talker_line

RUN = DepthRun(
    name="k0-a",
    started_at=samples.WHEN,
    commit="0f44056",
    settings={"run.depth": "8", "run.passage_chars": "1500"},
    data_digest=samples.SHA,
    note="K0, the passages' depth",
)


def _record(
    item: str,
    places: Sequence[int | None],
    *,
    variant: str = "v1",
    expected: Sequence[str] = ("guide-001",),
    failure: str | None = None,
) -> DepthRecord:
    """A record whose n-th passage found is point `places[n]` (None: a passage the set does not
    hold), each passage 100 characters."""
    points = tuple(None if n is None else f"guide-{n:03d}" for n in places)
    return DepthRecord(
        item=item,
        variant=variant,
        language="english",
        expected=tuple(expected),
        passages=tuple(f"made-up/chunk_{n}" for n, _ in enumerate(points)),
        points=points,
        chars=(100,) * len(points),
        failure=failure,  # type: ignore[arg-type]
    )


def _ranked(at_one: int, later: dict[int, int], misses: int) -> list[DepthRecord]:
    """One-variant items whose one expected point is first for `at_one` of them, at place p for
    `later[p]` of them, and nowhere for `misses`."""
    places = [1] * at_one + [p for p, n in later.items() for _ in range(n)] + [None] * misses
    return [
        _record(f"i{n:02d}", [None] * (place - 1) + [1] if place else [2, 3])
        for n, place in enumerate(places)
    ]


@pytest.mark.parametrize("first", [17, 7])
def test_a_share_on_the_margin_is_kept_exactly(first: int) -> None:
    # Found at k = 1 by `first` of 20 items, at k = 8 by one more: exactly 0.05 below, which
    # float arithmetic misses for 7 of 20 (0.35) against 8 of 20 (0.4).
    card = scorecard(RUN, _ranked(first, {5: 1}, 19 - first), complete=True, stopped=None)
    assert card.depths[0].found == first / 20 and card.depths[-1].found == (first + 1) / 20
    assert card.kept_k == 1


def test_the_smallest_k_within_the_margin_is_kept() -> None:
    # 0.8 at k = 1 is past 0.05 below 0.9; 0.85 at k = 2 is within it.
    card = scorecard(RUN, _ranked(16, {2: 1, 5: 1}, 2), complete=True, stopped=None)
    assert [at.found for at in card.depths][:5] == pytest.approx([0.8, 0.85, 0.85, 0.85, 0.9])
    assert card.kept_k == 2


def test_each_item_weighs_its_variants_share_once() -> None:
    records = [
        _record("a1", [1], variant="v1"),
        _record("a1", [2, 1], variant="v2"),
        _record("a2", [1, 2], expected=("guide-001", "guide-002")),
    ]
    card = scorecard(RUN, records, complete=True, stopped=None)
    one, two = card.depths[0], card.depths[1]
    assert one.hit == pytest.approx((1 / 2 + 1) / 2)  # not 2 of 3 variants
    assert one.found == pytest.approx((1 / 2 + 1 / 2) / 2)  # a2: one of its two points
    assert (two.hit, two.found) == (1, 1)
    assert (one.chars_median, one.chars_most) == (100, 100)
    assert (two.chars_median, two.chars_p90, two.chars_most) == (200, 200, 200)
    assert card.depths[-1].chars_most == 200  # no variant found more than two passages


def test_a_failed_search_is_left_out_and_a_run_that_did_not_finish_keeps_no_k() -> None:
    records = [_record("a1", [2, 1]), _record("a2", [], failure="provider")]
    card = scorecard(RUN, records, complete=True, stopped=None)
    assert (card.items, card.variants, card.failures) == (1, 2, 1)
    assert card.depths[0].found == 0 and card.kept_k == 2
    assert scorecard(RUN, records, complete=False, stopped="interrupted").kept_k is None
    empty = scorecard(RUN, records[1:], complete=True, stopped=None)
    assert empty.kept_k is None and empty.depths[0].found is None
    assert empty.depths[0].chars_median is None and empty.depths[0].chars_most is None


def test_a_record_has_a_point_and_characters_for_each_passage_and_a_failure_none() -> None:
    with pytest.raises(ValidationError, match="a point and characters for each passage"):
        DepthRecord.model_validate({**_record("a1", [1]).model_dump(), "chars": []})
    with pytest.raises(ValidationError, match="a failed search found no passage"):
        _record("a1", [1], failure="stuck")


def _line(**changes: object) -> DepthLine:
    records = [_record("a1", [3, 1]), _record("a2", [1])]
    return depth_line(scorecard(RUN, records, complete=True, stopped=None)).model_copy(
        update=changes
    )


def test_the_line_is_a_kind_of_its_own_read_back_and_rendered(tmp_path: Path) -> None:
    path = tmp_path / "history.jsonl"
    line, talker = _line(), talker_line()
    for each in (line, talker):
        assert history_accepts(each)
        append_line(each, path)
    assert read_history(path) == (line, talker)
    assert json.loads(path.read_text("utf-8").splitlines()[0])["kind"] == "knowledge_depth"
    assert requests_today(path, samples.WHEN.date()) == Counter(talker.requests)  # K0 sends none
    page = render_history([line, talker])
    # K0 sends no chat request: its line adds no cost, and its section shows no price.
    assert f"Spend so far: 2 run(s), 0.0 billed seconds, ${talker.cost_usd:.4f}." in page
    assert "## Knowledge-depth runs" in page
    # Kept: k = 2, whose share of points found is k = 8's; its characters' median is a1's two
    # passages and a2's one.
    assert (
        "| 1 | 2026-11-03T09:00:00+00:00 | k0-a | 0f44056 | dev | 2 | 2 | 0 | 2 | 100.0% "
        "| 100.0% | 150 | yes |"
    ) in page
    assert "| 1 | 50.0% | 50.0% | 100 | 100 | 100 |" in page
    assert "| 2 | 100.0% | 100.0% | 150 | 190 | 200 |" in page
    section = page.split("### 1 · k0-a")[1].split("### 2 ·")[0]
    assert "Price" not in section and "| Setting run.depth | 8 |" in section
    unkept = render_history([_line(kept_k=None, complete=False, stopped="interrupted")])
    assert "| 2 | 2 | 0 | — | — | 100.0% | — | no |" in unkept


def test_a_line_holds_dev_only_and_a_k_within_the_depth() -> None:
    raw = json.loads(_line().model_dump_json())
    with pytest.raises(ValidationError):
        DepthLine.model_validate(raw | {"split": "held-out"})
    with pytest.raises(ValidationError):
        DepthLine.model_validate(raw | {"kept_k": 9})
