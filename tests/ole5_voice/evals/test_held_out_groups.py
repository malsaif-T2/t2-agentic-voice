"""A held-out run's groups of fewer than 3 items (plan 002's registration, "Amendments",
2026-11-01): in its scorecard's breakdowns and window groups, its history line and the page it
renders, and `eval-compare`, every value that covers fewer than `HELD_OUT_MIN_ITEMS` items is
pooled into one group, `OTHER`, itself left out when it too covers fewer. Items are counted, not
variants; the totals are whole; a dev run shows every group; and a scorecard or history line
holding a smaller held-out group is refused as it is read.

The made-up held-out set has the committed split's held-out strata (`split.json` and `golden/`,
read 2026-11-01): 13 items of 36 variants, `mixed`, `confirmation` and `short_request` one item
each, and 7 of its 9 window groups of one item.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from ole5_voice.evals import compare
from ole5_voice.evals.compare import load_scorecard
from ole5_voice.evals.history import append_line, line_of, read_history, render_history
from ole5_voice.evals.runs import (
    HELD_OUT_MIN_ITEMS,
    OTHER,
    SCORECARD_FILE,
    HistoryLine,
    Metrics,
    RunInfo,
    Scorecard,
    StratumValue,
    VariantResult,
)
from ole5_voice.evals.scorecard import EvalDataError, write_scorecard

from tests.ole5_voice.evals import samples
from tests.ole5_voice.evals.fakes import FakeScorers, FakeSignTest, fake_normalize

HEARD = "made-up words heard"
# Each item's language, kind, `want` label and number of variants, as the committed split's 13
# held-out items have them; the IDs are made up.
Row = tuple[str, str, str, str, int]
HELD_OUT: list[Row] = [
    ("h01", "saudi", "listening_sound", "listen", 6),
    ("h02", "saudi", "listening_sound", "listen", 2),
    ("h03", "saudi", "listening_sound", "listen", 2),
    ("h04", "english", "listening_sound", "listen", 3),
    ("h05", "english", "request", "send", 3),
    ("h06", "saudi", "stop_word", "stop", 2),
    ("h07", "english", "stop_word", "stop", 2),
    ("h08", "saudi", "short_request", "send", 2),
    ("h09", "mixed", "request", "send", 3),
    ("h10", "msa", "request", "send", 3),
    ("h11", "saudi", "request", "send", 2),
    ("h12", "saudi", "request", "send", 2),
    ("h13", "msa", "confirmation", "submit", 4),
]
# The values that cover fewer than 3 of those items: mixed 1, msa 2, stop_word 2 and one each.
SMALL = ("mixed", "msa", "stop_word", "short_request", "confirmation")


def _results(
    rows: list[Row], split: str = "held-out", right: Callable[[int], bool] = lambda n: n % 2 == 0
) -> list[VariantResult]:
    """Each row's variants, on the laptop, each judged (`right` by its number) and with one
    window of 500 ms."""
    window = {"ms": 500, "text": "x", "empty": False, "words": 1, "leading_words": 0}
    return [
        VariantResult.model_validate(
            {
                "item": item,
                "variant": f"v{n}",
                "split": split,
                "kind": kind,
                "language": language,
                "device": "laptop",
                "want": want,
                "reference": "a made-up reference",
                "answer": {"variant": f"v{n}", "text": f"{HEARD} {item}", "windows": [window]},
                "right": right(n),
            }
        )
        for item, language, kind, want, variants in rows
        for n in range(variants)
    ]


def _card(
    out: Path, results: list[VariantResult], *, split: str = "held-out", name: str = "h1"
) -> Scorecard:
    run = RunInfo.model_validate(samples.run(name).model_dump() | {"split": split})
    return write_scorecard(
        run,
        results,
        complete=True,
        out=out,
        scorers=FakeScorers(rate=0.25),
        normalize=fake_normalize,
    )


def _items(breakdowns: dict[str, dict[str, Metrics]]) -> dict[str, dict[str, int]]:
    return {s: {value: m.items for value, m in values.items()} for s, values in breakdowns.items()}


def test_a_held_out_runs_groups_under_3_items_are_pooled_into_other(tmp_path: Path) -> None:
    card = _card(tmp_path, _results(HELD_OUT))
    assert HELD_OUT_MIN_ITEMS == 3
    # English, of exactly 3 items, is shown; so is an `OTHER` of exactly 3, mixed's and msa's.
    # Mixed is pooled though its one item has 3 variants: items are counted, not variants.
    assert _items(card.breakdowns) == {
        "language": {"english": 3, "saudi": 7, OTHER: 3},
        "device": {"laptop": 13},
        "kind": {"listening_sound": 4, "request": 5, OTHER: 4},
        "split": {"held-out": 13},
    }
    # Pooled from those items' variants as any group is: 2 of 3, 2 of 3 and 2 of 4 right.
    language = card.breakdowns["language"][OTHER]
    assert (language.variants, language.right, language.accuracy) == (10, 6, 0.6)
    kind = card.breakdowns["kind"][OTHER]
    assert (kind.variants, kind.right, kind.accuracy) == (10, 5, 0.5)
    # The window groups of one length, 7 of 9 of one item each, pooled as one, last.
    assert [(w.ms, w.language, w.want, w.items, w.clips) for w in card.windows] == [
        (500, "saudi", "listen", 3, 10),
        (500, "saudi", "send", 3, 6),
        (500, OTHER, None, 7, 20),
    ]
    assert (card.totals.items, card.totals.variants, card.totals.right) == (13, 36, 20)
    written = (tmp_path / SCORECARD_FILE).read_text(encoding="utf-8")
    assert [small for small in SMALL if f'"{small}"' in written] == []
    assert '"english"' in written and HEARD not in written


def test_an_other_of_fewer_than_3_items_is_left_out(tmp_path: Path) -> None:
    """Saudi's 3 items are shown; English's and msa's one item each pool into an `OTHER` of 2,
    left out, and so on for the kinds and the window groups. The totals keep every item."""
    rows = [*HELD_OUT[:3], HELD_OUT[4], HELD_OUT[9]]
    card = _card(tmp_path, _results(rows))
    assert _items(card.breakdowns) == {
        "language": {"saudi": 3},
        "device": {"laptop": 5},
        "kind": {"listening_sound": 3},
        "split": {"held-out": 5},
    }
    assert [(w.language, w.want, w.items) for w in card.windows] == [("saudi", "listen", 3)]
    assert (card.totals.items, card.totals.variants) == (5, 16)
    tiny = _card(tmp_path / "tiny", _results(HELD_OUT[3:5]))
    assert _items(tiny.breakdowns) == {"language": {}, "device": {}, "kind": {}, "split": {}}
    assert (tiny.windows, tiny.totals.items) == ((), 2)


def test_a_dev_run_shows_every_group_with_the_same_totals(tmp_path: Path) -> None:
    dev = _card(tmp_path / "dev", _results(HELD_OUT, "dev"), split="dev", name="r1")
    assert _items(dev.breakdowns) == {
        "language": {"english": 3, "mixed": 1, "msa": 2, "saudi": 7},
        "device": {"laptop": 13},
        "kind": {
            "confirmation": 1,
            "listening_sound": 4,
            "request": 5,
            "short_request": 1,
            "stop_word": 2,
        },
        "split": {"dev": 13},
    }
    assert [(w.language, w.items) for w in dev.windows] == [
        ("english", 1),
        ("english", 1),
        ("english", 1),
        ("mixed", 1),
        ("msa", 1),
        ("msa", 1),
        ("saudi", 3),
        ("saudi", 3),
        ("saudi", 1),
    ]
    held_out = _card(tmp_path / "held-out", _results(HELD_OUT))
    assert held_out.totals == dev.totals


def test_a_held_out_scorecard_holding_a_smaller_group_is_refused_as_it_is_read(
    tmp_path: Path,
) -> None:
    card = _card(tmp_path, _results(HELD_OUT))
    assert load_scorecard(tmp_path) == card
    written = json.loads((tmp_path / SCORECARD_FILE).read_text(encoding="utf-8"))
    one_item = written["breakdowns"]["language"][OTHER] | {"items": 1}
    two_items = written["windows"][0] | {"items": 2}
    crafted = tmp_path / "crafted.json"
    for change in (
        {"breakdowns": written["breakdowns"] | {"language": {"mixed": one_item}}},
        {"windows": [two_items]},
    ):
        crafted.write_text(json.dumps(written | change), encoding="utf-8")
        with pytest.raises(EvalDataError, match="at least 3 items") as raised:
            load_scorecard(crafted)
        assert raised.value.__context__ is None
        # A dev run's scorecard holds every group, whatever its size.
        dev = written | change | {"run": written["run"] | {"split": "dev"}}
        assert Scorecard.model_validate_json(json.dumps(dev))


def test_a_held_out_history_line_holds_no_smaller_group(tmp_path: Path) -> None:
    card = _card(tmp_path / "h1", _results(HELD_OUT))
    line = line_of(card, items=13, billed_seconds=0.0, cost_usd=0.0)
    found = {s: {v: x.items for v, x in values.items()} for s, values in line.breakdowns.items()}
    assert found == _items(card.breakdowns)
    assert line.breakdowns["kind"][OTHER] == StratumValue(items=4, accuracy=0.5)
    page = render_history([line])
    assert "| language | \\(other\\) | 3 | 60.0% |" in page
    assert [small for small in SMALL if f"| {small} |" in page] == []
    # Read back or written, a held-out line with a smaller group is refused; a dev line is not.
    path, fresh = tmp_path / "history.jsonl", tmp_path / "fresh.jsonl"
    small = line.model_dump(mode="json")
    small["breakdowns"]["language"]["mixed"] = {"items": 1, "accuracy": 1.0}
    path.write_bytes(json.dumps(small).encode("utf-8") + b"\n")
    with pytest.raises(EvalDataError, match=r"line 1: .*at least 3 items"):
        read_history(path)
    mixed = {"language": {"mixed": StratumValue(items=1, accuracy=1.0)}}
    with pytest.raises(EvalDataError, match="at least 3 items"):
        append_line(line.model_copy(update={"breakdowns": mixed}), fresh)
    assert not fresh.exists()
    assert HistoryLine.model_validate(small | {"split": "dev"}).breakdowns["language"]["mixed"]


def test_eval_compare_shows_no_smaller_group_of_two_held_out_runs(tmp_path: Path) -> None:
    a = _card(tmp_path / "h1", _results(HELD_OUT))
    b = _card(tmp_path / "h2", _results(HELD_OUT, right=lambda n: n == 0), name="h2")
    report = compare.compare(a, b, sign_test=FakeSignTest())
    assert f"| language | {OTHER} | 0.6000 | 0.3000 | -0.3000 |" in report
    assert "| language | english | " in report  # exactly 3 items
    assert "| kind | listening_sound | " in report and f"| kind | {OTHER} | " in report
    assert [small for small in SMALL if f"| {small} |" in report] == []
    assert "| items | 13 | 13 | +0 |" in report and HEARD not in report
    # B - A is taken only between groups over the same items: with one more mixed request in
    # B, its `OTHER` language and its requests cover an item A's do not, and are not shown.
    grown = _results([*HELD_OUT, ("h14", "mixed", "request", "send", 1)])
    report = compare.compare(a, _card(tmp_path / "h3", grown, name="h3"), sign_test=FakeSignTest())
    assert f"| language | {OTHER} |" not in report and "| kind | request |" not in report
    assert "| language | english | " in report and f"| kind | {OTHER} | " in report
    # A smaller group that skipped the checks (`model_copy`) is not shown either.
    one = Metrics(items=1, variants=3, right=2, failures=0, accuracy=2 / 3)
    copied = a.model_copy(update={"breakdowns": {"language": {"mixed": one}}})
    assert "| language | mixed |" not in compare.compare(copied, copied, sign_test=FakeSignTest())
