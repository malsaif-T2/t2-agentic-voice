"""Where a module mentions a [[restricted]] name, for ARCH-CONSTRUCT (scripts/arch_module.py,
for the library's modules, and scripts/arch_public.py, for the apps').

A name only some modules may refer to at all is looked for in the module's tokens, not only in
its tree: every NAME token that is the name, whatever it does there (an import or its alias, an
attribute, a read, an assignment's target, an annotation, a subscript's key, a keyword, a class
pattern's keyword), read as Python reads an identifier (NFKC: a fullwidth spelling is it); and
every literal that holds it, a docstring included: a string or bytes token, an f-string's
literal part, and the tree's constants, which show what escapes and implicit concatenation
build. A name the code computes at run time is not in its text, and is checked by nothing here.
"""

from __future__ import annotations

import ast
import io
import tokenize
import unicodedata
from collections.abc import Collection

from scripts._common import Violation
from scripts.harness_arch import ArchConfig

_LITERALS = frozenset({tokenize.STRING, tokenize.FSTRING_MIDDLE})


def mentions(source: str, tree: ast.Module, names: Collection[str]) -> set[tuple[int, str]]:
    """(line, name) for each line of `source` (parsed as `tree`) that mentions one of `names`."""
    if not names:
        return set()
    found: set[tuple[int, str]] = set()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        line = token.start[0]
        if token.type == tokenize.NAME:
            word = unicodedata.normalize("NFKC", token.string)
            found.update((line, name) for name in names if word == name)
        elif token.type in _LITERALS:
            found.update((line, name) for name in names if name in token.string)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str | bytes):
            found.update((node.lineno, name) for name in names if _holds(node.value, name))
    return found


def _holds(value: str | bytes, name: str) -> bool:
    """Whether a literal's value holds `name`."""
    return name in value if isinstance(value, str) else name.encode() in value


def referred(
    arch: ArchConfig, source: str, tree: ast.Module, display: str, *, layer: str, rel: str | None
) -> list[Violation]:
    """ARCH-CONSTRUCT's violations for one module's mentions of a [[restricted]] name: a module
    of the library (`rel` inside the package, in `layer`) may mention only the names whose
    layers or files hold it, and an app's (`layer` the app's name, `rel` None) none."""
    names = {
        n: r for n, r in arch.restricted_names.items() if rel is None or not r.allows(layer, rel)
    }
    where = f"app '{layer}'" if rel is None else f"layer '{layer}'"
    return [
        Violation(
            display, line, "ARCH-CONSTRUCT", f"'{name}' referred to in {where}", names[name].fix
        )
        for line, name in sorted(mentions(source, tree, names))
    ]
