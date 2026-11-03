"""Each `t2v/1` route's cap on its body in bytes (api/protocol.py's `BODIES`, `max_bytes`): every
field the caps count takes characters JSON writes in two bytes at most, and each cap holds the
largest body its route takes, built of the costliest character each field allows, so a change to
a bound or a field's characters cannot refuse a valid body unseen."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError
from t2_agentic_voice.api.protocol import (
    BODIES,
    MAX_CANDIDATE_CHARS,
    MAX_CANDIDATES,
    MAX_OFFER_SECRET_CHARS,
    MAX_SDP_CHARS,
    MAX_TOKEN_CHARS,
)
from t2_agentic_voice.core.events import MAX_INDEX

END = {"candidate": "", "sdp_mid": "0", "sdp_mline_index": 0}
OFFER = {"call_id": "c-1", "sdp": "v=0", "type": "offer"}
# Every ASCII character, and others a field might let through: a no-break space, a euro sign,
# a line separator, a byte-order mark and one outside the BMP.
CHARACTERS = [chr(code) for code in range(128)]
CHARACTERS += [chr(code) for code in (0xA0, 0x20AC, 0x2028, 0xFEFF, 0x1F600)]
# Each field the caps count at two bytes a character, its route and its bound, and a body
# valid but for that field's value.
FIELDS: dict[str, tuple[str, int, Callable[[str], dict[str, Any]]]] = {
    "token": ("POST /join", MAX_TOKEN_CHARS, lambda value: {"token": value, "protocol": 1}),
    "sdp": ("POST /offer", MAX_SDP_CHARS, lambda value: OFFER | {"sdp": value}),
    "offer_secret": (
        "POST /offer",
        MAX_OFFER_SECRET_CHARS,
        lambda value: OFFER | {"offer_secret": value},
    ),
    "candidate": (
        "PATCH /offer",
        MAX_CANDIDATE_CHARS,
        lambda value: {"call_id": "c-1", "candidates": [END | {"candidate": value}]},
    ),
    "sdp_mid": (
        "PATCH /offer",
        64,
        lambda value: {"call_id": "c-1", "candidates": [END | {"sdp_mid": value}]},
    ),
    "patch_secret": (
        "PATCH /offer",
        MAX_OFFER_SECRET_CHARS,
        lambda value: {"call_id": "c-1", "candidates": [END], "offer_secret": value},
    ),
}


def _written(character: str) -> int:
    """The most bytes JSON writes `character` in, as a browser's JSON.stringify writes it (UTF-8
    as it is, a control character escaped) or Python's json.dumps (escaped to ASCII)."""
    return max(len(json.dumps(character, ensure_ascii=flag).encode()) - 2 for flag in (True, False))


def _takes(field: str, character: str) -> bool:
    """Whether the field's route takes a body whose field holds `character`, as it parses one."""
    route, _, body = FIELDS[field]
    try:
        BODIES[route].request.model_validate_json(json.dumps(body(character)))
    except ValidationError:
        return False
    return True


def _costliest(field: str) -> str:
    """The character the field takes that JSON writes in the most bytes."""
    return max((each for each in CHARACTERS if _takes(field, each)), key=_written)


@pytest.mark.parametrize("field", list(FIELDS))
def test_every_field_the_caps_count_takes_characters_json_writes_in_two_bytes(field: str) -> None:
    """The caps are twice the longest values a body holds: a field that took a control
    character (six bytes as `\\u0001`), a non-ASCII one (up to four) or an escaped one (up to
    twelve) would let a valid body past its cap."""
    taken = [each for each in CHARACTERS if _takes(field, each)]
    assert taken and max(_written(each) for each in taken) == 2
    assert all(each.isascii() for each in taken)


def _largest(route: str) -> dict[str, Any]:
    """The largest body `route` takes: every value at its bound, each of the costliest character
    its field allows."""

    def longest(field: str) -> str:
        return _costliest(field) * FIELDS[field][1]

    call = {"call_id": "c" * 64}
    if route == "POST /join":
        return {"token": longest("token"), "protocol": MAX_INDEX, "language": "ar-SA"}
    if route == "POST /offer":
        return call | {
            "sdp": longest("sdp"),
            "type": "offer",
            "offer_secret": longest("offer_secret"),
        }
    line = {"candidate": longest("candidate"), "sdp_mid": longest("sdp_mid")}
    candidates = [line | {"sdp_mline_index": MAX_INDEX}] * MAX_CANDIDATES
    return call | {"candidates": candidates, "offer_secret": longest("patch_secret")}


@pytest.mark.parametrize("route", list(BODIES))
def test_each_routes_cap_holds_the_largest_body_it_takes(route: str) -> None:
    body = _largest(route)
    text = json.dumps(body, separators=(",", ":"))  # as a browser's JSON.stringify writes it
    BODIES[route].request.model_validate_json(text)
    assert len(text.encode("utf-8")) <= BODIES[route].max_bytes < 4 * len(text)
