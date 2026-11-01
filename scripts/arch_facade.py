"""ARCH-FACADE, for the architecture check (scripts/check_architecture.py): a public facade
([package] facades) only re-exports names.

A facade is a module directly under the package root that an app imports, such as
`<package>.ports`. It holds its docstring, its imports and one `__all__` assignment, a list or a
tuple of string literals, and nothing else: no function, class, constant or code that runs. So
every public name lives in the layer that owns it, under that layer's rules, and the facade
says only which names are public (the design's 5.3; D-020).
"""

from __future__ import annotations

import ast

from scripts._common import Violation

FIX = (
    "Move it into the layer that owns it and re-export its names here: a facade holds only its "
    "docstring, its imports, and `__all__` as a list of string literals."
)


def check_facade(display: str, tree: ast.Module) -> list[Violation]:
    """Every statement of the facade that is not its docstring, an import or `__all__`."""
    violations: list[Violation] = []
    exports = 0
    for index, node in enumerate(tree.body):
        if isinstance(node, ast.Import | ast.ImportFrom) or (index == 0 and _is_docstring(node)):
            continue
        if _assigns_all(node):
            exports += 1
            if exports > 1:
                problem = "`__all__` is assigned more than once"
            elif _literal_names(node):
                continue
            else:
                problem = "`__all__` is not a list or tuple of string literals"
        else:
            problem = f"a facade holds only re-exports, not this {type(node).__name__} statement"
        violations.append(Violation(display, node.lineno, "ARCH-FACADE", problem, FIX))
    if exports == 0:
        problem = "the facade has no `__all__`, so it names no public name"
        fix = "List every name this facade re-exports in `__all__ = [...]`."
        violations.append(Violation(display, 1, "ARCH-FACADE", problem, fix))
    return violations


def _is_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _assigns_all(node: ast.stmt) -> bool:
    if isinstance(node, ast.Assign):
        return any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
    return (
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "__all__"
    )


def _literal_names(node: ast.stmt) -> bool:
    """`__all__ = [...]`, alone on its line of targets, holding only string literals."""
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        value: ast.expr | None = node.value
    elif isinstance(node, ast.AnnAssign):
        value = node.value
    else:
        return False
    return isinstance(value, ast.List | ast.Tuple) and all(
        isinstance(item, ast.Constant) and isinstance(item.value, str) for item in value.elts
    )
