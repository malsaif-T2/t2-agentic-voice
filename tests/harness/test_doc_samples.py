"""DOC-SAMPLE (scripts/doc_samples.py): a code block after a link to a `.py` file is a run of that
file's lines, so a page never shows code its source no longer holds. On small repositories built
in a temporary folder, with the synthetic config of support.py."""

from __future__ import annotations

from pathlib import Path

from scripts.check_docs import check_repo
from tests.harness.support import config, doc_rules, write

SOURCE = '''\
"""A tested file."""


def test_a_ruling() -> None:
    ruling = {
        "id": "term",

        "write": "Outlook",
    }
    assert ruling
'''
SAMPLE = '```python\nruling = {\n  "id": "term",\n  "write": "Outlook",\n}\n```\n'
GUIDE = "docs/guide.md"
TEST = "../tests/test_rulings.py"  # the source, as the guide links it


def _guide(*parts: str) -> dict[str, str]:
    return {
        "CLAUDE.md": f"[guide]({GUIDE})",
        GUIDE: "".join(parts),
        "tests/test_rulings.py": SOURCE,
    }


def _line(text: str, start: str, after: int = 0) -> int:
    """The number of the first line after line `after` that starts with `start`."""
    lines = text.splitlines()
    return next(n for n in range(after + 1, len(lines) + 1) if lines[n - 1].startswith(start))


def test_a_sample_matches_its_source_indentation_and_blank_lines_aside(tmp_path: Path) -> None:
    files = _guide(f"From [the test]({TEST}):\n\n", SAMPLE)
    assert doc_rules(tmp_path, files) == []


def test_a_sample_that_drifted_from_its_source_is_reported(tmp_path: Path) -> None:
    drifted = SAMPLE.replace('"write": "Outlook"', '"write": "outlook"')
    files = _guide(f"From [the test]({TEST}):\n\n", drifted)
    line = _line(files[GUIDE], '  "write"')
    assert doc_rules(tmp_path, files) == [(GUIDE, line, "DOC-SAMPLE")]
    violations, _ = check_repo(write(tmp_path, files), config(tmp_path))
    assert '`"write": "outlook",`' in violations[0].problem
    assert "tests/test_rulings.py" in violations[0].problem


def test_nothing_may_be_elided_and_the_order_holds(tmp_path: Path) -> None:
    elided = SAMPLE.replace('  "id": "term",\n', "  ...\n")
    reordered = '```python\n"write": "Outlook",\n"id": "term",\n```\n'
    files = _guide(f"[a]({TEST})\n\n", elided, f"\n[b]({TEST})\n\n", reordered)
    text = files[GUIDE]
    lines = [_line(text, "  ..."), _line(text, '"id"', _line(text, "[b]"))]
    assert doc_rules(tmp_path, files) == [(GUIDE, n, "DOC-SAMPLE") for n in lines]


def test_a_block_with_no_py_link_before_it_is_no_sample(tmp_path: Path) -> None:
    files = _guide(
        f"[the test]({TEST}), and a block after it:\n\n```\nanything = 1\n```\n\n",
        "Another block, with no link of its own:\n\n```\nmore = 2\n```\n",
        "\n[a page](x.md) is no source:\n\n```\nthird = 3\n```\n",
    )
    files["docs/x.md"] = ""
    found = _line(files[GUIDE], "anything")
    assert doc_rules(tmp_path, files) == [(GUIDE, found, "DOC-SAMPLE")]


def test_history_keeps_its_samples(tmp_path: Path) -> None:
    drifted = SAMPLE.replace("Outlook", "Gmail")
    files = {
        **_guide(),
        "CLAUDE.md": f"[guide]({GUIDE}) [history](docs/plans/completed/)",
        "docs/plans/completed/001-old.md": "[t](../../../tests/test_rulings.py)\n\n" + drifted,
    }
    assert [rule for _, _, rule in doc_rules(tmp_path, files) if rule == "DOC-SAMPLE"] == []
