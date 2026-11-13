"""What docs and code cite exists (DOC-MILESTONE, DOC-REF), and no register gives one number
to two entries (DOC-REGISTER): on small repositories built in a temporary folder, with the
synthetic config of support.py.

This file is in harness.toml's [docs] code_exempt: its fixtures cite made-up milestones,
decisions, debt rows, principles, plans, and invariants.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from scripts.check_docs import ROOT, check_repo
from scripts.harness_config import load_config
from tests.harness.support import ACTIVE, DONE, config, doc_rules, write

ROADMAP = "| # | Milestone |\n| --- | --- |\n| M1 | One |\n| M2 | Two |\n"


def test_living_docs_cite_only_roadmap_milestones(tmp_path: Path) -> None:
    files = {
        "CLAUDE.md": "[roadmap](docs/plans/roadmap.md) [history](docs/plans/completed/)",
        "docs/plans/roadmap.md": ROADMAP + "\nM2 builds on M1.\n",
        "ARCHITECTURE.md": "Arrives in M1.\nArrives in M7.\n",
        "docs/plans/completed/000-old.md": DONE + "\nPlanned for M9 at the time.\n",
    }
    assert doc_rules(tmp_path, files) == [("ARCHITECTURE.md", 2, "DOC-MILESTONE")]


def test_code_never_cites_milestones(tmp_path: Path) -> None:
    files = {
        "CLAUDE.md": "[roadmap](docs/plans/roadmap.md)",
        "docs/plans/roadmap.md": ROADMAP,
        "src/app/mod.py": "x = 1  # arrives in M2\n",
        "scripts/tool.py": "SIZE = 'M2.5'  # a code with a decimal part, not a milestone\n",
    }
    assert doc_rules(tmp_path, files) == [("src/app/mod.py", 1, "DOC-MILESTONE")]


def test_code_and_the_root_toml_never_name_a_plans_track_or_block(tmp_path: Path) -> None:
    files = {
        "CLAUDE.md": "[roadmap](docs/plans/roadmap.md)",
        "docs/plans/roadmap.md": ROADMAP + "\nTrack A of plan 001 is history here.\n",
        "src/app/a.py": '"""Built in Track A."""\n',
        "src/app/b.py": "# the stand-ins of Tracks A to D\n",
        "src/app/c.py": "x = 1  # Block 0's stub\n",
        "src/app/d.py": "# Block H's run\n",
        "scripts/tool.py": "# a block of code, the track's end, ClauseBlocked, Block\n",
        "harness.toml": "# kept for plan 003, Track C\n",
        "docs/guide/page.md": "Block 0 in a doc is not code.\n",
    }
    found = [f for f in doc_rules(tmp_path, files) if f[2] == "DOC-PLANWORDS"]
    assert found == [
        ("harness.toml", 1, "DOC-PLANWORDS"),
        ("src/app/a.py", 1, "DOC-PLANWORDS"),
        ("src/app/b.py", 1, "DOC-PLANWORDS"),
        ("src/app/c.py", 1, "DOC-PLANWORDS"),
        ("src/app/d.py", 1, "DOC-PLANWORDS"),
    ]


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
    assert doc_rules(tmp_path, files) == expected


def test_history_may_cite_retired_debt_but_not_missing_decisions(tmp_path: Path) -> None:
    plan = "docs/plans/completed/001-first.md"
    files = {**REGISTRY_DOCS, plan: REGISTRY_DOCS[plan] + "Follows D-009.\n"}
    line = files[plan].splitlines().index("Follows D-009.") + 1
    assert doc_rules(tmp_path, files) == [(plan, line, "DOC-REF")]


def test_the_generated_run_history_keeps_the_references_of_its_runs(tmp_path: Path) -> None:
    """A note that cited a debt row since paid, or a milestone since re-planned, was right at its
    run and cannot be edited, so this repository counts the history page as history."""
    history = "docs/generated/eval-history.md"
    assert history in load_config(ROOT).docs.historical
    files = {
        **REGISTRY_DOCS,
        "CLAUDE.md": REGISTRY_DOCS["CLAUDE.md"] + f" [history]({history})",
        history: "| run | note |\n| --- | --- |\n| 1 | TD-001 paid, before M9 |\n| 2 | D-009 |\n",
    }
    assert doc_rules(tmp_path, files, historical=(history,)) == [(history, 4, "DOC-REF")]


def test_references_and_registers_read_the_entries_alike(tmp_path: Path) -> None:
    """One parser per register for both rules: an invariant heading with a trailing space still
    opens the section, and an entry inside a code fence is an example, not an entry."""
    security = "## Threats\n\n3. **Not one.** x\n\n## Invariants \n\n1. **One.** a\n"
    debt = "| ID | Debt |\n| --- | --- |\n| TD-002 | a |\n\n```\n| TD-005 | an example |\n```\n"
    code = "# invariant 1 holds; TD-002 is owed.\n# invariant 3 is none.\n# Nor TD-005.\n"
    files = {
        **REGISTRY_DOCS,
        "docs/SECURITY.md": security,
        "docs/plans/tech-debt.md": debt,
        "src/app/mod.py": code,
    }
    found = [("src/app/mod.py", n, "DOC-REF") for n in (2, 3)]
    # The example is still read as a citation, as every fenced line is.
    assert doc_rules(tmp_path, files) == [("docs/plans/tech-debt.md", 6, "DOC-REF"), *found]


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
    assert doc_rules(tmp_path, files) == [(path, line, "DOC-REGISTER") for path, line in expected]
