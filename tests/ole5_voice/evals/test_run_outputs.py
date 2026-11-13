"""What every run writes alike: a file written whole (`files.write_whole`, `write_json`: a
partial file first, then moved into place, so an interrupted write leaves no half file), its
history line recorded twice (`history.record_line`: the worktree's history and a copy beside the
scorecard), and the history page's tables, each header with the separator its columns need
(`history_tables.table`, `block`, `ruled`)."""

from __future__ import annotations

from pathlib import Path

from ole5_voice.evals import files, history, history_tables
from ole5_voice.evals.models import Model


class _Card(Model):
    name: str
    count: int


def test_a_file_is_written_whole_and_replaces_an_earlier_one(tmp_path: Path) -> None:
    (tmp_path / "scorecard.json").write_text("an earlier run's", encoding="utf-8")
    files.write_json(tmp_path, "scorecard.json", _Card(name="مثال", count=2))
    written = (tmp_path / "scorecard.json").read_bytes()
    assert written == '{\n  "name": "مثال",\n  "count": 2\n}\n'.encode()
    files.write_whole(tmp_path, "turns.jsonl", "one\ntwo\n")
    assert (tmp_path / "turns.jsonl").read_bytes() == b"one\ntwo\n"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["scorecard.json", "turns.jsonl"]


def test_a_runs_line_is_recorded_in_the_history_and_beside_its_scorecard(tmp_path: Path) -> None:
    appended: list[tuple[str, Path]] = []
    history.record_line(
        lambda line, path: appended.append((line, path)), "a line", tmp_path / "d", tmp_path / "o"
    )
    assert appended == [
        ("a line", tmp_path / "d" / "history.jsonl"),
        ("a line", tmp_path / "o" / "history.jsonl"),
    ]


def test_each_table_has_the_separator_its_columns_need() -> None:
    assert history_tables.ruled("| a | b | c |") == "| a | b | c |\n| --- | --- | --- |"
    rows = ["| 1 | 2 |"]
    assert history_tables.table("Runs", "| a | b |", rows) == [
        "\n## Runs\n",
        "| a | b |\n| --- | --- |",
        "| 1 | 2 |",
    ]
    assert history_tables.block("| a | b |", rows) == ["", "| a | b |\n| --- | --- |", "| 1 | 2 |"]
    assert history_tables.table("Runs", "| a |", []) == history_tables.block("| a |", []) == []
