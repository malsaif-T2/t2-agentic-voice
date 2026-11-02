"""`poe eval-compare`: fixed, broken and net per variant, the sign test by item against
evaluation.md's formula, the stratum guard and the smallest detectable change as the plan's
registration defines them, `--focus`, infrastructure failures left out and listed, held-out runs
by aggregates only, and two runs that differ in commit, data or split refused. The report names
variants by ID and never holds what was heard."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from ole5_voice.evals import compare
from ole5_voice.evals.compare import (
    ByItem,
    Change,
    ComparisonError,
    by_item,
    pair,
    smallest_change,
    stratum_guard,
)
from ole5_voice.evals.runs import SCORECARD_FILE, Metrics, RunInfo, Scorecard, VariantResult
from ole5_voice.evals.scorecard import EvalDataError, load_scorecard

from tests.ole5_voice.evals import samples
from tests.ole5_voice.evals.fakes import FakeSignTest

HEARD = "made-up words heard"


def exact_sign_test(better: int, worse: int) -> float:
    """evaluation.md's formula, the oracle these tests check the counts with:
    p = min(1, 2 * sum over i <= min(b, w) of C(b + w, i) / 2^(b + w))."""
    n = better + worse
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(better, worse) + 1)) / (1 << n))


def _result(
    item: str,
    variant: str,
    right: bool | None,
    *,
    language: str = "saudi",
    device: str = "laptop",
    failure: str | None = None,
    judged: bool = True,
) -> VariantResult:
    answered = right is not None
    return VariantResult.model_validate(
        {
            "item": item,
            "variant": variant,
            "split": "dev",
            "kind": "request",
            "language": language,
            "device": device,
            "reference": "a made-up reference",
            "answer": {
                "variant": variant,
                "text": f"{HEARD} {item} {variant}" if answered else None,
                "failure": failure,
            },
            "judged": judged,
            "right": right,
        }
    )


def _card(
    results: list[VariantResult],
    *,
    name: str = "r1",
    split: str = "dev",
    accuracy: float | None = 0.5,
    items: int | None = None,
    **run: object,
) -> Scorecard:
    info = RunInfo.model_validate(
        samples.run(name).model_dump() | {"split": split, "model": "whisper-large-v3"} | run
    )
    covered = len({result.item for result in results}) if items is None else items
    totals = Metrics(
        items=covered, variants=len(results) or covered, right=1, failures=0, accuracy=accuracy
    )
    return Scorecard(
        run=info,
        complete=True,
        totals=totals,
        breakdowns={"language": {"saudi": totals}} if accuracy is not None else {},
        variants=tuple(results),
    )


def test_the_oracle_is_evaluation_mds_formula() -> None:
    assert exact_sign_test(6, 0) == 2 / 64 == 0.03125
    assert exact_sign_test(5, 0) == 0.0625
    assert exact_sign_test(3, 3) == exact_sign_test(0, 0) == 1.0


def test_each_variant_is_fixed_broken_the_same_or_left_out_and_listed() -> None:
    a = _card(
        [
            _result("i1", "v1", False),
            _result("i1", "v2", True),
            _result("i2", "v1", True),
            _result("i3", "v1", None, failure="provider"),
            _result("i4", "v1", True),
            _result("i5", "v1", None, judged=False),
            _result("i6", "v1", True),
        ]
    )
    b = _card(
        [
            _result("i1", "v1", True),
            _result("i1", "v2", False),
            _result("i2", "v1", True),
            _result("i3", "v1", True),
            _result("i4", "v1", None, failure="stuck"),
            _result("i5", "v1", False),
            _result("i7", "v1", True),
        ],
        name="r2",
    )
    changes, left_out = pair(a, b)
    assert changes == [
        Change("i1", "v1", "saudi", "laptop", 1),
        Change("i1", "v2", "saudi", "laptop", -1),
        Change("i2", "v1", "saudi", "laptop", 0),
    ]
    assert left_out == [
        ("i3/v1", "a provider failure in A"),
        ("i4/v1", "stuck past its time limit in B"),
        ("i5/v1", "not judged"),
        ("i6/v1", "in A only"),
        ("i7/v1", "in B only"),
    ]
    both = _card([_result("i3", "v1", None, failure="provider")], name="r2")
    assert pair(both, both)[1] == [("i3/v1", "a provider failure in A; a provider failure in B")]
    # i1's two variants cancel out: unchanged, with i2.
    assert by_item(changes, exact_sign_test) == ByItem(items=2, better=0, worse=0, p=1.0)


def _guard_runs() -> tuple[Scorecard, Scorecard]:
    """20 items: six Saudi ones fixed on the laptop; six English ones broken on the Bluetooth
    headset; one MSA item fixed on the laptop and broken on the wired headset; seven mixed ones
    on the wired headset, four fixed and three broken."""
    a: list[VariantResult] = []
    b: list[VariantResult] = []

    def add(item: str, variant: str, before: bool, after: bool, language: str, device: str) -> None:
        a.append(_result(item, variant, before, language=language, device=device))
        b.append(_result(item, variant, after, language=language, device=device))

    for n in range(6):
        add(f"s{n}", "v1", False, True, "saudi", "laptop")
        add(f"e{n}", "v1", True, False, "english", "bluetooth")
    add("m1", "v1", False, True, "msa", "laptop")
    add("m1", "v2", True, False, "msa", "wired")
    for n in range(7):
        add(f"x{n}", "v1", n >= 4, n < 4, "mixed", "wired")
    return _card(a), _card(b, name="r2")


def test_the_stratum_guard_takes_each_devices_variants_only() -> None:
    changes, _ = pair(*_guard_runs())
    guard = stratum_guard(changes, exact_sign_test)
    rows = {(stratum, value): (r, reading) for stratum, value, r, reading in guard}
    worse_6, better_6, better_7 = exact_sign_test(0, 6), exact_sign_test(6, 0), 2 / 128
    assert rows == {
        ("language", "english"): (ByItem(6, 0, 6, worse_6), "worse in B beyond the noise"),
        ("language", "mixed"): (ByItem(7, 4, 3, 1.0), "within the noise"),
        ("language", "msa"): (ByItem(1, 0, 0, 1.0), "too small to guard"),  # its net is 0
        ("language", "saudi"): (ByItem(6, 6, 0, better_6), "better in B beyond the noise"),
        ("device", "bluetooth"): (ByItem(6, 0, 6, worse_6), "worse in B beyond the noise"),
        # m1 is better on the laptop and worse on the wired headset.
        ("device", "laptop"): (ByItem(7, 7, 0, better_7), "better in B beyond the noise"),
        ("device", "wired"): (ByItem(8, 4, 4, 1.0), "within the noise"),
    }
    whole = by_item(changes, exact_sign_test)
    assert whole == ByItem(items=20, better=10, worse=9, p=1.0)


def test_a_stratum_of_five_changed_items_is_too_small_to_guard() -> None:
    five = [Change(f"i{n}", "v1", "saudi", "laptop", 1) for n in range(5)]
    assert stratum_guard(five, exact_sign_test)[0][2:] == (
        ByItem(5, 5, 0, 0.0625),
        "too small to guard",
    )


def test_the_smallest_detectable_change_follows_the_registration() -> None:
    # No noise: b = 6, w = 0 gives 2/64 < 0.05, and b = 5 gives 0.0625.
    assert smallest_change(0, 10, exact_sign_test) == 6
    assert smallest_change(0, 5, exact_sign_test) is None  # five items cannot show it
    # Three items changed by noise: b = c + 1, w = 2. For c = 8, p = 2 * (1 + 11 + 55) / 2^11
    # = 0.0654; for c = 9, p = 2 * (1 + 12 + 66) / 2^12 = 0.0386.
    assert exact_sign_test(9, 2) > 0.05 > exact_sign_test(10, 2)
    assert smallest_change(3, 20, exact_sign_test) == 9
    assert smallest_change(3, 11, exact_sign_test) is None  # only 8 unchanged items to add


def test_the_report_gives_every_count_and_never_a_transcript() -> None:
    a, b = _guard_runs()
    report = compare.compare(a, b, sign_test=exact_sign_test, focus=["s0", "e0", "m1"])
    assert "# r2 judged against r1\n" in report
    assert (
        "Compared 21 variant(s) of 20 item(s): fixed 11, broken 10, net +1; unchanged 0." in report
    )
    assert "Fixed (wrong in A, right in B): m1/v1, s0/v1, s1/v1, s2/v1, s3/v1, s4/v1, " in report
    assert "Broken (right in A, wrong in B): e0/v1, e1/v1, e2/v1, e3/v1, e4/v1, e5/v1, " in report
    assert "Left out of both runs: 0." in report
    assert "Items better 10, worse 9, unchanged 1: p = 1.0000, within the noise" in report
    # 19 of the 20 items changed, so one is left to add: b = 1 + 9 against w = 10 is p = 1.
    assert "19 item(s) changed, so the smallest change one run can detect is more than" in report
    assert "| device | laptop | 7 | 7 | 0 | 0.0156 | better in B beyond the noise |" in report
    assert "## Focus: 3 item(s), shown apart" in report
    assert "Variants: fixed 2, broken 2, net +0; unchanged 0." in report
    assert "Items better 1, worse 1, unchanged 1: p = 1.0000" in report
    assert "| accuracy | 0.5000 | 0.5000 | +0.0000 |" in report
    assert "| variants | 21 | 21 | +0 |" in report
    assert "| language | saudi | 0.5000 | 0.5000 | +0.0000 |" in report
    assert "one speaker" in report and HEARD not in report


def test_settings_that_differ_are_named_and_a_missing_stratum_shows_a_dash() -> None:
    a = _card([_result("i1", "v1", False)], settings={"stt.model": "whisper-large-v3"})
    turbo = {"stt.model": "whisper-large-v3-turbo", "groq.api_key": "set"}
    b = _card([_result("i1", "v1", True)], name="r2", settings=turbo, accuracy=None)
    report = compare.compare(a, b, sign_test=FakeSignTest(1.0))
    assert (
        "Settings that differ: groq.api_key (unset in A, set in B); "
        "stt.model (whisper-large-v3 in A, whisper-large-v3-turbo in B)."
    ) in report
    assert "| language | saudi | 0.5000 | — | — |" in report
    assert "| accuracy | 0.5000 | — | — |" in report
    assert "Fixed (wrong in A, right in B): i1/v1\nBroken (right in A, wrong in B): none" in report


def test_runs_that_differ_in_commit_data_or_split_are_refused() -> None:
    a = _card([])
    cases: list[tuple[dict[str, Any], str]] = [
        ({"commit": "1234567"}, "their commits differ (A 0f44056, B 1234567)"),
        ({"data_digest": "f" * 64}, "their data digests differ"),
        ({"split": "held-out", "items": 3}, "their splits differ (A dev, B held-out)"),
    ]
    for change, named in cases:
        b = _card([], name="r2", **change)
        with pytest.raises(ComparisonError, match=re.escape(named)):
            compare.compare(a, b, sign_test=FakeSignTest())
    both = _card([], name="r2", commit="1234567", split="held-out", items=3)
    with pytest.raises(ComparisonError, match=r"commits differ .*; their splits differ"):
        compare.compare(a, both, sign_test=FakeSignTest())


def test_held_out_runs_are_compared_by_aggregates_only() -> None:
    a = _card([], split="held-out", items=3)
    b = _card([], name="h2", split="held-out", accuracy=0.75, items=3)
    report = compare.compare(a, b, sign_test=FakeSignTest())
    assert "compared by aggregates only: no variant, no item" in report
    assert "## Variant by variant" not in report and "sign test" not in report
    assert "| accuracy | 0.5000 | 0.7500 | +0.2500 |" in report
    with pytest.raises(ComparisonError, match="aggregates only: no --focus"):
        compare.compare(a, b, sign_test=FakeSignTest(), focus=["i1"])


def test_a_focus_item_in_neither_run_is_refused() -> None:
    a = _card([_result("i1", "v1", True)])
    with pytest.raises(ComparisonError, match="1 item"):
        compare.compare(a, a, sign_test=FakeSignTest(), focus=["i1", "i9"])


def _write(card: Scorecard, folder: Path) -> Path:
    folder.mkdir(parents=True)
    (folder / SCORECARD_FILE).write_text(card.model_dump_json(), encoding="utf-8")
    return folder


def test_a_scorecard_is_read_strictly_from_its_folder_or_file(tmp_path: Path) -> None:
    card = _card([_result("i1", "v1", True)])
    folder = _write(card, tmp_path / "r1")
    assert load_scorecard(folder) == load_scorecard(folder / SCORECARD_FILE) == card
    (tmp_path / "bad.json").write_bytes(b"\xff not text")
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    for path, problem in (
        (tmp_path / "missing", "not a readable scorecard"),
        (tmp_path / "bad.json", "not a readable scorecard"),
        (tmp_path / "broken.json", "not a valid scorecard"),
    ):
        with pytest.raises(EvalDataError, match=problem):
            load_scorecard(path)


def test_a_held_out_scorecard_holding_a_variant_is_refused_unread(tmp_path: Path) -> None:
    """A held-out scorecard holds aggregates only; one that holds a variant (written by hand, or
    by a `model_copy`) is refused as it is read, and nothing of the variant is shown."""
    crafted = json.loads(_card([], split="held-out", items=3).model_dump_json())
    variant = _result("i1", "v1", True).model_dump(mode="json") | {"split": "held-out"}
    (tmp_path / "card.json").write_text(json.dumps(crafted | {"variants": [variant]}), "utf-8")
    with pytest.raises(EvalDataError, match="aggregates only") as raised:
        load_scorecard(tmp_path / "card.json")
    assert HEARD not in str(raised.value) and raised.value.__context__ is None


def test_a_scorecard_listing_a_variant_twice_is_refused_as_it_is_read(tmp_path: Path) -> None:
    """Pairing would keep the last copy silently, while the file's totals counted both."""
    crafted = json.loads(_card([_result("i1", "v1", False)]).model_dump_json())
    twice = [*crafted["variants"], _result("i1", "v1", True).model_dump(mode="json")]
    (tmp_path / "card.json").write_text(json.dumps(crafted | {"variants": twice}), "utf-8")
    with pytest.raises(EvalDataError, match="each variant once") as raised:
        load_scorecard(tmp_path / "card.json")
    assert HEARD not in str(raised.value)


