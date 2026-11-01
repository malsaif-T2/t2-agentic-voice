"""Items written as TOML, in their fixed shape, with no TOML-writing package (plan 002's decision
log): the item's own keys, then one `[[variants]]` table each, with its `[[variants.segments]]`
and `[[variants.confirmations]]`. `tomllib` reads the text back as the same item, which the
tests check by a round trip; a key whose value is None is left out, as TOML has no null.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from ole5_voice.evals.models import Item

# TOML basic strings escape these by name; any other control character as \uXXXX.
_NAMED = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f", "\r": "\\r"}

Value = str | int | datetime | Sequence[str] | Sequence[int]


def dump_item(item: Item, *, comments: Sequence[str] = ()) -> str:
    """The TOML text of `item`, which `tomllib` reads back as the same item; each of `comments`
    becomes a `#` line at its top (a draft's note, say), which reading drops."""
    lines = [_comment(text) for text in comments]
    lines += _keys(
        [
            ("id", item.id),
            ("source", item.source),
            ("kind", item.kind),
            ("language", item.language),
            ("text", item.text),
            ("alternatives", item.alternatives),
            ("terms", item.terms),
            ("want", item.want),
        ]
    )
    for variant in item.variants:
        lines += ["", "[[variants]]"]
        lines += _keys(
            [
                ("id", variant.id),
                ("device", variant.device),
                ("session", variant.session),
                ("reference", variant.reference),
                ("reference_source", variant.reference_source),
                ("turn_ends_ms", variant.turn_ends_ms),
                ("tags", variant.tags),
            ]
        )
        for segment in variant.segments:
            lines += ["", "[[variants.segments]]"]
            lines += _keys(
                [("root", segment.root), ("path", segment.path), ("sha256", segment.sha256)]
            )
        for confirmation in variant.confirmations:
            lines += ["", "[[variants.confirmations]]"]
            lines += _keys([("at", confirmation.at), ("review_pass", confirmation.review_pass)])
    return "\n".join(lines) + "\n"


def _keys(pairs: Sequence[tuple[str, Value | None]]) -> list[str]:
    return [f"{key} = {_value(value)}" for key, value in pairs if value is not None]


def _value(value: Value) -> str:
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()  # an offset or a local date-time, as TOML writes them
    return "[" + ", ".join(_value(entry) for entry in value) + "]"


def _string(text: str) -> str:
    """`text` as a TOML basic string: every character as itself but the quote, the backslash
    and the control characters, which are escaped."""
    escaped = "".join(
        _NAMED.get(c) or (f"\\u{ord(c):04x}" if ord(c) < 0x20 or ord(c) == 0x7F else c)
        for c in text
    )
    return f'"{escaped}"'


def _comment(text: str) -> str:
    """One `#` line; a line break in it would end the comment and start TOML, so it is refused."""
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in text if c != "\t"):
        raise ValueError("a comment is one line of text")
    return f"# {text}".rstrip()
