"""The architecture check is part of the harness; it gets tests like any other code. They run
on small projects built in a temporary folder, with the synthetic config of support.py."""

from __future__ import annotations

from pathlib import Path

from scripts.check_architecture import ROOT, check_repo
from scripts.harness_config import HarnessConfig, load_config
from tests.harness.support import ARCHITECTURE, config, write


def _check(tmp_path: Path, files: dict[str, str]) -> list[tuple[str, str]]:
    """(path inside the package, rule) of each violation in a project holding `files`."""
    loaded = config(tmp_path)
    package = {"src/app/__init__.py": ""} | {f"src/app/{k}": v for k, v in files.items()}
    write(tmp_path, {"ARCHITECTURE.md": ARCHITECTURE, **package})
    violations, _ = check_repo(tmp_path, loaded)
    return [(v.path.removeprefix("src/app/"), v.rule) for v in violations]


def test_repository_is_clean() -> None:
    violations, checked = check_repo(ROOT, load_config(ROOT))
    assert checked > 10  # src/, scripts/, and tests/
    assert violations == [], "\n".join(map(str, violations))


def test_allowed_downward_imports_pass(tmp_path: Path) -> None:
    files = {
        "core/types.py": "",
        "domain/rules.py": "from app.core import types\n",
        "services/use.py": "from app.domain.rules import x\nimport app.adapters.store\n",
        "api/app.py": "import app.services.use\n",
    }
    assert _check(tmp_path, files) == []


def test_upward_and_sibling_imports_are_rejected(tmp_path: Path) -> None:
    files = {
        "core/x.py": "from app.api import routes\n",
        "domain/y.py": "import app.adapters.store\n",
    }
    assert sorted(_check(tmp_path, files)) == [
        ("core/x.py", "ARCH-LAYER"),
        ("domain/y.py", "ARCH-LAYER"),
    ]


def test_relative_imports_are_resolved(tmp_path: Path) -> None:
    files = {
        "domain/sub/x.py": "from ...api import routes\n",
        "domain/y.py": "from .. import adapters\nfrom . import sub\n",
    }
    assert sorted(_check(tmp_path, files)) == [
        ("domain/sub/x.py", "ARCH-LAYER"),
        ("domain/y.py", "ARCH-LAYER"),
    ]


def test_imports_of_a_literal_name_are_imports_too(tmp_path: Path) -> None:
    files = {
        "core/a.py": "import importlib\nimportlib.import_module('app.api.routes')\n",
        "core/b.py": "from importlib import import_module as load\nload('app.services')\n",
        "domain/c.py": "__import__('app.adapters.store')\n__import__('sqlite3')\n",
        "domain/d.py": (
            "import importlib as il\nil.import_module(name)\nil.import_module('.x', 'app')\n"
            "il.import_module('app.core.types')\nother.import_module('app.api')\n"
        ),
    }
    assert sorted(_check(tmp_path, files)) == [
        ("core/a.py", "ARCH-LAYER"),
        ("core/b.py", "ARCH-LAYER"),
        ("domain/c.py", "ARCH-LAYER"),
        ("domain/c.py", "ARCH-OWNER"),
    ]


def test_code_outside_layers_is_rejected(tmp_path: Path) -> None:
    result = _check(tmp_path, {"helpers.py": "", "utils/x.py": ""})
    assert sorted(result) == [("helpers.py", "ARCH-LAYER"), ("utils/x.py", "ARCH-LAYER")]


def test_a_subpackage_keeps_its_narrower_rule(tmp_path: Path) -> None:
    files = {
        "services/use.py": "import app.adapters.store\n",  # the layer may
        "services/reports/pdf.py": "from app.adapters import store\n",  # its subpackage not
        "services/reports/sum.py": "from app.domain import rules\n",
    }
    assert _check(tmp_path, files) == [("services/reports/pdf.py", "ARCH-LAYER")]


def test_owned_libraries_stay_in_their_layer(tmp_path: Path) -> None:
    files = {
        "adapters/ok.py": "import sqlite3\nimport httpx\n",
        "core/ok.py": "import logging\n",
        "domain/bad.py": "from sqlite3 import connect\nimport structlog\n",
        "api/bad.py": "import httpx\n",
    }
    assert sorted(_check(tmp_path, files)) == [
        ("api/bad.py", "ARCH-OWNER"),
        ("domain/bad.py", "ARCH-OWNER"),
        ("domain/bad.py", "ARCH-OWNER"),
    ]


