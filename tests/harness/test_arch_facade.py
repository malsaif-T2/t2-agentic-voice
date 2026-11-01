"""Public facades ([package] facades): ARCH-FACADE keeps each to re-exports; the package root's
rules apply to it (it may import every layer, but an owned library only from its owner); no
layer imports one; and an app imports one as a public module (ARCH-PUBLIC)."""

from __future__ import annotations

from pathlib import Path

from scripts.check_architecture import check_repo
from tests.harness.support import ARCHITECTURE, SYNTHETIC, config, write

# The synthetic library with one facade, `app.ports`, and one app built on it.
FACADE = SYNTHETIC.replace("facades = []", 'facades = ["app.ports"]').replace(
    'public = ["app", "app.testing"]', 'public = ["app", "app.testing", "app.ports"]'
)
APP = '\n[[apps]]\nname = "shop"\nroot = "apps/shop/src"\n'
DOCSTRING = '"""The ports."""\n\nfrom __future__ import annotations\n\n'


def _check(tmp_path: Path, files: dict[str, str]) -> list[tuple[str, int, str, str]]:
    """(path, line, rule, problem) of each violation, with the facade and the app present."""
    base = {
        "ARCHITECTURE.md": ARCHITECTURE,
        "src/app/__init__.py": "",
        "src/app/ports.py": DOCSTRING + "__all__: list[str] = []\n",
        "apps/shop/src/shop/__init__.py": "",
    }
    write(tmp_path, base | files)
    violations, _ = check_repo(tmp_path, config(tmp_path, FACADE + APP))
    return sorted((v.path, v.line, v.rule, v.problem) for v in violations)


def test_a_facade_may_re_export_from_every_layer(tmp_path: Path) -> None:
    facade = DOCSTRING + (
        "from app.api.routes import Router\n"
        "from app.domain.ports import Port\n"
        "import app.core.config\n\n"
        '__all__ = ["Port", "Router"]\n'
    )
    assert _check(tmp_path, {"src/app/ports.py": facade}) == []


def test_a_facade_holds_only_its_docstring_imports_and_all(tmp_path: Path) -> None:
    facade = DOCSTRING + (
        "from app.domain.ports import Port\n"  # 5
        "LIMIT = 3\n"  # 6: a constant
        "def helper() -> int:\n    return LIMIT\n"  # 7: a function
        "class Extra:\n    pass\n"  # 9: a class
        '__all__ = ["Port"]\n'  # 11: the one export list
        '__all__ = ["Port", "Extra"]\n'  # 12: a second one
        '__all__ += ["helper"]\n'  # 13: an augmented one
        '"""A second string is not the docstring."""\n'  # 14
    )
    found = [
        (line, problem) for _, line, _, problem in _check(tmp_path, {"src/app/ports.py": facade})
    ]
    assert [line for line, _ in found] == [6, 7, 9, 12, 13, 14]
    assert "Assign statement" in found[0][1]
    assert "more than once" in found[3][1]


def test_a_facade_names_its_exports_as_literals(tmp_path: Path) -> None:
    computed = DOCSTRING + "from app.domain.ports import Port\n\n__all__ = [Port.__name__]\n"
    found = _check(tmp_path, {"src/app/ports.py": computed})
    assert [(rule, problem) for _, _, rule, problem in found] == [
        ("ARCH-FACADE", "`__all__` is not a list or tuple of string literals")
    ]
    bare = _check(tmp_path, {"src/app/ports.py": DOCSTRING + "from app.domain import Port\n"})
    assert [(line, rule) for _, line, rule, _ in bare] == [(1, "ARCH-FACADE")]


def test_an_owned_library_stays_with_its_owner_even_in_a_facade(tmp_path: Path) -> None:
    facade = DOCSTRING + 'import httpx\n\n__all__ = ["httpx"]\n'
    found = _check(tmp_path, {"src/app/ports.py": facade})
    assert [(path, rule) for path, _, rule, _ in found] == [("src/app/ports.py", "ARCH-OWNER")]


def test_no_layer_imports_a_facade(tmp_path: Path) -> None:
    found = _check(tmp_path, {"src/app/domain/rule.py": "from app.ports import Port\n"})
    assert [(path, rule) for path, _, rule, _ in found] == [
        ("src/app/domain/rule.py", "ARCH-LAYER")
    ]
    assert "from a facade" in found[0][3]


def test_a_module_at_the_root_that_is_not_a_facade_sits_outside_every_layer(
    tmp_path: Path,
) -> None:
    found = _check(tmp_path, {"src/app/helpers.py": '__all__ = ["x"]\n'})
    assert [(path, rule) for path, _, rule, _ in found] == [("src/app/helpers.py", "ARCH-LAYER")]


def test_an_app_imports_a_facade_as_a_public_module(tmp_path: Path) -> None:
    app = (
        "from app import ports\n"
        "from app.ports import Port\n"
        "import app.ports\n"
        "from app import core, ports as p\n"  # 4: `core` is a layer, never public
    )
    found = _check(tmp_path, {"apps/shop/src/shop/use.py": app})
    assert [(line, rule) for _, line, rule, _ in found] == [(4, "ARCH-PUBLIC")]
    assert "'app.core' is not public" in found[0][3]
