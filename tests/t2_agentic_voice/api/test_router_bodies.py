"""How each `t2v/1` route reads its body (api/http_errors.py; D-029): JSON alone, 415 before a byte
is read; never past its cap, 413 from a true length, from none (chunked) and from one that lies;
each body the protocol's own test refuses answered 400 in the one shape, echoing nothing it sent;
and a join of another protocol version answered with its notice before the token is verified."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel
from t2_agentic_voice.api.protocol import (
    BODIES,
    MISMATCH_NOTICE,
    CandidatesRequest,
    JoinRequest,
    OfferRequest,
)

from tests.t2_agentic_voice.api.runtime_support import (
    PREFIX,
    Harness,
    dev_settings,
    refused,
    serving,
)
from tests.t2_agentic_voice.api.test_protocol import ADVERSARIAL, MARK

pytestmark = pytest.mark.usefixtures("patched_stores")

ROUTES = {"POST /join": JoinRequest, "POST /offer": OfferRequest, "PATCH /offer": CandidatesRequest}
NOT_JSON = [
    "text/plain",
    "application/x-www-form-urlencoded",
    "multipart/form-data; boundary=zx",
    None,
]


def _split(route: str) -> tuple[str, str]:
    method, path = route.split(" ")
    return method, PREFIX + path


@pytest.mark.parametrize("route", sorted(ROUTES))
@pytest.mark.parametrize("content_type", NOT_JSON)
def test_a_body_not_sent_as_json_is_refused_before_a_byte_is_read(
    route: str, content_type: str | None, tmp_path: Path
) -> None:
    harness = Harness(dev_settings(tmp_path))
    read: list[bytes] = []

    async def body() -> AsyncIterator[bytes]:
        read.append(b"{}")
        yield b'{"token": "x", "protocol": 1}'

    async def scene() -> None:
        method, path = _split(route)
        headers = {} if content_type is None else {"content-type": content_type}
        async with serving(harness.app()) as http:
            answer = await http.request(method, path, content=body(), headers=headers)
        assert answer.status_code == 415
        refused(answer, route, "unsupported_media_type")
        assert read == [] and harness.identity.asked == []

    asyncio.run(scene())


@pytest.mark.parametrize("route", sorted(ROUTES))
@pytest.mark.parametrize("how", ["true length", "chunked", "lying length"])
def test_a_body_over_its_cap_is_refused_in_the_one_shape(
    route: str, how: str, tmp_path: Path
) -> None:
    harness = Harness(dev_settings(tmp_path))
    cap = BODIES[route].max_bytes
    over = b"[" + b" " * cap + b"]"

    async def chunks() -> AsyncIterator[bytes]:
        for start in range(0, len(over), 4096):
            yield over[start : start + 4096]

    async def scene() -> None:
        method, path = _split(route)
        headers = {"content-type": "application/json"}
        content: bytes | AsyncIterator[bytes] = over
        if how == "chunked":
            content = chunks()
        elif how == "lying length":
            content, headers["content-length"] = chunks(), "2"
        async with serving(harness.app()) as http:
            answer = await http.request(method, path, content=content, headers=headers)
        assert answer.status_code == 413
        refused(answer, route, "too_large")

    asyncio.run(scene())


def test_a_length_that_is_no_number_is_counted_as_the_body_streams(tmp_path: Path) -> None:
    harness = Harness(dev_settings(tmp_path))

    async def scene() -> None:
        async with serving(harness.app()) as http:
            body = json.dumps({"token": "x", "protocol": 2}).encode()
            answer = await http.post(
                PREFIX + "/join",
                content=body,
                headers={"content-type": "application/json; charset=utf-8", "content-length": "x"},
            )
        assert answer.status_code == 400
        refused(answer, "POST /join", "protocol_mismatch")

    asyncio.run(scene())


ROUTED: list[tuple[str, type[BaseModel], dict[str, Any]]] = [
    (route, model, body)
    for model, body in ADVERSARIAL
    for route, taken in ROUTES.items()
    if taken is model
]


@pytest.mark.parametrize(("route", "model", "body"), ROUTED)
def test_each_refused_body_is_answered_400_echoing_none_of_it(
    route: str, model: type[BaseModel], body: dict[str, Any], tmp_path: Path
) -> None:
    """Each body the protocol's test refuses, posted as a client would: parsed before its
    secret is looked at, refused with pydantic's error types alone, the token never verified."""
    harness = Harness(dev_settings(tmp_path))

    async def scene() -> None:
        method, path = _split(route)
        async with serving(harness.app()) as http:
            answer = await http.request(
                method, path, content=json.dumps(body), headers={"content-type": "application/json"}
            )
        named = body.get("protocol", 1)
        wrong_version = model is JoinRequest and not (type(named) is int and named == 1)
        assert answer.status_code == 400
        refused(answer, route, "protocol_mismatch" if wrong_version else "invalid_request")
        assert MARK not in answer.text
        assert harness.identity.asked == []

    asyncio.run(scene())


def test_a_join_of_another_version_gets_its_notice_and_spends_no_token(tmp_path: Path) -> None:
    harness = Harness(dev_settings(tmp_path))

    async def scene() -> None:
        async with serving(harness.app()) as http:
            answer = await http.post(
                PREFIX + "/join",
                content=json.dumps({"token": "x", "protocol": 2, "capabilities": []}),
                headers={"content-type": "application/json"},
            )
        assert answer.status_code == 400
        body = refused(answer, "POST /join", "protocol_mismatch")
        assert body["notice"] == MISMATCH_NOTICE
        assert harness.identity.asked == []

    asyncio.run(scene())
