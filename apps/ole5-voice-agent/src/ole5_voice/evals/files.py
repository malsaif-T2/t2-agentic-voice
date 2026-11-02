"""How the golden set's commands read a file: one way, whose refusal names the fields that failed,
never a value refused, which may be a transcript or a key.

`read_model` reads a JSON or TOML file into a strict model (or a `TypeAdapter`'s type), and
`parse_json` checks a text already read (a history line, a model serialized again); each
refuses with the caller's own error, which `refuse` builds from the problem, so a caller keeps
its error class and its wording. `read_text` and `read_lines` read a file as UTF-8 text. Every
refusal is raised outside the handler, so no exception chain leads to the input: a pydantic
`ValidationError` holds the input it refused even where its text hides it, and a decode error
holds the file's bytes.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

# Builds a caller's error from what went wrong, which names fields only.
Refuse = Callable[[str], Exception]
# Why a file that cannot be read is refused: missing, unreadable, or not UTF-8.
UNREADABLE = "cannot be read as UTF-8 text"


def first_problem(error: ValidationError) -> str:
    """A validation error told by its fields and messages, never by the input it refused."""
    problems = error.errors(include_input=False, include_url=False)
    where = ".".join(str(part) for part in problems[0]["loc"]) or "the top level"
    return f"{len(problems)} problem(s), the first at {where}: {problems[0]['msg']}"


def read_text(path: Path) -> str | None:
    """`path`'s text, read as UTF-8; None when it cannot be read or is not UTF-8."""
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def read_lines(path: Path) -> tuple[str, ...] | None:
    """The entries of a file of one entry a line, each stripped, blank lines and `#` comments
    skipped; None when it cannot be read (`read_text`)."""
    text = read_text(path)
    if text is None:
        return None
    lines = (line.strip() for line in text.splitlines())
    return tuple(line for line in lines if line and not line.startswith("#"))


def parse_json[T](shape: type[T] | TypeAdapter[T], text: str | bytes, refuse: Refuse) -> T:
    """`text`, JSON, as `shape`; `refuse(problem)` when it is not JSON or does not fit."""
    adapter = shape if isinstance(shape, TypeAdapter) else TypeAdapter(shape)
    try:
        return adapter.validate_json(text)
    except ValidationError as error:
        problem = first_problem(error)
    raise refuse(problem)


def read_model[T](
    path: Path, shape: type[T] | TypeAdapter[T], refuse: Refuse, *, toml: bool = False
) -> T:
    """`path`'s JSON, or with `toml` its TOML, as `shape`; `refuse(problem)` when it cannot be
    read as UTF-8 text, is not JSON or TOML, or does not fit."""
    text = read_text(path)
    if text is None:
        raise refuse(UNREADABLE)
    if not toml:
        return parse_json(shape, text, refuse)
    adapter = shape if isinstance(shape, TypeAdapter) else TypeAdapter(shape)
    try:
        return adapter.validate_python(tomllib.loads(text))
    except tomllib.TOMLDecodeError as error:  # a position, and at most the one character
        problem = f"not TOML ({error})"
    except ValidationError as error:
        problem = first_problem(error)
    raise refuse(problem)
