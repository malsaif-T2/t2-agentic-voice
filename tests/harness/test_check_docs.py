"""The docs check is part of the harness; it gets tests like any other code. They run on small
repositories built in a temporary folder, with the synthetic config of support.py.

This file is in harness.toml's [docs] code_exempt: its fixtures cite made-up milestones,
decisions, and placeholders, which the real repository's check would otherwise report.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from scripts.check_docs import ROOT, check_repo
from scripts.doc_plans import TEMPLATE
from scripts.harness_config import load_config
from tests.harness.support import config, write

SECTIONS = ("## Goal", "## Acceptance criteria", "## Plan", "## Progress log", "## Decision log")
PLAN_BODY = "\n\n".join(f"{heading}\n\ntext" for heading in SECTIONS)
MAINTENANCE = "Milestone: none (maintenance)"
ACTIVE = f"Status: active · {MAINTENANCE} · Started: 2026-01-12\n\n" + PLAN_BODY
DONE = f"Status: completed · {MAINTENANCE} · Started: 2026-01-12 · Completed: 2026-01-15\n\n"
DONE += PLAN_BODY


def _rules(
    root: Path, files: dict[str, str], required: tuple[str, ...] = ()
) -> list[tuple[str, int, str]]:
    loaded = config(root)
    loaded = replace(loaded, docs=replace(loaded.docs, required=required))
    violations, _ = check_repo(write(root, files), loaded)
    return sorted((v.path, v.line, v.rule) for v in violations)


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
    assert _rules(tmp_path, files) == []


def test_broken_link_reported_with_line(tmp_path: Path) -> None:
    files = {"CLAUDE.md": "intro\n\nsee [missing](docs/nope.md)\n"}
    assert _rules(tmp_path, files) == [("CLAUDE.md", 3, "DOC-LINK")]


def test_links_in_code_are_ignored(tmp_path: Path) -> None:
    files = {"CLAUDE.md": "```\n[x](nope.md)\n```\n`[y](nope.md)`\n"}
    assert _rules(tmp_path, files) == []


def test_filename_case_must_match(tmp_path: Path) -> None:
    files = {"CLAUDE.md": "[s](docs/security.md)", "docs/SECURITY.md": ""}
    assert ("CLAUDE.md", 1, "DOC-LINK") in _rules(tmp_path, files)


def test_orphan_doc_reported(tmp_path: Path) -> None:
    files = {"CLAUDE.md": "no links", "docs/lonely.md": ""}
    assert _rules(tmp_path, files) == [("docs/lonely.md", 1, "DOC-ORPHAN")]


def test_directory_link_makes_contents_reachable(tmp_path: Path) -> None:
    files = {"CLAUDE.md": "[guides](docs/guides/)", "docs/guides/one.md": ""}
    assert _rules(tmp_path, files) == []


def test_entry_point_must_stay_short(tmp_path: Path) -> None:
    assert _rules(tmp_path, {"CLAUDE.md": "line\n" * 11}) == [("CLAUDE.md", 11, "DOC-ENTRY")]


def test_required_doc_missing(tmp_path: Path) -> None:
    result = _rules(tmp_path, {"CLAUDE.md": ""}, required=("ARCHITECTURE.md",))
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
    assert _rules(tmp_path, files) == [
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
    assert _rules(tmp_path, files) == [
        ("CLAUDE.md", 2, "DOC-EOL"),
        ("src/app/mod.py", 1, "DOC-EOL"),
    ]


def test_plans_need_every_section(tmp_path: Path) -> None:
    files = {
        "CLAUDE.md": "[active](docs/plans/active/)",
        "docs/plans/active/001-good.md": ACTIVE,
        "docs/plans/active/002-bad.md": ACTIVE.replace("## Plan\n", "## Steps\n"),
    }
    assert _rules(tmp_path, files) == [("docs/plans/active/002-bad.md", 1, "DOC-PLAN")]


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
    assert _rules(tmp_path, files) == [
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
    assert _rules(tmp_path, files) == [
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


ROADMAP = "| # | Milestone |\n| --- | --- |\n| M1 | One |\n| M2 | Two |\n"


def test_living_docs_cite_only_roadmap_milestones(tmp_path: Path) -> None:
    files = {
        "CLAUDE.md": "[roadmap](docs/plans/roadmap.md) [history](docs/plans/completed/)",
        "docs/plans/roadmap.md": ROADMAP + "\nM2 builds on M1.\n",
        "ARCHITECTURE.md": "Arrives in M1.\nArrives in M7.\n",
        "docs/plans/completed/000-old.md": DONE + "\nPlanned for M9 at the time.\n",
    }
    assert _rules(tmp_path, files) == [("ARCHITECTURE.md", 2, "DOC-MILESTONE")]


def test_code_never_cites_milestones(tmp_path: Path) -> None:
    files = {
        "CLAUDE.md": "[roadmap](docs/plans/roadmap.md)",
        "docs/plans/roadmap.md": ROADMAP,
        "src/app/mod.py": "x = 1  # arrives in M2\n",
        "scripts/tool.py": "SIZE = 'M2.5'  # a code with a decimal part, not a milestone\n",
    }
    assert _rules(tmp_path, files) == [("src/app/mod.py", 1, "DOC-MILESTONE")]


REGISTRY_DOCS = {
    "CLAUDE.md": (
        "[decisions](docs/design/decisions.md) [debt](docs/plans/tech-debt.md) "
        "[principles](docs/harness/golden-principles.md) [security](docs/SECURITY.md) "
        "[plans](docs/plans/completed/) [roadmap](docs/plans/roadmap.md)"
    ),
    "docs/design/decisions.md": "# Decisions\n\n## D-001 · Stack · 2026-10-01 · Accepted\n",
    "docs/plans/tech-debt.md": "| ID | Debt |\n| --- | --- |\n| TD-002 | Untyped tests |\n",
    "docs/harness/golden-principles.md": "| ID | Principle |\n| --- | --- |\n| GP-01 | Layers |\n",
    "docs/SECURITY.md": "## Invariants\n\n1. **One.** a\n2. **Two.** b\n\n## Threats\n\n3. **x**\n",
    "docs/plans/roadmap.md": ROADMAP,
    "docs/plans/completed/001-first.md": DONE + "\nPaid TD-001, which is gone now.\n",
}


def test_cited_references_resolve(tmp_path: Path) -> None:
    code = (
        "# D-001, TD-002, GP-01, plan 001, and invariants 1 and 2 all exist.\n"
        "# D-002 does not.\n"
        "# Nor does TD-003,\n"
        "# or GP-02,\n"
        "# or plan 002,\n"
        "# or invariant 3 (inv. 2 does), nor invariants 1, 4.\n"
    )
    files = {**REGISTRY_DOCS, "src/app/mod.py": code}
    expected = [("src/app/mod.py", line, "DOC-REF") for line in (2, 3, 4, 5, 6, 6)]
    assert _rules(tmp_path, files) == expected


def test_history_may_cite_retired_debt_but_not_missing_decisions(tmp_path: Path) -> None:
    plan = "docs/plans/completed/001-first.md"
    files = {**REGISTRY_DOCS, plan: REGISTRY_DOCS[plan] + "Follows D-009.\n"}
    line = files[plan].splitlines().index("Follows D-009.") + 1
    assert _rules(tmp_path, files) == [(plan, line, "DOC-REF")]


def test_a_registry_turned_off_is_not_checked(tmp_path: Path) -> None:
    loaded = config(tmp_path)
    loaded = replace(loaded, references=replace(loaded.references, decisions=""))
    write(tmp_path, {**REGISTRY_DOCS, "src/app/mod.py": "# D-002 is not checked.\n"})
    violations, _ = check_repo(tmp_path, loaded)
    assert violations == []


def _line(text: str, start: str) -> int:
    return next(n for n, line in enumerate(text.splitlines(), start=1) if line.startswith(start))


def test_no_number_is_given_to_two_entries(tmp_path: Path) -> None:
    decisions = (
        "# Decisions\n\n```\n## D-NNN · Title · YYYY-MM-DD · Status\n## D-001 in a fence\n```\n\n"
        "## D-001 · Stack · 2026-01-12 · Accepted (a setting; not the default)\n\n"
        "## D-002 · Layers · 2026-01-12 · Amended by D-001\n\n"
        "## D-001 · Again · 2026-01-13 · Proposed\n\n"
        "## D-003 whatever\n"
    )
    files = {
        **REGISTRY_DOCS,
        "CLAUDE.md": REGISTRY_DOCS["CLAUDE.md"] + " [active](docs/plans/active/)",
        "docs/plans/roadmap.md": ROADMAP + "\nOutside the milestones: [x](active/001-second.md)\n",
        "docs/plans/active/001-second.md": ACTIVE,
        "docs/design/decisions.md": decisions,
        "docs/plans/tech-debt.md": "| ID | Debt |\n| --- | --- |\n| TD-002 | a |\n| TD-002 | b |\n",
        "docs/harness/golden-principles.md": "| GP-01 | Layers |\n| GP-01 | Again |\n",
        "docs/SECURITY.md": "## Invariants\n\n1. **One.** a\n1. **Again.** b\n\n## Threats\n",
    }
    expected = [
        ("docs/SECURITY.md", 4),
        ("docs/design/decisions.md", _line(decisions, "## D-001 · Again")),
        ("docs/design/decisions.md", _line(decisions, "## D-003")),
        ("docs/harness/golden-principles.md", 2),
        ("docs/plans/active/001-second.md", 1),  # both plans: neither is known to be the newer
        ("docs/plans/completed/001-first.md", 1),
        ("docs/plans/tech-debt.md", 4),
    ]
    assert _rules(tmp_path, files) == [(path, line, "DOC-REGISTER") for path, line in expected]
