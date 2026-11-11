"""The architecture check is part of the harness; it gets tests like any other code. They run
on small projects built in a temporary folder, with the synthetic config of support.py."""

from __future__ import annotations

from pathlib import Path

from scripts.check_architecture import ROOT, check_repo
from scripts.harness_config import HarnessConfig, load_config
from tests.harness.support import ARCHITECTURE, SYNTHETIC, config, write

# Two apps on the synthetic library `app` (public: `app` and `app.testing`).
APPS = (
    '\n[[apps]]\nname = "shop"\nroot = "apps/shop/src"\n'
    '\n[[apps]]\nname = "demo"\nroot = "examples/demo/src"\n'
)
APP_PACKAGES = {
    "src/app/__init__.py": "",
    "apps/shop/src/shop/__init__.py": "",
    "examples/demo/src/demo/__init__.py": "",
}


def _check(tmp_path: Path, files: dict[str, str], text: str = SYNTHETIC) -> list[tuple[str, str]]:
    """(path inside the package, rule) of each violation in a project holding `files`, with the
    harness.toml `text`."""
    loaded = config(tmp_path, text)
    package = {"src/app/__init__.py": ""} | {f"src/app/{k}": v for k, v in files.items()}
    write(tmp_path, {"ARCHITECTURE.md": ARCHITECTURE, **package})
    violations, _ = check_repo(tmp_path, loaded)
    return [(v.path.removeprefix("src/app/"), v.rule) for v in violations]