def test_eval_compare_prints_its_report_or_its_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first = _write(_card([_result("i1", "v1", False)]), tmp_path / "r1")
    second = _write(_card([_result("i1", "v1", True)], name="r2"), tmp_path / "r2")
    focus = tmp_path / "focus.txt"
    focus.write_text("# the items the change aims at\n\ni1\n", encoding="utf-8")
    sign_test = FakeSignTest(0.5)
    args = [str(first), str(second), "--focus", str(focus)]
    assert compare.main(args, sign_test=sign_test) == 0
    out = capsys.readouterr().out
    assert out.startswith("# r2 judged against r1\n") and "## Focus: 1 item(s)" in out
    assert (1, 0) in sign_test.calls  # i1 is better
    other = _write(_card([], name="r3", commit="1234567"), tmp_path / "r3")
    assert compare.main([str(first), str(other)], sign_test=sign_test) == 1
    captured = capsys.readouterr()
    assert "comparison_not_made" in captured.out and "code=comparison_refused" in captured.out
    assert "the runs cannot be compared: their commits" in captured.out
    assert "# " not in captured.out and captured.err == ""  # a log line, and no report
    assert compare.main([str(first), str(second), "--focus", str(tmp_path / "none")]) == 1
    assert "not a readable focus file" in capsys.readouterr().out


def test_eval_compare_logs_as_the_library_logs_in_a_new_process(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], new_process_logs: Callable[[str, str], str]
) -> None:
    """eval-compare configures logging before it logs, as `poe eval` does (plan 004, app21)."""
    assert compare.main([str(tmp_path / "r1"), str(tmp_path / "r2")]) == 1
    assert "[error" in new_process_logs(capsys.readouterr().out, "comparison_not_made")


def test_the_librarys_sign_test_judges_a_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The default sign test, the library's `evals.sign_test`: six items better and none worse
    give 2/64."""
    first = _write(_card([_result(f"i{n}", "v1", False) for n in range(6)]), tmp_path / "r1")
    better = _card([_result(f"i{n}", "v1", True) for n in range(6)], name="r2")
    second = _write(better, tmp_path / "r2")
    assert compare.main([str(first), str(second)]) == 0
    assert "p = 0.0312, beyond the noise" in capsys.readouterr().out