def test_output_goes_through_the_logger(tmp_path: Path) -> None:
    files = {
        "api/x.py": "print('hi')\n",
        "api/y.py": "import sys\nsys.stdout.write('hi')\nsys.stderr.writelines([])\n",
        "core/logging.py": "import sys\nsys.stdout.write('allowed here')\n",
    }
    assert sorted(_check(tmp_path, files)) == [
        ("api/x.py", "ARCH-PRINT"),
        ("api/y.py", "ARCH-PRINT"),
        ("api/y.py", "ARCH-PRINT"),
    ]


def test_environment_access_only_in_config(tmp_path: Path) -> None:
    files = {
        "core/config.py": "import os\nos.environ['A']\n",
        "domain/a.py": "import os\nos.getenv('A')\n",
        "domain/b.py": "import os as system\nsystem.environ.get('A')\n",
        "domain/c.py": "from os import environ\n",
        "domain/d.py": "import os.path\nos.environ['A']\n",
    }
    assert sorted(_check(tmp_path, files)) == [
        ("domain/a.py", "ARCH-ENV"),
        ("domain/b.py", "ARCH-ENV"),
        ("domain/c.py", "ARCH-ENV"),
        ("domain/d.py", "ARCH-ENV"),
    ]


def test_restricted_classes_are_constructed_only_by_their_layer(tmp_path: Path) -> None:
    files = {
        "domain/approve.py": "Approved(id=1)\n",
        "services/a.py": "Approved(id=1)\n",
        "services/b.py": "Approved.model_validate({})\n",
        "api/c.py": "models.Approved.model_construct()\n",
    }
    assert sorted(_check(tmp_path, files)) == [
        ("api/c.py", "ARCH-CONSTRUCT"),
        ("services/a.py", "ARCH-CONSTRUCT"),
        ("services/b.py", "ARCH-CONSTRUCT"),
    ]


def test_module_rules_apply_in_the_package(tmp_path: Path) -> None:
    files = {
        "core/big.py": "x = 1\n" * 41,
        "core/broken.py": "def (:\n",
    }
    assert sorted(_check(tmp_path, files)) == [
        ("core/big.py", "ARCH-SIZE"),
        ("core/broken.py", "ARCH-PARSE"),
    ]


def test_a_missing_package_is_a_config_problem(tmp_path: Path) -> None:
    violations, checked = check_repo(tmp_path, config(tmp_path))
    assert ([v.rule for v in violations], checked) == (["HARNESS-CONFIG"], 0)
    assert "src/app/__init__.py does not exist" in violations[0].problem


def test_violations_carry_remediation(tmp_path: Path) -> None:
    loaded: HarnessConfig = config(tmp_path)
    write(tmp_path, {"src/app/__init__.py": "", "src/app/core/x.py": "print(1)\n"})
    violations, _ = check_repo(tmp_path, loaded)
    rendered = str(violations[0])
    assert rendered.startswith("src/app/core/x.py:1: [ARCH-PRINT]")
    assert "\n    FIX: " in rendered


def test_scripts_and_tests_follow_the_module_rules_only(tmp_path: Path) -> None:
    loaded = config(tmp_path)
    write(
        tmp_path,
        {
            "ARCHITECTURE.md": ARCHITECTURE,
            "src/app/__init__.py": "",
            "scripts/tool.py": "import sqlite3\nprint('fine outside the layers')\n",
            "scripts/big.py": "x = 1\n" * 41,
            "tests/test_x.py": "def test_x() -> None:\n    assert (1, 2) == (1, 2)  # fmt: skip\n",
        },
    )
    violations, checked = check_repo(tmp_path, loaded)
    assert checked == 4
    assert sorted((v.path, v.rule) for v in violations) == [
        ("scripts/big.py", "ARCH-SIZE"),
        ("tests/test_x.py", "ARCH-FMT"),
    ]


def test_fmt_skip_is_only_for_data_tables(tmp_path: Path) -> None:
    source = (
        'TABLE = {\n    "a": 1,  "bb": 2,\n}  # fmt: skip\n'
        "class Codes:\n    ALL = (1,  2)  # fmt: skip\n"
        'NOTE = "a # fmt: skip inside a string is text"\n'
        "def f() -> int:\n    return (1 +  2)  # fmt: skip\n"
        "raise_it = None\nif raise_it:\n    raise ValueError(\n        'x')  # fmt: skip\n"
    )
    result = _check(tmp_path, {"core/table.py": source})
    assert result == [("core/table.py", "ARCH-FMT"), ("core/table.py", "ARCH-FMT")]