def test_this_repositorys_config_points_the_check_at_its_code() -> None:
    """The gate's `arch` step runs the check on this repository and fails on any violation; it
    would pass on no files, so this test keeps that its OK is not one of nothing: the config
    names the library, the apps, scripts/ and tests/, and each holds Python modules. The rules
    themselves are the tests below, on small projects."""
    arch = load_config(ROOT).arch
    folders = [arch.package_dir, *(app.dir for app in arch.apps), *arch.support_dirs]
    assert len(arch.apps) > 1 and {"scripts", "tests"} <= set(arch.support_dirs)
    assert [f for f in folders if next((ROOT / f).rglob("*.py"), None) is None] == []


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
            "import importlib as il\nil.import_module(name)\nil.import_module('.x')\n"
            "il.import_module('app.core.types')\nother.import_module('app.api')\n"
        ),
        # a relative name with its literal anchor, a keyword, importlib's __import__, a level
        "domain/e.py": "import importlib as il\nil.import_module('.api', 'app')\n",
        "domain/f.py": "import importlib\nimportlib.import_module(name='sqlite3')\n",
        "domain/g.py": "from importlib import __import__ as imp\nimp('app.services')\n",
        "domain/sub/h.py": "__import__('adapters', globals(), None, (), 3)\n",
    }
    assert sorted(_check(tmp_path, files)) == [
        ("core/a.py", "ARCH-LAYER"),
        ("core/b.py", "ARCH-LAYER"),
        ("domain/c.py", "ARCH-LAYER"),
        ("domain/c.py", "ARCH-OWNER"),
        ("domain/e.py", "ARCH-LAYER"),
        ("domain/f.py", "ARCH-OWNER"),
        ("domain/g.py", "ARCH-LAYER"),
        ("domain/sub/h.py", "ARCH-LAYER"),
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


def test_the_print_and_environment_fixes_say_what_harness_toml_says(tmp_path: Path) -> None:
    """The logging owner's fix says how to log; the settings library's owner, when it has one,
    says how to add a setting; otherwise the fix names [rules] env_allowed_files."""
    settings = '\n[[owners]]\nmodules = ["pydantic_settings"]\nlayers = ["core"]\nfix = "Add it."\n'
    files = {"src/app/__init__.py": "", "src/app/api/x.py": "import os\nprint(os.getenv('A'))\n"}
    fixes = []
    for text in (SYNTHETIC, SYNTHETIC + settings):
        loaded = config(tmp_path, text)
        found = check_repo(write(tmp_path, files), loaded)[0]
        fixes.append({v.rule: v.fix for v in found if v.rule in ("ARCH-PRINT", "ARCH-ENV")})
    assert fixes[0]["ARCH-PRINT"] == "Log via app.core.logging.get_logger."
    assert fixes[0]["ARCH-ENV"] == "Read the setting in core/config.py, and pass its value in."
    assert fixes[1]["ARCH-ENV"] == "Add it."


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


SEAL = (
    '\n[[restricted]]\nnames = ["SEAL"]\nlayers = ["domain"]\nfiles = ["core/seal.py"]\n'
    'fix = "Only domain/ and core/seal.py hold SEAL."\n'
)


def test_a_restricted_name_is_mentioned_only_by_its_layers_and_files(tmp_path: Path) -> None:
    """Every mention counts, not only a call: an import under any alias, an attribute (bound to
    a name or not), a name read, a re-export, a class pattern's keyword, an annotation, a
    subscript's key, an assignment of the name to itself, a fullwidth spelling, and a literal
    that holds it (a string, an f-string's part, bytes, an escape, two literals joined, a
    docstring); and a star import from a module that may bind it, the row's file or a module of
    its layers. Only the row's layers and files may: a module that defines a name of the same
    spelling is no exception. A comment, and another word, are not mentions."""
    star, module = "from app.core.seal import *\n", "from app.core import seal\n\n"
    files = {
        "__init__.py": "from app.core.seal import SEAL\n",
        "core/seal.py": "SEAL = object()\n\n\ndef sealed(value):\n    return value is SEAL\n",
        "core/own.py": "SEAL = object()\nkept = SEAL\n",
        "domain/approve.py": "from app.core.seal import SEAL as S\n\nkept = S\n",
        "services/alias.py": "from app.core.seal import SEAL as S\n",
        "services/attribute.py": module + "kind = seal.SEAL\n",
        "services/string.py": module + "kind = getattr(seal, 'SEAL')\n",
        "services/padded.py": module + "kind = getattr(seal, ' SEAL'.strip())\n",
        "services/fstring.py": module + "kind = getattr(seal, f'{x}SEAL')\n",
        "services/bytes.py": module + "kind = getattr(seal, b'SEAL'.decode())\n",
        "services/escaped.py": module + "kind = getattr(seal, 'S\\x45AL')\n",
        "services/joined.py": module + "kind = getattr(seal, 'SE' 'AL')\n",
        "services/doc.py": '"""Where SEAL is kept."""\n',
        "services/match.py": module + "match seal:\n    case object(SEAL=kind):\n        pass\n",
        "services/wide.py": module + "kind = seal.\uff33EAL\n",
        "services/read.py": star + "\nkind = SEAL\n",
        "services/star.py": star,
        "services/relative.py": "from ..core.seal import *\n",
        "services/layer.py": "from app.domain.approve import *\n",
        "services/annotated.py": star + "SEAL: object\nkind = SEAL\n",
        "services/keyed.py": star + "_seen = {}\n_seen[SEAL] = 1\n",
        "services/itself.py": star + "SEAL = SEAL\n",
        "services/clean.py": "# SEAL, in a comment\nfrom app.core import seal\n\nkind = 'seal'\n",
        "api/relative.py": "from ..core.seal import SEAL\n",
    }
    found = _check(tmp_path, files, SYNTHETIC + SEAL)
    assert {path for path, _ in found} == {
        *(f for f in files if f.startswith("services/") and f != "services/clean.py"),
        "__init__.py",
        "core/own.py",
        "api/relative.py",
    }
    assert {rule for _, rule in found} == {"ARCH-CONSTRUCT"}


def test_an_app_never_mentions_a_restricted_name(tmp_path: Path) -> None:
    """Not even by an attribute path through the public package root, which ARCH-PUBLIC, reading
    imports, lets pass."""
    files = {
        "apps/shop/src/shop/reach.py": "import app\n\nkind = app.core.seal.SEAL\n",
        "apps/shop/src/shop/clean.py": "import app\n",
    }
    loaded = config(tmp_path, SYNTHETIC + SEAL + APPS)
    write(tmp_path, {"ARCHITECTURE.md": ARCHITECTURE, **APP_PACKAGES, **files})
    violations, _ = check_repo(tmp_path, loaded)
    assert [(v.path, v.line, v.rule, v.problem) for v in violations] == [
        ("apps/shop/src/shop/reach.py", 3, "ARCH-CONSTRUCT", "'SEAL' referred to in app 'shop'")
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


def test_the_package_root_reexports_and_layers_never_import_from_it(tmp_path: Path) -> None:
    files = {
        "__init__.py": "from app.core.config import Settings\nfrom app.api import routes\n",
        "core/y.py": "from app import core\n",
        "domain/x.py": "from app import Settings\n",
    }
    assert _check(tmp_path, files) == [("domain/x.py", "ARCH-LAYER")]


def _check_apps(tmp_path: Path, files: dict[str, str]) -> list[tuple[str, str]]:
    """(path, rule) of each violation in a project with the library and both apps."""
    loaded = config(tmp_path, SYNTHETIC + APPS)
    write(tmp_path, {"ARCHITECTURE.md": ARCHITECTURE, **APP_PACKAGES, **files})
    violations, _ = check_repo(tmp_path, loaded)
    return sorted((v.path, v.rule) for v in violations)


def test_an_app_imports_only_the_public_api(tmp_path: Path) -> None:
    files = {
        "apps/shop/src/shop/ok.py": (
            "from app import Settings\nimport app\nimport app.testing.fakes\n"
            "from app.testing import fake\nimport shop.ok\nimport httpx\nfrom . import ok\n"
        ),
        "apps/shop/src/shop/bad.py": (
            "from app.core.config import Settings\nimport app.domain\nfrom app import core\n"
        ),
    }
    assert _check_apps(tmp_path, files) == [("apps/shop/src/shop/bad.py", "ARCH-PUBLIC")] * 3


def test_apps_stay_apart_from_each_other_and_from_the_library(tmp_path: Path) -> None:
    files = {
        "apps/shop/src/shop/x.py": "from demo import run\n",
        "examples/demo/src/demo/big.py": "x = 1\n" * 41,
        "src/app/core/y.py": "import shop\n",
        "src/app/domain/z.py": "from shop.x import thing\n",
    }
    assert _check_apps(tmp_path, files) == [
        ("apps/shop/src/shop/x.py", "ARCH-PUBLIC"),
        ("examples/demo/src/demo/big.py", "ARCH-SIZE"),
        ("src/app/core/y.py", "ARCH-PUBLIC"),
        ("src/app/domain/z.py", "ARCH-PUBLIC"),
    ]


def test_a_missing_app_is_a_config_problem(tmp_path: Path) -> None:
    loaded = config(tmp_path, SYNTHETIC + APPS)
    write(tmp_path, {"ARCHITECTURE.md": ARCHITECTURE, "src/app/__init__.py": ""})
    violations, _ = check_repo(tmp_path, loaded)
    assert [(v.rule, v.problem) for v in violations] == [
        ("HARNESS-CONFIG", "apps/shop/src/shop/__init__.py does not exist"),
        ("HARNESS-CONFIG", "examples/demo/src/demo/__init__.py does not exist"),
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
