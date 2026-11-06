"""How a client's `t2v/1` message is read before it is parsed (voice/protocol.py's
`parse_client_message`): its JSON value from the object Pipecat parsed or from the text itself,
refused by its size in bytes, as JSON it is not, or for a key held twice; and the one error a
refused message is, naming only the kinds of problem, never a value, a key or a type the client
sent (docs/SECURITY.md's trust boundaries).
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from pydantic import JsonValue

from t2_agentic_voice.core.errors import InvalidRequestError


class _KeyTwiceError(Exception):
    """A JSON object of the client's holds one key twice."""


def _once(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """A JSON object's members, refusing a key held twice: `json.loads` would keep its last
    value, and a reader that took the first would see another message."""
    members = dict(pairs)
    if len(members) != len(pairs):
        raise _KeyTwiceError
    return members


def read_json(message: object, *, limit: int) -> tuple[object, str | None]:
    """`message`'s JSON value, or the kind of problem that refuses it before it is read as a
    message: its size in bytes, over `limit`, JSON it is not, or a key held twice."""
    if isinstance(message, str | bytes) and len(message) > limit:
        return None, "too_large"  # a character is a byte or more, so its bytes are too
    try:
        if isinstance(message, str | bytes):
            text = message.encode() if isinstance(message, str) else message
            if len(text) > limit:
                return None, "too_large"
            return json.loads(text.decode(), object_pairs_hook=_once), None
        written = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode()
    except _KeyTwiceError:
        return None, "duplicate_key"
    except (TypeError, ValueError, RecursionError):  # not UTF-8, not JSON, or not writable
        return None, "json_invalid"
    return (None, "too_large") if len(written) > limit else (message, None)


def refused(problems: Iterable[str]) -> InvalidRequestError:
    """The error for a client's message refused for `problems`, the kinds of problem alone."""
    found: list[JsonValue] = []
    found.extend(sorted(problems))
    return InvalidRequestError(
        "The client sent a message that is not one of t2v/1's.", details={"problems": found}
    )
