"""harness.toml is read strictly: every mistake is a HARNESS-CONFIG violation with its line and
a FIX, so a misspelt key or a broken layer graph never passes unnoticed."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from scripts.harness_config import HarnessConfigError, load_config
from tests.harness.support import SYNTHETIC, config

ROOT = Path(__file__).resolve().parents[2]


def _problems(tmp_path: Path, text: str) -> list[tuple[int, str]]:
    with pytest.raises(HarnessConfigError) as raised:
        config(tmp_path, text)
    assert all(v.rule == "HARNESS-CONFIG" and v.fix for v in raised.value.violations)
    return [(v.line, v.problem) for v in raised.value.violations]


def _line(text: str, needle: str) -> int:
    return text.splitlines().index(needle) + 1


def test_this_repositorys_config_loads() -> None:
    loaded = load_config(ROOT)
    assert "core" in loaded.arch.layers
    assert loaded.docs.entry in loaded.docs.required


def test_the_synthetic_config_loads(tmp_path: Path) -> None:
    loaded = config(tmp_path)
    assert loaded.package_dir == "src/app"
    assert loaded.arch.layers["services"] == {"core", "domain", "adapters"}
    assert loaded.arch.owners["httpx"].layers == {"adapters"}
    assert loaded.arch.restricted["Approved"].layers == {"domain"}
    assert loaded.gc.path_bases == ("", "docs")
    assert loaded.quality.weights["coverage"] == 40


def test_a_missing_or_unparsable_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(HarnessConfigError, match=r"harness\.toml is missing"):
        load_config(tmp_path)
    assert _problems(tmp_path, "[package\n")[0][0] == 1


def test_an_unknown_layer_and_a_cycle_are_rejected(tmp_path: Path) -> None:
    text = SYNTHETIC.replace("core = []", 'core = ["api"]').replace(
        'domain = ["core"]', 'domain = ["core", "infra"]'
    )
    found = _problems(tmp_path, text)
    assert (
        _line(text, 'domain = ["core", "infra"]'),
        "layer 'domain' may import 'infra', not a layer",
    ) in found
    assert any("cycle: core -> api -> " in problem for _, problem in found)


def test_misspelt_and_missing_keys_are_rejected(tmp_path: Path) -> None:
    text = SYNTHETIC.replace("max_lines = 40", "max_line = 40")
    found = _problems(tmp_path, text)
    assert (_line(text, "[modules]"), "[modules] needs `max_lines`") in found
    assert (_line(text, "max_line = 40"), "[modules] has an unknown key `max_line`") in found


def test_wrong_kinds_are_rejected(tmp_path: Path) -> None:
    text = SYNTHETIC.replace("max_entry_lines = 10", 'max_entry_lines = "ten"').replace(
        'name = "app"', 'name = "My-App"'
    )
    found = {problem for _, problem in _problems(tmp_path, text)}
    assert "[docs] max_entry_lines must be a whole number of at least 1" in found
    assert "'My-App' is not a Python package name" in found


def test_owners_must_name_real_layers_once(tmp_path: Path) -> None:
    text = SYNTHETIC.replace('layers = ["api"]', 'layers = ["web"]').replace(
        'modules = ["fastapi"]', 'modules = ["fastapi", "httpx"]'
    )
    found = {problem for _, problem in _problems(tmp_path, text)}
    assert "[[owners]] names 'web', not a layer" in found
    assert "'httpx' is listed in two [[owners]] tables" in found


def test_apps_and_the_public_api_are_read(tmp_path: Path) -> None:
    apps = '\n[[apps]]\nname = "shop"\nroot = "apps/shop/src"\n'
    loaded = config(tmp_path, SYNTHETIC + apps)
    assert loaded.product_dirs == ("src/app", "apps/shop/src/shop")
    assert loaded.arch.app_names == {"shop"}
    modules = ("app", "app.core", "app.testing", "app.testing.fakes", "apps")
    assert [loaded.arch.is_public(m) for m in modules] == [True, False, True, True, False]


def test_apps_and_public_modules_are_checked(tmp_path: Path) -> None:
    apps = (
        '\n[[apps]]\nname = "app"\nroot = "apps/a/src"\n'
        '\n[[apps]]\nname = "My-Shop"\nroot = "apps/b/src"\n'
    )
    text = SYNTHETIC.replace('public = ["app", "app.testing"]', 'public = ["app", "other.x"]')
    found = {problem for _, problem in _problems(tmp_path, text + apps)}
    assert "public module 'other.x' is not inside package 'app'" in found
    assert "'app' is already the library's or another app's name" in found
    assert "'My-Shop' is not a Python package name" in found


def test_a_subpackage_rule_starts_with_a_layer(tmp_path: Path) -> None:
    text = SYNTHETIC.replace('path = "services/reports"', 'path = "reports"')
    found = {problem for _, problem in _problems(tmp_path, text)}
    assert "subpackage 'reports' does not start with a layer's folder" in found


def test_an_unknown_table_is_rejected_but_tool_tables_are_not(tmp_path: Path) -> None:
    text = SYNTHETIC + "\n[tool.coverage.report]\nfail_under = 1\n\n[extras]\nx = 1\n"
    assert [p for _, p in _problems(tmp_path, text)] == ["unknown table [extras]"]


def test_the_coverage_floor_lives_in_harness_toml_only() -> None:
    """coverage.py reads the floor from harness.toml (`poe test` passes --cov-config), so a
    second copy in pyproject.toml would be a second place to change it, and to forget."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    harness = tomllib.loads((ROOT / "harness.toml").read_text(encoding="utf-8"))
    assert "coverage" not in pyproject.get("tool", {}), (
        "FIX: move [tool.coverage.*] from pyproject.toml into harness.toml."
    )
    assert harness["tool"]["coverage"]["report"]["fail_under"] > 0
    test_task = pyproject["tool"]["poe"]["tasks"]["test"]["cmd"]
    assert "--cov-config=harness.toml" in test_task
