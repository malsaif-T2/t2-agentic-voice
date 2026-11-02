"""ARCH-DEPS (scripts/arch_deps.py): every outside module the code imports is declared by its own
project. On a small workspace built here: the library is the root project (its package at src/,
as a one-package repository has it), and the app `shop` a member with its own pyproject.toml."""

from __future__ import annotations

from pathlib import Path

from scripts.arch_deps import check_deps, normalized
from scripts.check_architecture import ROOT
from scripts.harness_config import load_config
from tests.harness.support import SYNTHETIC, config, write

SHOP = '\n[[apps]]\nname = "shop"\nroot = "apps/shop/src"\n'
# module -> the distributions that install it, as the environment would say.
INSTALLED = {
    "httpx": ["httpx"],
    "yaml": ["PyYAML"],
    "pydantic": ["pydantic"],
    "pytest": ["pytest"],
    "_pytest": ["pytest"],
    "requests": ["requests"],
    "coverage": ["coverage"],
    "opentelemetry": ["opentelemetry-sdk", "opentelemetry-api"],
}
PROJECTS = {
    "pyproject.toml": (
        '[project]\nname = "App_Lib"\ndependencies = ["httpx>=0.28,<1", "opentelemetry-api"]\n'
        '[dependency-groups]\ndev = ["pytest>=9", {include-group = "lint"}]\nlint = []\n'
    ),
    "apps/shop/pyproject.toml": (
        '[project]\nname = "shop"\ndependencies = ["app-lib", "Pydantic>=2.13"]\n'
    ),
}


def _found(tmp_path: Path, files: dict[str, str]) -> list[tuple[str, int, str]]:
    loaded = config(tmp_path, SYNTHETIC + SHOP)
    write(tmp_path, {**PROJECTS, **files})
    violations = check_deps(tmp_path, loaded.arch, INSTALLED)
    assert {v.rule for v in violations} <= {"ARCH-DEPS"}
    return sorted((v.path, v.line, v.problem.split("'")[1]) for v in violations)


def test_each_project_imports_only_what_it_declares(tmp_path: Path) -> None:
    files = {
        "src/app/adapters/client.py": (
            "import os\nimport httpx\nfrom . import x\nimport app.core\nimport opentelemetry.sdk\n"
            "def load() -> None:\n    import yaml\n"  # inside a function, still an import
        ),
        # The app borrows httpx from the library, which declares it; the app does not.
        "apps/shop/src/shop/__init__.py": "import pydantic\nfrom app import thing\nimport httpx\n",
        "apps/shop/src/shop/__pycache__/old.py": "import yaml\n",
    }
    assert _found(tmp_path, files) == [
        ("apps/shop/src/shop/__init__.py", 3, "httpx"),
        ("src/app/adapters/client.py", 7, "yaml"),
    ]


def test_scripts_and_tests_import_what_the_root_or_a_member_declares(tmp_path: Path) -> None:
    files = {
        "tests/test_x.py": (
            "import pytest\nfrom _pytest import capture\nimport httpx\nimport pydantic\n"
            "import shop\nimport app\nfrom scripts import tool\nfrom tests import helpers\n"
            "import requests\nimport nowhere\n"
        ),
        "scripts/tool.py": "from __future__ import annotations\nimport coverage\nimport sys\n",
    }
    assert _found(tmp_path, files) == [
        ("scripts/tool.py", 2, "coverage"),
        ("tests/test_x.py", 9, "requests"),
        ("tests/test_x.py", 10, "nowhere"),
    ]


def test_an_app_declares_the_library_it_is_built_on(tmp_path: Path) -> None:
    lonely = '[project]\nname = "shop"\ndependencies = ["pydantic"]\n'
    files = {"apps/shop/pyproject.toml": lonely, "apps/shop/src/shop/a.py": "import app\n"}
    assert _found(tmp_path, files) == [("apps/shop/src/shop/a.py", 1, "app")]


def test_the_fix_names_the_command_for_the_project(tmp_path: Path) -> None:
    loaded = config(tmp_path, SYNTHETIC + SHOP)
    files = {"apps/shop/src/shop/a.py": "import requests\n", "tests/t.py": "import yaml\n"}
    write(tmp_path, {**PROJECTS, **files})
    fixes = {v.path: v.fix for v in check_deps(tmp_path, loaded.arch, INSTALLED)}
    assert "`uv add --package shop requests`" in fixes["apps/shop/src/shop/a.py"]
    assert "`uv add --dev PyYAML`" in fixes["tests/t.py"]
    assert all("never pip or edit uv.lock" in fix for fix in fixes.values())


def test_distribution_names_compare_as_packaging_compares_them() -> None:
    assert normalized("Shop_Tools.Extra") == normalized("shop-tools-extra") == "shop-tools-extra"


def test_this_repository_declares_what_it_imports() -> None:
    assert check_deps(ROOT, load_config(ROOT).arch) == []
