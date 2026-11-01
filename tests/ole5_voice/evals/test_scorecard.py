"""The scorecard: every metric of a made-up run recomputed by hand, the window measures summed,
a held-out run's aggregates only, and a run or a result made with `model_copy` refused before
anything is written (docs/SECURITY.md, invariant 5).

The scorers are stand-ins (`fakes.FakeScorers`, with a value per output), so these tests check
what the scorecard pools and passes, not Track A's scoring; the last test runs the library's own
scorers on a case worked by hand.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from ole5_voice.evals.runs import (
    SCORECARD_FILE,
    Metrics,
    RunInfo,
    Scorecard,
    ScorecardWriter,
    VariantResult,
    WindowMetrics,
)
from ole5_voice.evals.scorecard import STRATA, EvalDataError, quantile, write_scorecard
from t2_agentic_voice.evals import Recall

from tests.ole5_voice.evals import samples
from tests.ole5_voice.evals.fakes import FakeScorers, fake_normalize

MADE_UP_KEY = "gsk_made-up-key-for-tests-0123456789"
HELD_OUT_TEXT = "made-up words heard on a held-out clip"
PRICE = 0.111
PDF, OUTLOOK, TICKET = "send the PDF file", "open Outlook now", "ticket 4821"
# The sample run: item, variant, language, device, kind, reference, what was heard (None for a
# provider failure), the verdict, and the latency of its one answered request of 10 s.
Row = tuple[str, str, str, str, str, str, str | None, bool | None, float]
ROWS: list[Row] = [
    ("i1", "v1", "saudi", "laptop", "request", PDF, "send a PDF file", False, 300),
    ("i1", "v2", "saudi", "wired", "request", PDF, PDF, True, 280),
    ("i2", "v1", "english", "laptop", "ticket_number", TICKET, TICKET, True, 310),
    ("i3", "v1", "none", "laptop", "silence", "", "thank you", False, 250),
    ("i3", "v2", "none", "bluetooth", "silence", "", "", True, 240),
    ("i4", "v1", "english", "bluetooth", "request", "open the report", None, None, 0),
    ("i5", "v1", "mixed", "laptop", "request", OUTLOOK, "open outlet now", False, 320),
    ("i2", "v2", "english", "wired", "ticket_number", TICKET, "ticket 4812", False, 290),
]
# The variants whose requests differ, as (latency ms, billed s, outcome), attempts in order.
REQUESTS: dict[str, list[tuple[float, float, str]]] = {
    "i1/v2": [(50, 0, "rate_limited"), (280, 10, "ok")],
    "i4/v1": [(100, 0, "server_error")] * 4,
    "i5/v1": [(320, 12.5, "ok")],
}
TERMS = {"i1": ["PDF"], "i5": ["Outlook"]}
# What the stand-in scorers give for each output; WER and CER are 0.25 for every pool.
RECALLS = {"send a PDF file": (1, 1), PDF: (1, 1), "open outlet now": (1, 0)}
RECALLS |= {TICKET: (1, 1), "ticket 4812": (1, 0)}
SILENCE = {"thank you": 8, "": 0}
# Every metric, worked by hand from the rows above (cer equals wer, and the cost is the billed
# seconds at $0.111 an hour). A rate leaves out the provider failure; latency is over answered
# requests, linear between ranks: the totals' seven, 240 to 320, give the median 290 and the
# 90th percentile 310 + 0.4 * (320 - 310) = 314.
FIELDS = ["variants", "right", "failures", "accuracy", "wer", "term_recall", "id_recall"]
FIELDS += ["silence_share", "silence_chars", "requests", "retries", "latency_median_ms"]
FIELDS += ["latency_p90_ms", "billed_seconds"]
EXPECTED: dict[tuple[str, str], tuple[float | None, ...]] = {
    ("totals", ""): (8, 3, 1, 3 / 7, 0.25, 2 / 3, 1 / 2, 1 / 2, 8, 12, 4, 290, 314, 72.5),
    ("language", "english"): (3, 1, 1, 1 / 2, 0.25, None, 1 / 2, None, 0, 6, 3, 300, 308, 20),
    ("language", "mixed"): (1, 0, 0, 0.0, 0.25, 0.0, None, None, 0, 1, 0, 320, 320, 12.5),
    ("language", "none"): (2, 1, 0, 1 / 2, None, None, None, 1 / 2, 8, 2, 0, 245, 249, 20),
    ("language", "saudi"): (2, 1, 0, 1 / 2, 0.25, 1.0, None, None, 0, 3, 1, 290, 298, 20),
    ("device", "bluetooth"): (2, 1, 1, 1.0, None, None, None, 0.0, 0, 5, 3, 240, 240, 10),
    ("device", "laptop"): (4, 1, 0, 1 / 4, 0.25, 1 / 2, 1.0, 1.0, 8, 4, 0, 305, 317, 42.5),
    ("device", "wired"): (2, 1, 0, 1 / 2, 0.25, 1.0, 0.0, None, 0, 3, 1, 285, 289, 20),
    ("kind", "request"): (4, 1, 1, 1 / 3, 0.25, 2 / 3, None, None, 0, 8, 4, 300, 316, 32.5),
    ("kind", "silence"): (2, 1, 0, 1 / 2, None, None, None, 1 / 2, 8, 2, 0, 245, 249, 20),
    ("kind", "ticket_number"): (2, 1, 0, 1 / 2, 0.25, None, 1 / 2, None, 0, 2, 0, 300, 308, 20),
    ("split", "dev"): (8, 3, 1, 3 / 7, 0.25, 2 / 3, 1 / 2, 1 / 2, 8, 12, 4, 290, 314, 72.5),
}
# The items each covers, counted by hand, not its variants: i1 to i5 in all, English i2 and i4.
ITEMS = dict(zip(EXPECTED, [5, 2, 1, 1, 1, 2, 4, 2, 3, 1, 1, 5], strict=True))


class LookupScorers(FakeScorers):
    """`FakeScorers` whose recall and silence values are looked up by the output scored, so
    each result gets its own; every call is recorded."""

    def __init__(self) -> None:
        super().__init__(rate=0.25)
        self.recalls = {output: Recall(expected=e, found=f) for output, (e, f) in RECALLS.items()}
        self.silences = dict(SILENCE)

    def term_recall(self, reference: str, output: str, terms: Sequence[str]) -> Recall:
        super().term_recall(reference, output, terms)
        return self.recalls[output]

    def id_recall(self, reference: str, output: str) -> Recall:
        super().id_recall(reference, output)
        return self.recalls[output]

    def silence_output(self, output: str) -> int:
        super().silence_output(output)
        return self.silences[output]


def _result(row: Row, **more: object) -> VariantResult:
    item, variant, language, device, kind, reference, heard, right, latency = row
    requests = REQUESTS.get(f"{item}/{variant}", [(latency, 10.0, "ok")])
    answer = {
        "variant": variant,
        "text": heard,
        "failure": "provider" if heard is None and right is None else None,
        "requests": [
            {"segment": 0, "attempt": n, "latency_ms": ms, "billed_seconds": s, "outcome": o}
            for n, (ms, s, o) in enumerate(requests, start=1)
        ],
    }
    fields: dict[str, object] = {"item": item, "variant": variant, "split": "dev", "right": right}
    fields |= {"language": language, "device": device, "kind": kind, "reference": reference}
    return VariantResult.model_validate(
        fields | {"answer": answer, "terms": TERMS.get(item, [])} | more
    )


def _run(**fields: object) -> RunInfo:
    return RunInfo.model_validate(
        samples.run().model_dump() | {"price_per_hour_usd": PRICE} | fields
    )


def _card(
    out: Path,
    results: Sequence[VariantResult] | None = None,
    scorers: FakeScorers | None = None,
    *,
    run: RunInfo | None = None,
    complete: bool = True,
) -> Scorecard:
    return write_scorecard(
        run or _run(),
        [_result(row) for row in ROWS] if results is None else results,
        complete=complete,
        out=out,
        scorers=scorers or LookupScorers(),
        normalize=fake_normalize,
    )


def test_write_scorecard_is_a_scorecard_writer() -> None:
    writer: ScorecardWriter = write_scorecard
    assert writer is write_scorecard
    assert list(STRATA) == ["language", "device", "kind", "split"]


def test_every_metric_is_recomputed_by_hand(tmp_path: Path) -> None:
    card = _card(tmp_path)
    found = {("totals", ""): card.totals} | {
        (stratum, value): metrics
        for stratum, values in card.breakdowns.items()
        for value, metrics in values.items()
    }
    assert list(found) == list(EXPECTED)
    for key, numbers in EXPECTED.items():
        fields = dict(zip(FIELDS, numbers, strict=True))
        cost = (fields["billed_seconds"] or 0.0) / 3600 * PRICE
        more = {"cer": fields["wer"], "cost_usd": cost, "items": ITEMS[key]}
        expected = Metrics.model_validate(fields | more)
        assert found[key].model_dump() == pytest.approx(expected.model_dump()), key
    assert (card.violations, card.speakers, card.complete) == (0, "one speaker", True)
    assert card.violations_reason == "no hard constraint applies to speech-to-text"


def test_wer_and_cer_pool_the_judged_variants_with_a_reference(tmp_path: Path) -> None:
    scorers = LookupScorers()
    _card(tmp_path, scorers=scorers)
    calls = [args for name, args in scorers.calls if name == "wer"]
    assert [args for name, args in scorers.calls if name == "cer"] == calls
    # The totals first, in the results' order: no failure, no empty reference.
    assert calls[0] == (
        (PDF, PDF, TICKET, OUTLOOK, TICKET),
        ("send a PDF file", PDF, TICKET, "open outlet now", "ticket 4812"),
    )
    # Then each stratum value with such a variant: english, mixed and saudi (not none); laptop
    # and wired (not bluetooth); request and ticket_number; dev.
    assert len(calls) == 1 + 3 + 2 + 2 + 1
    assert calls[1:3] == [
        ((TICKET, TICKET), (TICKET, "ticket 4812")),
        ((OUTLOOK,), ("open outlet now",)),
    ]
    assert calls[-1] == calls[0]
    # Each result is scored once, whatever its strata.
    assert [args for name, args in scorers.calls if name == "silence_output"] == [
        ("thank you",),
        ("",),
    ]
    assert [args for name, args in scorers.calls if name == "term_recall"] == [
        (PDF, "send a PDF file", ("PDF",)),
        (PDF, PDF, ("PDF",)),
        (OUTLOOK, "open outlet now", ("Outlook",)),
    ]
    assert [args[1] for name, args in scorers.calls if name == "id_recall"] == [
        TICKET,
        "ticket 4812",
    ]


def test_the_scorecard_is_written_whole_and_reads_back(tmp_path: Path) -> None:
    out = tmp_path / "run" / "r1"
    out.mkdir(parents=True)
    (out / SCORECARD_FILE).write_text("an earlier scorecard of the same run", encoding="utf-8")
    card = _card(out, complete=False)
    data = (out / SCORECARD_FILE).read_bytes()
    assert data == (card.model_dump_json(indent=2) + "\n").encode("utf-8")
    assert b"\r" not in data
    assert Scorecard.model_validate_json(data) == card
    assert (card.complete, len(card.variants)) == (False, 8)
    assert [path.name for path in out.iterdir()] == [SCORECARD_FILE]  # no partial file left
    fresh = tmp_path / "new" / "folder"
    _card(fresh)
    assert (fresh / SCORECARD_FILE).is_file()


# A run that sent only the windows: item, language, want, reference, failure, and each window
# as (ms, words heard, leading words, holds the one-word reference, reused).
Clip = tuple[str, str, str | None, str, str | None, list[tuple[int, int, int, bool | None, bool]]]
CLIPS: list[Clip] = [
    ("t1", "saudi", "send", PDF, None, [(500, 2, 1, None, False), (750, 3, 2, None, False)]),
    ("t5", "saudi", "send", PDF, None, [(500, 0, 0, None, False), (750, 4, 4, None, True)]),
    (
        "t2",
        "english",
        "greet",
        "hello",
        None,
        [(500, 1, 1, True, False), (750, 1, 0, False, False)],
    ),
    ("t3", "english", "greet", "hello", "stuck", [(500, 1, 1, True, False)]),
    ("t4", "msa", None, "two words", None, [(500, 0, 0, None, False)]),
]


def test_a_run_of_windows_only_sums_each_windows_measures(tmp_path: Path) -> None:
    results = [
        _result(
            (item, "v1", language, "laptop", "request", reference, "", None, 200),
            judged=False,
            want=want,
            answer={
                "variant": "v1",
                "failure": failure,
                "requests": [
                    {
                        "segment": 0,
                        "attempt": 1,
                        "latency_ms": 200,
                        "billed_seconds": 10,
                        "outcome": "ok",
                    }
                ]
                * len(windows),
                "windows": [
                    {
                        "ms": ms,
                        "text": "x" * words,
                        "empty": not words,
                        "words": words,
                        "leading_words": leading,
                        "holds_word": holds,
                        "reused": reused,
                    }
                    for ms, words, leading, holds, reused in windows
                ],
            },
        )
        for item, language, want, reference, failure, windows in CLIPS
    ]
    scorers = LookupScorers()
    card = _card(tmp_path, results, scorers)
    names = ["items", "clips", "empty", "reused", "words", "leading_words", "reference_words"]
    names += ["one_word_clips", "holds_word"]
    assert card.windows == tuple(  # the stuck clip's window is left out
        WindowMetrics.model_validate(
            {"ms": ms, "language": language, "want": want} | dict(zip(names, counts, strict=True))
        )
        for ms, language, want, *counts in [
            (500, "english", "greet", 1, 1, 0, 0, 1, 1, 1, 1, 1),
            (500, "msa", None, 1, 1, 1, 0, 0, 0, 2, 0, 0),
            (500, "saudi", "send", 2, 2, 1, 0, 2, 1, 8, 0, 0),
            (750, "english", "greet", 1, 1, 0, 0, 1, 0, 1, 1, 0),
            (750, "saudi", "send", 2, 2, 0, 1, 7, 6, 8, 0, 0),
        ]
    )
    # Nothing was judged: no verdict, no rate and no scorer called; the requests still count.
    assert card.totals == Metrics(
        items=5,
        variants=5,
        right=0,
        failures=1,
        requests=8,
        latency_median_ms=200.0,
        latency_p90_ms=200.0,
        billed_seconds=80.0,
        cost_usd=80 / 3600 * PRICE,
    )
    assert scorers.calls == []


def test_a_held_out_scorecard_holds_aggregates_only(tmp_path: Path) -> None:
    def held_out(row: Row) -> VariantResult:
        result = _result(row, split="held-out")
        if result.answer.text is None:
            return result
        answer = result.answer.model_dump() | {"text": HELD_OUT_TEXT}
        return VariantResult.model_validate(result.model_dump() | {"answer": answer})

    scorers = LookupScorers()
    scorers.recalls = {HELD_OUT_TEXT: Recall(expected=1, found=1)}
    scorers.silences = {HELD_OUT_TEXT: len(HELD_OUT_TEXT)}
    results = [held_out(row) for row in ROWS]
    card = _card(tmp_path, results, scorers, run=_run(split="held-out"))
    assert (card.variants, card.totals.variants, card.totals.failures) == ((), 8, 1)
    assert card.breakdowns["split"] == {"held-out": card.totals}
    written = (tmp_path / SCORECARD_FILE).read_text(encoding="utf-8")
    assert HELD_OUT_TEXT not in written
    assert '"v1"' not in written and '"i1"' not in written  # no variant or item named


def test_results_of_another_split_or_scored_twice_are_refused(tmp_path: Path) -> None:
    results = [_result(row) for row in ROWS]
    for refused, problem in (
        ([*results, _result(ROWS[0], variant="v9", split="held-out")], "its own split"),
        ([*results, results[0]], "each variant once"),
    ):
        with pytest.raises(EvalDataError, match=problem):
            _card(tmp_path, refused)
    assert not (tmp_path / SCORECARD_FILE).exists()


def test_a_run_or_result_made_with_model_copy_is_refused_and_never_written(
    tmp_path: Path,
) -> None:
    """`model_copy(update=...)` skips the checks; the writer checks again, so a secret setting's
    value, a traced held-out run or a verdict on a failure never reaches the file, and the error
    holds none of it, not even in its chain."""
    results = [_result(row) for row in ROWS]
    secret = _run().model_copy(update={"settings": {"groq.api_key": MADE_UP_KEY}})
    traced = _run().model_copy(update={"split": "held-out", "traced": True})
    failed = results[5].model_copy(update={"right": True})
    for run, given in ((secret, results), (traced, []), (_run(), [*results[:5], failed])):
        with pytest.raises(EvalDataError) as raised:
            _card(tmp_path, given, run=run)
        error = raised.value
        assert error.code == "eval_data_invalid"
        assert error.__cause__ is None and error.__context__ is None
        assert MADE_UP_KEY not in f"{error} {error!r} {error.details} {error.args}"
    assert not tmp_path.joinpath(SCORECARD_FILE).exists()


def test_the_quantile_interpolates_between_ranks() -> None:
    assert quantile([], 0.5) is None
    assert quantile([7.0], 0.9) == 7.0
    assert quantile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5  # the median of an even count
    assert quantile([float(n) for n in range(1, 11)], 0.9) == pytest.approx(9.1)
    assert quantile([1.0, 2.0], 1.0) == 2.0


def test_the_librarys_scorers_score_a_case_worked_by_hand(tmp_path: Path) -> None:
    """The default scorers and normalizer, the library's `evals` and `languages`: WER 1 of 5
    words; CER, spaces removed, 3 of 22 characters ("the" for "a": one substitution and two
    deletions); the one term heard."""
    results = [
        _result(
            ("i1", "v1", "english", "laptop", "request", "send the file", "send a file", False, 300)
        ),
        _result(
            ("i6", "v1", "english", "laptop", "request", "open outlook", "open outlook", True, 300),
            terms=["outlook"],
        ),
    ]
    card = write_scorecard(samples.run(), results, complete=True, out=tmp_path)
    assert card.totals.wer == pytest.approx(1 / 5)
    assert card.totals.cer == pytest.approx(3 / 22)
    assert (card.totals.accuracy, card.totals.term_recall) == (0.5, 1.0)
