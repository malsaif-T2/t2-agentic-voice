"""The run history and `poe eval-history`: lines appended with LF endings, only to a well-formed
history and only after their own checks (a secret setting's value never reaches the committed
file: docs/SECURITY.md, invariant 5); the page rendered from it, with a run's own text escaped;
and the freshness test of `docs/generated/eval-history.md` (GP-11)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from ole5_voice.evals import history
from ole5_voice.evals.history import append_line, line_of, read_history, render_history
from ole5_voice.evals.runs import SCORECARD_FILE, HistoryLine, Metrics, Scorecard
from ole5_voice.evals.scorecard import EvalDataError

from scripts.check_docs import PLACEHOLDER, extract_links
from tests.ole5_voice.evals import samples

MADE_UP_KEY = "gsk_made-up-key-for-tests-0123456789"
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


def _line(name: str = "r1", **fields: object) -> HistoryLine:
    return HistoryLine.model_validate(samples.history_line(name).model_dump() | fields)


def _json(line: HistoryLine) -> bytes:
    return line.model_dump_json().encode("utf-8") + b"\n"


def test_lines_are_appended_one_per_line_with_lf_endings(tmp_path: Path) -> None:
    path = tmp_path / "history.jsonl"
    first, second = _line("r1"), _line("r2", note="the second run\nof two", accuracy=None)
    append_line(first, path)  # the file is created
    append_line(second, path)
    assert path.read_bytes() == _json(first) + _json(second)
    assert read_history(path) == (first, second)
    empty = tmp_path / "empty.jsonl"
    empty.write_bytes(b"")
    append_line(first, empty)
    assert read_history(empty) == (first,)


@pytest.mark.parametrize(
    "existing",
    [
        b'{"not": "a history line"}\n',
        b"\n",  # a blank line
        b"\xff\xfe\n",  # not UTF-8
        _json(_line()).rstrip(b"\n"),  # no LF at its end
        _json(_line()).replace(b"\n", b"\r\n"),  # a CRLF ending
    ],
)
def test_a_line_is_appended_only_to_a_well_formed_history(tmp_path: Path, existing: bytes) -> None:
    path = tmp_path / "history.jsonl"
    path.write_bytes(existing)
    with pytest.raises(EvalDataError, match=re.escape(str(path))):
        append_line(_line("r2"), path)
    assert path.read_bytes() == existing  # unchanged


def test_a_line_made_with_model_copy_is_checked_again_before_it_is_written(
    tmp_path: Path,
) -> None:
    """`model_copy(update=...)` skips the checks; a secret setting's value would otherwise reach
    the committed history. The error holds no value, not even in its chain."""
    path = tmp_path / "history.jsonl"
    for change in ({"settings": {"groq.api_key": MADE_UP_KEY}}, {"cost_usd": -1.0}):
        with pytest.raises(EvalDataError) as raised:
            append_line(_line().model_copy(update=change), path)
        error = raised.value
        assert (error.code, error.__cause__, error.__context__) == ("eval_data_invalid", None, None)
        assert MADE_UP_KEY not in f"{error} {error!r} {error.details}"
    assert not path.exists()


def test_reading_names_the_bad_line_never_its_text(tmp_path: Path) -> None:
    path = tmp_path / "history.jsonl"
    leaked = samples.history_line().model_dump(mode="json") | {"settings": {"api_key": MADE_UP_KEY}}
    path.write_bytes(_json(_line()) + json.dumps(leaked).encode("utf-8") + b"\n")
    with pytest.raises(EvalDataError, match="line 2") as raised:
        read_history(path)
    assert MADE_UP_KEY not in str(raised.value)
    assert raised.value.__context__ is None
    with pytest.raises(EvalDataError, match="not a readable"):
        read_history(tmp_path / "missing.jsonl")


def test_a_scorecard_gives_its_history_line() -> None:
    totals = Metrics(
        variants=4,
        right=2,
        failures=1,
        accuracy=2 / 3,
        latency_median_ms=290.0,
        billed_seconds=40.0,
        cost_usd=40 / 3600 * 0.111,
    )
    english = Metrics(variants=4, right=2, failures=1, accuracy=2 / 3)
    run = samples.run().model_copy(update={"model": "whisper-large-v3"})
    card = Scorecard(
        run=run, complete=False, totals=totals, breakdowns={"language": {"english": english}}
    )
    line = line_of(card, items=3)
    assert line.model_dump() == {
        "time": run.started_at,
        "commit": run.commit,
        "run": run.name,
        "answerer": run.answerer,
        "model": "whisper-large-v3",
        "settings": run.settings,
        "split": "dev",
        "items": 3,
        "variants": 4,
        "accuracy": 2 / 3,
        "violations": 0,
        "billed_seconds": 40.0,
        "price_per_hour_usd": run.price_per_hour_usd,
        "cost_usd": 40 / 3600 * 0.111,
        "latency_median_ms": 290.0,
        "breakdowns": {"language": {"english": 2 / 3}},
        "scorecard": SCORECARD_FILE,
        "data_digest": run.data_digest,
        "note": run.note,
        "complete": False,
    }


def test_the_page_says_no_runs_yet_for_an_empty_history() -> None:
    page = render_history([])
    assert page.startswith("# Run history\n\nGenerated by `uv run poe eval-history`")
    assert page.endswith("\n\nNo runs yet.\n")
    assert "one speaker" in page


def test_the_page_shows_the_spend_each_run_and_its_strata() -> None:
    dev = _line(
        "r1",
        answerer="groq",
        model="whisper-large-v3",
        settings={"groq.api_key": "set", "stt.model": "whisper-large-v3"},
        accuracy=0.41,
        billed_seconds=1960.0,
        price_per_hour_usd=0.111,
        cost_usd=1960 / 3600 * 0.111,
        latency_median_ms=295.4,
        breakdowns={"language": {"saudi": 0.3, "english": None}},
    )
    held_out = _line("h1", split="held-out", complete=False, billed_seconds=840.0, cost_usd=0.04)
    page = render_history([dev, held_out])
    assert "Spend so far: 2 run(s), 2800.0 billed seconds, $0.1004.\n" in page
    assert (
        "| 1 | 2026-11-03T09:00:00+00:00 | r1 | 0f44056 | groq | whisper-large-v3 | dev | 1 | 1 "
        "| 41.0% | 0 | 1960.0 | $0.0604 | 295 | yes |"
    ) in page
    assert "| 2 | 2026-11-03T09:00:00+00:00 | h1 | 0f44056 | reference | — | held-out |" in page
    assert page.count("| no |") == 1  # the held-out run did not complete
    assert "### 1 · r1\n\n| Field | Value |\n| --- | --- |\n| Why | a made-up run |" in page
    assert "| Setting groq.api_key | set |" in page and MADE_UP_KEY not in page
    assert "| Price per hour of audio | $0.111 |" in page
    assert "| language | english | — |\n| language | saudi | 30.0% |" in page
    assert page.count("| Stratum | Value | Accuracy |") == 1  # none for a run with none
    assert "\r" not in page and page.endswith("|\n")


def test_a_runs_own_text_is_escaped_so_it_renders_as_text(tmp_path: Path) -> None:
    """A note or setting holding Markdown never makes a link, an HTML tag, a placeholder the
    docs check would flag, or a table cell of its own."""
    placeholder = "{{" + "NAME" + "}}"  # written apart, or the docs check flags this file
    note = f"see [the plan](missing.md) | <script>x</script> {placeholder} `c` *b*\nnext line"
    assert PLACEHOLDER.search(note)  # unescaped, the docs check would flag it
    line = _line(note=note, settings={"odd|name": "a [b](c.md)"}, model="m|odd")
    page = render_history([line])
    md = tmp_path / "docs" / "generated" / "eval-history.md"
    md.parent.mkdir(parents=True)
    md.write_text(page, encoding="utf-8", newline="\n")
    assert [link.raw for link in extract_links(md, tmp_path)] == ["README.md"]
    assert PLACEHOLDER.search(page) is None and "<script>" not in page
    why = next(row for row in page.splitlines() if row.startswith("| Why |"))
    assert len(_UNESCAPED_PIPE.findall(why)) == 3  # two cells, nothing more
    assert "next line" in why
    setting = next(row for row in page.splitlines() if row.startswith("| Setting"))
    assert setting == r"| Setting odd\|name | a \[b\]\(c.md\) |"
    run = next(row for row in page.splitlines() if row.startswith("| 1 |"))
    assert len(_UNESCAPED_PIPE.findall(run)) == 16 and r"m\|odd" in run  # 15 cells


def test_eval_history_renders_the_given_history(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source, page = tmp_path / "history.jsonl", tmp_path / "eval-history.md"
    append_line(_line(), source)
    assert history.main(["--history", str(source), "--out", str(page)]) == 0
    assert page.read_bytes() == render_history(read_history(source)).encode("utf-8")
    assert capsys.readouterr().out == f"eval-history: wrote {page} (1 run(s))\n"


def test_eval_history_refuses_a_bad_history_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source, page = tmp_path / "history.jsonl", tmp_path / "eval-history.md"
    source.write_bytes(b"{}\n")
    assert history.main(["--history", str(source), "--out", str(page)]) == 1
    assert "line 1: not a history line" in capsys.readouterr().err
    assert not page.exists()


def test_the_committed_history_page_is_fresh() -> None:
    """The freshness test (GP-11): the committed page is what the committed history renders."""
    assert history.HISTORY.is_file() and history.DOC.parent.name == "generated"
    expected = render_history(read_history(history.HISTORY)).encode("utf-8")
    assert history.DOC.read_bytes() == expected, (
        "docs/generated/eval-history.md is stale.\n"
        "    FIX: run `uv run poe eval-history`, then commit the page with the history."
    )
