"""A held-out run's groups of fewer than 3 items (plan 002's registration, "Amendments",
2026-11-01): in its scorecard's breakdowns and window groups, its history line and the page it
renders, and `eval-compare`, every value that covers fewer than `HELD_OUT_MIN_ITEMS` answered
items is pooled into one group, `OTHER`, itself left out when it too covers fewer, and a rate of
a group shown that is taken over fewer items is left out. Items are counted, not variants, and an
item whose every variant failed is not counted; the totals are whole; a dev run shows every group
and every rate; a scorecard or history line holding a smaller held-out group is refused as it is
read; and `eval-compare` shows a held-out group only over the same items with no failure, and
refuses two held-out runs that cover different variants.

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
from ole5_voice.evals.compare import ComparisonError, load_scorecard
from ole5_voice.evals.history import append_line, line_of, read_history, render_history
from ole5_voice.evals.models import OTHER, TICKET_KIND
from ole5_voice.evals.runs import (
    HELD_OUT_MIN_ITEMS,
    SCORECARD_FILE,
    HistoryLine,
    Metrics,
    RunInfo,
    Scorecard,
    StratumValue,
    VariantResult,
)
from ole5_voice.evals.scorecard import EvalDataError, write_scorecard
from t2_agentic_voice.evals import Recall

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
    rows: list[Row],
    split: str = "held-out",
    right: Callable[[int], bool] = lambda n: n % 2 == 0,
    failed: Callable[[str, int], bool] = lambda item, n: False,
) -> list[VariantResult]:
    """Each row's variants, on the laptop, each judged (`right` by its number) and with one
    window of 500 ms, but those `failed` names, a provider's failure with no window."""
    window = {"ms": 500, "text": "x", "empty": False, "words": 1, "leading_words": 0}

    def answer(item: str, n: int) -> dict[str, object]:
        if failed(item, n):
            return {"variant": f"v{n}", "failure": "provider"}
        return {"variant": f"v{n}", "text": f"{HEARD} {item}", "windows": [window]}

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
                "answer": answer(item, n),
                "right": None if failed(item, n) else right(n),
            }
        )
        for item, language, kind, want, variants in rows
        for n in range(variants)
    ]


def _card(
    out: Path,
    results: list[VariantResult],
    *,
    split: str = "held-out",
    name: str = "h1",
    scorers: FakeScorers | None = None,
) -> Scorecard:
    run = RunInfo.model_validate(samples.run(name).model_dump() | {"split": split})
    return write_scorecard(
        run,
        results,
        complete=True,
        out=out,
        scorers=scorers or FakeScorers(rate=0.25),
        normalize=fake_normalize,
    )


def _items(breakdowns: dict[str, dict[str, Metrics]]) -> dict[str, dict[str, int]]:
    return {s: {value: m.items for value, m in values.items()} for s, values in breakdowns.items()}


def test_a_held_out_runs_groups_under_3_items_are_pooled_into_other(tmp_path: Path) -> None:
    card = _card(tmp_path, _results(HELD_OUT))
    assert (HELD_OUT_MIN_ITEMS, OTHER) == (3, "other")
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


def test_an_item_whose_every_variant_failed_is_not_counted(tmp_path: Path) -> None:
    """With English's h04 and h05 failing in every variant, English's accuracy would be h07's
    alone: it covers one answered item, so it is pooled, and `OTHER` covers 4 (h07, h09, h10,
    h13), not 6. Listening sounds keep 3 answered items of 4, and are shown."""
    lost = _results(HELD_OUT, failed=lambda item, n: item in ("h04", "h05"))
    card = _card(tmp_path, lost)
    assert _items(card.breakdowns) == {
        "language": {"saudi": 7, OTHER: 4},
        "device": {"laptop": 11},
        "kind": {"listening_sound": 3, "request": 4, OTHER: 4},
        "split": {"held-out": 11},
    }
    language = card.breakdowns["language"][OTHER]
    assert (language.variants, language.failures, language.right) == (18, 6, 7)
    assert (card.totals.items, card.totals.variants, card.totals.failures) == (11, 36, 6)
    assert [(w.language, w.want, w.items) for w in card.windows] == [
        ("saudi", "listen", 3),
        ("saudi", "send", 3),
        (OTHER, None, 5),  # h06, h07, h09, h10 and h13: the failures' windows are left out
    ]


# English's 3 items hold one rate each: e1 a product term, e2 a ticket number (both with a
# reference, for WER), e3 silence; e1 alone has a one-word window. Saudi's 3 all hold terms and
# one-word windows. Item, language, kind, reference, whether it holds a term.
RATES: list[tuple[str, str, str, str, bool]] = [
    ("e1", "english", "request", "send the PDF", True),
    ("e2", "english", TICKET_KIND, "ticket 4821", False),
    ("e3", "english", "silence", "", False),
    *((f"s{n}", "saudi", "request", "send the PDF", True) for n in "123"),
]


def _rated(split: str) -> list[VariantResult]:
    """`RATES`' items, two variants each, all right, a term's item with a one-word window."""
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
                "want": "send",
                "reference": reference,
                "terms": ["PDF"] if term else [],
                "answer": {
                    "variant": f"v{n}",
                    "text": f"{HEARD} {item}",
                    "windows": [window | {"holds_word": True} if term else window],
                },
                "right": True,
            }
        )
        for item, language, kind, reference, term in RATES
        for n in range(2)
    ]


