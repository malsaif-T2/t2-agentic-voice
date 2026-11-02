"""What an error, a log line or an output may show, in one place (GP-19; docs/SECURITY.md,
invariant 5). A value that leaked through an error's text, its exception chain or a third-party
log line was fixed again and again in plan 002, each test gathering "everything shown" by hand
and each missing a different surface. A test that checks a secret, or a value a check refused,
is never shown asks `holding(value, shown(error, caplog=caplog, capsys=capsys, recwarn=recwarn))`
instead, with the fixtures it has.

Any package's tests may use it. The design's `testing.assert_no_secret_leaks` (5.1) is to grow
from it."""

from __future__ import annotations

import json
import traceback
from collections.abc import Mapping

import pytest
from pydantic import ValidationError


def _chain(error: BaseException) -> list[BaseException]:
    """`error` and every exception chained to it, a cause or a context, a suppressed one too."""
    found: list[BaseException] = []
    waiting: list[BaseException | None] = [error]
    while waiting:
        each = waiting.pop()
        if each is not None and not any(each is seen for seen in found):
            found.append(each)
            waiting += [each.__cause__, each.__context__]
    return found


def _attributes(error: BaseException) -> str:
    """The repr of what `error` holds beside its arguments; none for a type with no `__dict__`
    (one written in Rust, as pydantic's ValidationError is)."""
    return repr(getattr(error, "__dict__", {}))


def _carried(error: BaseException) -> str:
    """What `error` holds beside its text: its attributes, and a ValidationError's `errors()`."""
    if isinstance(error, ValidationError):
        return repr(error.errors())
    return _attributes(error)


def shown(
    error: BaseException | None = None,
    *,
    caplog: pytest.LogCaptureFixture | None = None,
    capsys: pytest.CaptureFixture[str] | None = None,
    recwarn: pytest.WarningsRecorder | None = None,
) -> dict[str, str]:
    """Every surface that may show a value, by name:
    - of `error`: its text, its repr, its traceback as Python prints it (the chain it shows and
      any note added), its attributes (a `T2VoiceError`'s message and details) and its details
      as JSON; for a pydantic ValidationError, its `errors()` and its `json()`, which carry the
      input that its text and repr leave out under `hide_input_in_errors` (FastAPI's own 422
      sends `errors()` to the client); and the text, repr and attributes (a ValidationError's
      `errors()`) of each exception chained to it, a context `raise ... from None` suppressed
      included, since a debugger or a crash reporter still reaches it;
    - of `caplog`: every log record's formatted text and message, a third party's included, and
      the fields of each of the library's (`record.fields`), which neither of those holds;
    - of `capsys`: what was written to stdout (`configure_logging`'s lines) and to stderr, read
      here, so a test reads them from the result rather than from `capsys` again;
    - of `recwarn`: every Python warning's category and message (pydantic's serializer warnings
      quoted a refused value), which under pytest reach neither stderr nor `capsys`."""
    surfaces: dict[str, str] = {}
    if error is not None:
        surfaces["text"] = str(error)
        surfaces["repr"] = repr(error)
        surfaces["traceback"] = "".join(traceback.format_exception(error))
        surfaces["attributes"] = _attributes(error)
        details = getattr(error, "details", None)
        if details is not None:
            surfaces["details"] = json.dumps(details, ensure_ascii=False, default=repr)
        if isinstance(error, ValidationError):
            surfaces["errors"] = repr(error.errors())
            surfaces["errors json"] = error.json()
        chained = _chain(error)[1:]
        surfaces["chain"] = "\n".join(f"{c}\n{c!r}\n{_carried(c)}" for c in chained)
    if caplog is not None:
        messages = [record.getMessage() for record in caplog.records]
        held = [vars(record) for record in caplog.records]
        fields = [repr(each["fields"]) for each in held if "fields" in each]
        surfaces["log records"] = "\n".join([caplog.text, *messages, *fields])
    if capsys is not None:
        surfaces["stdout"], surfaces["stderr"] = capsys.readouterr()
    if recwarn is not None:
        surfaces["warnings"] = "\n".join(f"{w.category.__name__}: {w.message}" for w in recwarn)
    return surfaces


def holding(value: str, surfaces: Mapping[str, str]) -> list[str]:
    """The names of the surfaces that hold `value`: [] when none does, so a failing assertion
    names where it leaked."""
    return [name for name, text in surfaces.items() if value in text]
