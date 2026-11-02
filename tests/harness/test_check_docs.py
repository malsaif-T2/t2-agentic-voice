"""The docs check is part of the harness; it gets tests like any other code. They run on small
repositories built in a temporary folder, with the synthetic config of support.py.

This file is in harness.toml's [docs] code_exempt: its fixtures cite made-up milestones,
decisions, and placeholders, which the real repository's check would otherwise report.
"""

from __future__ import annotations

from pathlib import Path

from scripts.check_docs import ROOT, check_repo
from scripts.doc_plans import TEMPLATE
from scripts.harness_config import load_config
from tests.harness.support import ACTIVE, DONE, MAINTENANCE, PLAN_BODY, config, doc_rules, write


def test_repository_is_clean() -> None:
    violations, checked = check_repo(ROOT, load_config(ROOT))
    assert checked > 0
    assert violations == [], "\n".join(map(str, violations))


def test_valid_links_and_reachability_pass(tmp_path: Path) -> None:
    files = {
        "CLAUDE.md": "[a](docs/a.md) [site](https://example.com) [top](#top)",
        "docs/a.md": "[b](sub/b.md#section) [spaced](<my file.md>)",
        "docs/sub/b.md": "back to [a](../a.md)",
        "docs/my file.md": "",
    }
    assert doc_rules(tmp_path, files) == []


def test_broken_link_reported_with_line(tmp_path: Path) -> None:
    files = {"CLAUDE.md": "intro\n\nsee [missing](docs/nope.md)\n"}
    assert doc_rules(tmp_path, files) == [("CLAUDE.md", 3, "DOC-LINK")]


def test_links_in_code_are_ignored(tmp_path: Path) -> None:
    files = {"CLAUDE.md": "```\n[x](nope.md)\n```\n`[y](nope.md)`\n"}
    assert doc_rules(tmp_path, files) == []


def test_filename_case_must_match(tmp_path: Path) -> None:
    files = {"CLAUDE.md": "[s](docs/security.md)", "docs/SECURITY.md": ""}
    assert ("CLAUDE.md", 1, "DOC-LINK") in doc_rules(tmp_path, files)


def test_orphan_doc_reported(tmp_path: Path) -> None:
    files = {"CLAUDE.md": "no links", "docs/lonely.md": ""}
    assert doc_rules(tmp_path, files) == [("docs/lonely.md", 1, "DOC-ORPHAN")]


def test_directory_link_makes_contents_reachable(tmp_path: Path) -> None:
    files = {"CLAUDE.md": "[guides](docs/guides/)", "docs/guides/one.md": ""}
    assert doc_rules(tmp_path, files) == []


def test_entry_point_must_stay_short(tmp_path: Path) -> None:
    assert doc_rules(tmp_path, {"CLAUDE.md": "line\n" * 11}) == [("CLAUDE.md", 11, "DOC-ENTRY")]


def test_required_doc_missing(tmp_path: Path) -> None:
    result = doc_rules(tmp_path, {"CLAUDE.md": ""}, required=("ARCHITECTURE.md",))
    assert result == [("ARCHITECTURE.md", 1, "DOC-REQUIRED")]


def _placeholder(name: str) -> str:
    """Built, not written out: the kit's installer fills every placeholder it finds."""
    return "{" * 2 + name + "}" * 2


def test_unfilled_placeholders_are_reported(tmp_path: Path) -> None:
    left = _placeholder("PKG")
    files = {
        "CLAUDE.md": f"# {_placeholder('NAME')}\n\nA template: [t](docs/templates/x.md)\n",
        "docs/templates/x.md": f"Kept: {_placeholder('TITLE')}\n",  # placeholders_allowed_in
        "src/app/mod.py": f'NAME = "{left}"\nJINJA = "{{{{ lower }}}}"\n',
        ".env.example": f"{_placeholder('PREFIX')}ENV=dev\n",
        ".github/workflows/ci.yml": f"name: {left}\n",
        f"src/{left}/__init__.py": "",
        # Not ours, or never read: hidden folders, runtime output, the developer's .env.
        ".venv/lib/site.py": left,
        "var/out.md": left,
        ".env": left,
    }
    assert doc_rules(tmp_path, files) == [
        (".env.example", 1, "DOC-PLACEHOLDER"),
        (".github/workflows/ci.yml", 1, "DOC-PLACEHOLDER"),
        ("CLAUDE.md", 1, "DOC-PLACEHOLDER"),
        ("src/app/mod.py", 1, "DOC-PLACEHOLDER"),
        (f"src/{left}", 1, "DOC-PLACEHOLDER"),  # the folder's name, once
    ]


def test_crlf_line_endings_are_reported(tmp_path: Path) -> None:
    files = {
        "CLAUDE.md": "one\ntwo\r\nthree\r\n",
        "src/app/mod.py": "x = 1\r\n",
        "notes.txt": "not read\r\n",
    }
    assert doc_rules(tmp_path, files) == [
        ("CLAUDE.md", 2, "DOC-EOL"),
        ("src/app/mod.py", 1, "DOC-EOL"),
    ]