def test_a_held_out_groups_rate_over_fewer_than_3_items_is_left_out(tmp_path: Path) -> None:
    """English covers 3 items, but its WER rests on 2 of them, its term recall on e1 alone (as
    the committed split's s04_pdf is its only held-out item with a product term), its ID recall
    on e2 and its text from silence on e3: each is left out. Saudi's, over 3 items, are shown;
    the totals are whole; a dev run shows every rate."""
    scorers = FakeScorers(rate=0.25, recall=Recall(expected=1, found=1), silence=5)
    held_out = _card(tmp_path / "h1", _rated("held-out"), scorers=scorers)
    dev = _card(tmp_path / "r1", _rated("dev"), split="dev", name="r1", scorers=scorers)
    rates = ("wer", "cer", "term_recall", "id_recall", "silence_share", "silence_chars")

    def shown(metrics: Metrics) -> tuple[object, ...]:
        return tuple(getattr(metrics, rate) for rate in rates)

    english = held_out.breakdowns["language"]["english"]
    assert (english.items, english.accuracy) == (3, 1.0)
    assert shown(english) == (None, None, None, None, None, 0)
    assert shown(held_out.breakdowns["language"]["saudi"])[:3] == (0.25, 0.25, 1.0)
    # The laptop's 6 items: WER over 5 and terms over 4 are shown, the ticket and silence not.
    assert shown(held_out.breakdowns["device"]["laptop"]) == (0.25, 0.25, 1.0, None, None, 0)
    assert shown(held_out.totals) == shown(dev.totals) == (0.25, 0.25, 1.0, 1.0, 1.0, 10)
    assert shown(dev.breakdowns["language"]["english"]) == (0.25, 0.25, 1.0, 1.0, 1.0, 10)
    # The one-word windows of English's group are e1's alone; Saudi's are of 3 items.
    found = {(w.language, w.one_word_clips, w.holds_word) for w in held_out.windows}
    assert found == {("english", 0, 0), ("saudi", 6, 6)}
    assert {(w.language, w.one_word_clips) for w in dev.windows} == {("english", 2), ("saudi", 6)}


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
    # A group of one variant claiming 3 items, edited by hand, is refused too.
    claimed = one_item | {"items": 3, "variants": 1, "right": 1, "failures": 0}
    crafted.write_text(json.dumps(written | {"breakdowns": {"language": {"mixed": claimed}}}))
    with pytest.raises(EvalDataError, match="answered variants"):
        load_scorecard(crafted)


def test_a_held_out_history_line_holds_no_smaller_group(tmp_path: Path) -> None:
    card = _card(tmp_path / "h1", _results(HELD_OUT))
    line = line_of(card, items=13, billed_seconds=0.0, cost_usd=0.0)
    found = {s: {v: x.items for v, x in values.items()} for s, values in line.breakdowns.items()}
    assert found == _items(card.breakdowns)
    assert line.breakdowns["kind"][OTHER] == StratumValue(items=4, accuracy=0.5)
    page = render_history([line])
    assert "| language | other | 3 | 60.0% |" in page
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
    assert "at least 3, with no failure" in report
    # A smaller group that skipped the checks (`model_copy`) is not shown either.
    one = Metrics(items=1, variants=3, right=2, failures=0, accuracy=2 / 3)
    copied = a.model_copy(update={"breakdowns": {"language": {"mixed": one}}})
    assert "| language | mixed |" not in compare.compare(copied, copied, sign_test=FakeSignTest())


def test_eval_compare_sets_side_by_side_only_held_out_groups_with_no_failure(
    tmp_path: Path,
) -> None:
    """In B, h04 and h05 fail in every variant and one of h01's variants fails: English is
    pooled in B alone, the languages' `OTHER` and two kinds cover other items in B, and Saudi
    keeps its 7 items with a failure, so its accuracy is over other variants: none of them is
    set against A's. The kinds' `OTHER`, of the same 4 items and variants in both, is."""
    a = _card(tmp_path / "h1", _results(HELD_OUT))

    def failed(item: str, n: int) -> bool:
        return item in ("h04", "h05") or (item, n) == ("h01", 0)

    b = _card(tmp_path / "h2", _results(HELD_OUT, failed=failed), name="h2")
    assert b.breakdowns["language"]["saudi"].items == a.breakdowns["language"]["saudi"].items
    report = compare.compare(a, b, sign_test=FakeSignTest())
    strata = [line for line in report.splitlines() if line.startswith(("| language", "| kind"))]
    assert strata == [f"| kind | {OTHER} | 0.5000 | 0.5000 | +0.0000 |"]
    assert "| device | " not in report and "| split | " not in report
    assert "| failures | 0 | 7 | +7 |" in report  # the totals are whole
    # Two held-out runs that cover different variants are refused: B - A of their totals would
    # be the numbers of the variants one holds alone.
    grown = _results([*HELD_OUT, ("h14", "mixed", "request", "send", 1)])
    with pytest.raises(
        ComparisonError, match=r"different variants cannot be compared \(A 36, B 37\)"
    ):
        compare.compare(a, _card(tmp_path / "h3", grown, name="h3"), sign_test=FakeSignTest())
