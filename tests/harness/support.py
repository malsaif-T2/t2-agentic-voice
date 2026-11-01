"""Helpers for the harness's own tests: a small repository on disk, and a harness.toml for it.

The checks run here against a synthetic project, not this one: package `app` with the layers
core, domain, adapters, services, and api, so a test states its rules in a few lines and stays
true whatever this project's own harness.toml says.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from scripts.harness_config import HarnessConfig, load_config

SYNTHETIC = """\
[package]
name = "app"
root = "src"
public = ["app", "app.testing"]
facades = []
banned_words = []

[layers]
core = []
domain = ["core"]
adapters = ["core"]
services = ["core", "domain", "adapters"]
api = ["core", "domain", "adapters", "services"]

[[owners]]
modules = ["logging", "structlog"]
layers = ["core"]
fix = "Log via app.core.logging.get_logger."

[[owners]]
modules = ["sqlite3", "httpx"]
layers = ["adapters"]
fix = "Input and output belong in adapters/."

[[owners]]
modules = ["fastapi"]
layers = ["api"]
fix = "HTTP belongs in api/."

[[restricted]]
classes = ["Approved"]
layers = ["domain"]
fix = "Only domain/ issues an Approved; call approve()."

[[subpackages]]
path = "services/reports"
may_not_import = ["adapters"]
fix = "Reports take their data from the service."

[rules]
env_allowed_files = ["core/config.py"]
output_allowed_files = ["core/logging.py"]
architecture_doc = "ARCHITECTURE.md"

[modules]
max_lines = 40
support_dirs = ["scripts", "tests"]

[docs]
entry = "CLAUDE.md"
max_entry_lines = 10
required = []
historical = ["docs/plans/completed/", "docs/design/decisions.md"]
code_dirs = ["src", "scripts", "tests"]
code_exempt = []
placeholders_allowed_in = ["docs/templates/"]

[plans]
roadmap = "docs/plans/roadmap.md"
active = "docs/plans/active"
completed = "docs/plans/completed"
sections = ["## Goal", "## Acceptance criteria", "## Plan", "## Progress log", "## Decision log"]

[references]
decisions = "docs/design/decisions.md"
tech_debt = "docs/plans/tech-debt.md"
golden_principles = "docs/harness/golden-principles.md"
invariants = "docs/SECURITY.md"

[gc]
due_after_commits = 5
min_tokens = 20
size_watch = 30
path_bases = ["", "docs"]
path_ignored = ["var/"]
hooks = ["emit"]
foreign_names = ["AsyncClient"]
name_files = ["pyproject.toml"]

[quality]
doc = "docs/harness/quality.md"
suppressions_floor = 10.0
duplication_floor = 5

[quality.weights]
coverage = 40
size = 20
suppressions = 15
duplication = 15
docstrings = 10
"""


# The synthetic project's ARCHITECTURE.md: its layer table, as ARCH-DOC reads it.
ARCHITECTURE = """\
# Architecture

| Layer | Responsibility | May import | Owns (only it may import) |
| --- | --- | --- | --- |
| `core` | Settings, logging | none | `logging`, `structlog` |
| `domain` | Rules, without IO | core | — |
| `adapters` | Storage and HTTP clients | core | `sqlite3`, `httpx` |
| `services` | Use cases | core, domain, adapters | — |
| `api` | HTTP routes | `core`, `domain`, `adapters`, `services` | `fastapi` |

After the table.
"""


def write(root: Path, files: Mapping[str, str]) -> Path:
    """Write `files` (path -> text) under `root`, creating folders; return `root`."""
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return root


def config(root: Path, text: str = SYNTHETIC) -> HarnessConfig:
    """`text` written as `root`/harness.toml, then loaded as the checks load it."""
    write(root, {"harness.toml": text})
    return load_config(root)
