"""The console line keeps every field on its one line (core/logging.py's `_one_line`): a key or a
value whose text holds a control, format, line or paragraph separator character, an escape
among them, is written as that text's repr, so a value from outside (a client's key, an ICE
candidate, a transcript) can neither forge a line nor erase one in a terminal. Everything else
reads as it always has (test_logging.py)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError
from t2_agentic_voice.api.protocol import JoinRequest
from t2_agentic_voice.core.logging import LIBRARY, configure_logging, get_logger

MODULE = f"{LIBRARY}.tests"
# A forged line, as a client would put it in a key or a value it sends.
FORGED = f"2026-11-02T00:00:00.000000Z [info     ] join_accepted [{LIBRARY}.api] subject=admin"
# Each character, of those the console escapes, that ends a line for a reader or a terminal:
# a line feed, a carriage return, NEL, a vertical tab, a form feed, a file separator, and
# the line and paragraph separators.
BREAKS = [chr(10), chr(13), chr(0x85), chr(11), chr(12), chr(0x1C), chr(0x2028), chr(0x2029)]
ESC = chr(27)
# An ANSI sequence that erases the line and puts the cursor at its start, then a colour.
REDRAW = f"{ESC}[2K{ESC}[1G{ESC}[31m"


class Lines:
    """An object whose repr, which the console writes for a value that is not a str, spans
    lines; its str() is its repr."""

    def __repr__(self) -> str:
        return f"made-up{chr(10)}{FORGED}"


class OneStrManyLines:
    """An object whose str() is one line and whose repr spans two."""

    def __str__(self) -> str:
        return "made-up"

    def __repr__(self) -> str:
        return f"made-up{chr(10)}{FORGED}"


class NoStr:
    """An object whose str() raises."""

    def __str__(self) -> str:
        raise RuntimeError("no text")

    def __repr__(self) -> str:
        return "NoStr()"


def _client_error() -> ValidationError:
    """A t2v/1 refusal whose text and repr name the key a client added, a forged line in it."""
    body = json.dumps({"token": "a" * 40, "protocol": 1, chr(10) + FORGED: 1})
    with pytest.raises(ValidationError) as raised:
        JoinRequest.model_validate_json(body)
    return raised.value


def _line(capsys: pytest.CaptureFixture[str], **fields: object) -> str:
    configure_logging("INFO", "console")
    get_logger(MODULE).warning("offer_refused", **fields)
    out = capsys.readouterr().out
    assert out.endswith("\n") and len(out.splitlines()) == 1, out
    return out


@pytest.mark.parametrize("brk", BREAKS)
def test_a_value_that_breaks_the_line_is_written_on_it_escaped(
    brk: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Adversarial: a candidate holding a line break (a no-break space for its spaces) and a
    forged line stays one line, and the break is escaped."""
    value = f"x{brk}{FORGED.replace(' ', chr(0xA0))}"
    out = _line(capsys, candidate=value)
    assert f"candidate={value!r}" in out and brk not in out.removesuffix("\n")


@pytest.mark.parametrize(
    "value",
    [
        REDRAW + FORGED,
        f"x{chr(0x202E)}nimda=tcejbus",  # right-to-left override
        f"x{chr(0x200F)}y",  # a right-to-left mark, a format character
        f"x{chr(0xD800)}y",  # a lone surrogate, which no UTF-8 stream writes
    ],
)
def test_an_escape_or_a_format_character_is_written_escaped(
    value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _line(capsys, candidate=value)
    assert f"candidate={value!r}" in out and ESC not in out
    assert not set(out) & {chr(0x200F), chr(0x202E), chr(0xD800)}


@pytest.mark.parametrize("value", [Lines(), OneStrManyLines(), _client_error()])
def test_an_object_whose_text_or_repr_spans_lines_is_written_as_its_text_escaped(
    value: object, capsys: pytest.CaptureFixture[str]
) -> None:
    """Adversarial (a refusal logged as it is, naming the key a client added): its str() is
    written as its repr, one line."""
    out = _line(capsys, error=value)
    assert f"error={str(value)!r}" in out


def test_a_key_that_breaks_the_line_is_written_escaped_and_loses_no_field(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Adversarial: keys from a mapping a client filled, logged as `**mapping`; a key written
    escaped that another field already has takes one more `field_`."""
    forged_key = f"x{chr(10)}{FORGED}"
    taken = repr(f"a{chr(10)}")
    out = _line(capsys, **{forged_key: "admin", f"a{chr(10)}": 1, taken: 2})
    assert f"{forged_key!r}=admin" in out
    assert f" {taken}=2 " in out and f"field_{taken}=1" in out


def test_a_field_with_no_text_is_written_as_its_repr(capsys: pytest.CaptureFixture[str]) -> None:
    out = _line(capsys, value=NoStr())
    assert "value=NoStr()" in out


def test_printable_text_reads_as_it_always_has(capsys: pytest.CaptureFixture[str]) -> None:
    """A Windows path, Arabic text and a dict holding a line break are written as before: the
    first two as they are, the dict as its repr, which escapes the break."""
    path = chr(92).join(["C:", "Users", "made-up"])
    arabic = "".join(map(chr, (0x645, 0x631, 0x62D, 0x628, 0x627)))
    out = _line(capsys, path=path, text=arabic, body={"sdp": f"v=0{chr(13)}{chr(10)}"})
    assert f"path={path} " in out and f"text={arabic}" in out
    assert f"body={ {'sdp': f'v=0{chr(13)}{chr(10)}'}!r}" in out