def test_control_characters_in_a_doc_are_reported(tmp_path: Path) -> None:
    """What a Windows path becomes when its backslashes are read as escapes (plan 002's
    review): a vertical tab and a bell, and a lone carriage return (`\\recordings`); a tab is
    kept, and the code is not read."""
    files = {
        "CLAUDE.md": "a tab\tis fine\n--replies ..\x0boice-lab\x07ssets\n",
        "docs/guide.md": "fine\nform feed \x0c here\n--audio talkover=..\\voice-lab\recordings\n",
        "src/app/mod.py": 'X = "\x0b"\n',
    }
    files["CLAUDE.md"] += "[guide](docs/guide.md)\n"
    assert doc_rules(tmp_path, files) == [
        ("CLAUDE.md", 2, "DOC-CONTROL"),
        ("docs/guide.md", 2, "DOC-CONTROL"),
        ("docs/guide.md", 3, "DOC-CONTROL"),
    ]


def test_plans_need_every_section(tmp_path: Path) -> None:
    files = {
        "CLAUDE.md": "[active](docs/plans/active/)",
        "docs/plans/active/001-good.md": ACTIVE,
        "docs/plans/active/002-bad.md": ACTIVE.replace("## Plan\n", "## Steps\n"),
    }
    assert doc_rules(tmp_path, files) == [("docs/plans/active/002-bad.md", 1, "DOC-PLAN")]


def test_the_missing_section_fix_names_a_template_that_has_them_all(tmp_path: Path) -> None:
    files = {
        "CLAUDE.md": "[active](docs/plans/active/)",
        "docs/plans/active/001-bad.md": ACTIVE.replace("## Plan\n", "## Steps\n"),
    }
    violations, _ = check_repo(write(tmp_path, files), config(tmp_path))
    assert [TEMPLATE in v.fix for v in violations if v.rule == "DOC-PLAN"] == [True]
    template = (ROOT / TEMPLATE).read_text(encoding="utf-8").splitlines()
    sections = load_config(ROOT).plans.sections
    assert [s for s in sections if s not in template] == [], f"{TEMPLATE} lacks a section"


def test_a_plans_status_matches_its_folder_and_the_roadmap_links_active_plans(
    tmp_path: Path,
) -> None:
    files = {
        "CLAUDE.md": "[roadmap](docs/plans/roadmap.md) [active](docs/plans/active/) "
        "[done](docs/plans/completed/)",
        "docs/plans/roadmap.md": "| M1 | One | in progress ([001](active/001-linked.md)) |\n",
        "docs/plans/active/001-linked.md": ACTIVE,
        "docs/plans/active/002-unlinked.md": ACTIVE,
        "docs/plans/active/003-finished.md": DONE,
        "docs/plans/completed/000-old.md": DONE,
        "docs/plans/completed/004-still-open.md": ACTIVE,
    }
    assert doc_rules(tmp_path, files) == [
        ("docs/plans/active/002-unlinked.md", 1, "DOC-PLAN"),  # not in the roadmap
        ("docs/plans/active/003-finished.md", 1, "DOC-PLAN"),  # says completed
        ("docs/plans/active/003-finished.md", 1, "DOC-PLAN"),  # and is not linked either
        ("docs/plans/completed/004-still-open.md", 1, "DOC-PLAN"),  # says active
    ]


def test_a_plans_name_and_status_line_keep_the_shape_the_checks_read(tmp_path: Path) -> None:
    files = {
        "CLAUDE.md": "[active](docs/plans/active/) [done](docs/plans/completed/)",
        "docs/plans/active/001-good.md": ACTIVE,
        "docs/plans/active/7-unnumbered.md": ACTIVE,
        "docs/plans/active/002-Capitals.md": ACTIVE,
        "docs/plans/active/003-bare.md": "Status: active\n\n" + PLAN_BODY,
        "docs/plans/active/004-template.md": ACTIVE.replace(MAINTENANCE, "Milestone: M?"),
        "docs/plans/completed/005-undated.md": DONE.replace(" · Completed: 2026-01-15", ""),
    }
    assert doc_rules(tmp_path, files) == [
        ("docs/plans/active/002-Capitals.md", 1, "DOC-PLAN"),
        ("docs/plans/active/003-bare.md", 1, "DOC-PLAN"),
        ("docs/plans/active/004-template.md", 1, "DOC-PLAN"),
        ("docs/plans/active/7-unnumbered.md", 1, "DOC-PLAN"),
        ("docs/plans/completed/005-undated.md", 1, "DOC-PLAN"),
    ]


def test_the_fix_for_an_unlinked_plan_says_where_it_belongs(tmp_path: Path) -> None:
    files = {
        "CLAUDE.md": "[roadmap](docs/plans/roadmap.md) [active](docs/plans/active/)",
        "docs/plans/roadmap.md": "| M1 | One | in progress |\n",
        "docs/plans/active/001-feature.md": ACTIVE.replace(MAINTENANCE, "Milestone: M1"),
        "docs/plans/active/002-cleanup.md": ACTIVE,
    }
    violations, _ = check_repo(write(tmp_path, files), config(tmp_path))
    fixes = {v.path.rsplit("/", 1)[1]: v.fix for v in violations}
    assert sorted(fixes) == ["001-feature.md", "002-cleanup.md"]
    assert "from M1's row in docs/plans/roadmap.md" in fixes["001-feature.md"]
    assert "from the 'Outside the milestones' line" in fixes["002-cleanup.md"]
