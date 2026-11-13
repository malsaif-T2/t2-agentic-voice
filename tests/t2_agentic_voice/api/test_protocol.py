"""The HTTP bodies of `t2v/1` (the design's 5.5): each request parsed strictly and bounded, as a
route parses it, and a refusal answered by `refusal` echoing no value (GP-19); a join of another
protocol version answered before the strict parse; a body sent as JSON alone; every secret out of
a body's repr and python-mode dump, and a response's own sent as it is; the one error body; no
`pc_id` in any body (plan 003's appendix, item 10). Each route's cap: test_protocol_caps.py."""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from pydantic import BaseModel, SecretStr, ValidationError
from t2_agentic_voice.api.protocol import (
    BODIES,
    MAX_CANDIDATE_CHARS,
    MAX_CANDIDATES,
    MAX_OFFER_SECRET_CHARS,
    MAX_SDP_CHARS,
    MAX_TOKEN_CHARS,
    MISMATCH_NOTICE,
    OFFER_SECRET_HEADER,
    CandidatesRequest,
    ErrorBody,
    IceCandidate,
    IceServer,
    JoinRequest,
    JoinResponse,
    OfferAnswer,
    OfferRequest,
    is_json,
    refusal,
    version_mismatch,
)
from t2_agentic_voice.core.events import MAX_INDEX
from t2_agentic_voice.core.logging import configure_logging, get_logger
from t2_agentic_voice.voice.protocol import PROTOCOL

from tests.leaks import holding, shown

MARK = "zx-made-up-mark-58"  # a value no refusal may repeat
TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJlLTEifQ.zx-made-up-signature"
SECRET = "zx-made-up-offer-secret-0123456789"
END = {"candidate": "", "sdp_mid": "0", "sdp_mline_index": 0}  # the end of candidates
LINE = "candidate:1 1 udp 2122260223 192.0.2.10 50000 typ host generation 0"
REFERENCE = "made-up-ref-0123"
# Where a model's own refusal carries the input it refused (FastAPI's 422 sends `errors()`).
CARRIED = {"errors", "errors json"}
OFFER = {"call_id": "c-1", "type": "offer"}
# Bodies no route takes, each refused as the route parses it (its JSON text): the router's test
# posts each one (test_router_bodies.py).
ADVERSARIAL: list[tuple[type[BaseModel], dict[str, Any]]] = [
    (JoinRequest, {"token": TOKEN}),
    (JoinRequest, {"protocol": 1}),
    (JoinRequest, {"token": "", "protocol": 1}),
    (JoinRequest, {"token": f"{MARK} x", "protocol": 1}),
    (JoinRequest, {"token": f"{MARK}\n", "protocol": 1}),
    (JoinRequest, {"token": MARK * 500, "protocol": 1}),  # over MAX_TOKEN_CHARS
    (JoinRequest, {"token": 7, "protocol": 1}),
    (JoinRequest, {"token": MARK, "protocol": "1"}),
    (JoinRequest, {"token": MARK, "protocol": 1.0}),
    (JoinRequest, {"token": MARK, "protocol": True}),
    (JoinRequest, {"token": MARK, "protocol": 0}),
    (JoinRequest, {"token": MARK, "protocol": MAX_INDEX + 1}),
    (JoinRequest, {"token": MARK, "protocol": 1, "consent": {"record_audio": True}}),
    (JoinRequest, {"token": TOKEN, "protocol": 1, "language": MARK}),  # not a library tag
    (JoinRequest, {"token": TOKEN, "protocol": 1, "language": "AR-SA"}),
    (JoinRequest, {"token": TOKEN, "protocol": 1, "language": 7}),
    (OfferRequest, {"call_id": "c-1", "sdp": "v=0", "type": "answer"}),  # never an answer
    (OfferRequest, {"call_id": "c-1", "sdp": "v=0"}),
    (OfferRequest, OFFER | {"sdp": ""}),
    (OfferRequest, OFFER | {"sdp": "v" * (MAX_SDP_CHARS + 1)}),
    (OfferRequest, OFFER | {"sdp": f"v=0\r\n{MARK}\x01"}),  # a control character
    (OfferRequest, OFFER | {"sdp": f"v=0\r\ns={MARK}{chr(0x20AC)}"}),  # a euro sign
    (OfferRequest, OFFER | {"sdp": f"v=0\r\ns={MARK}{chr(0x1F600)}"}),  # outside the BMP
    (OfferRequest, {"call_id": f"{MARK}/x", "sdp": "v=0", "type": "offer"}),
    (OfferRequest, OFFER | {"sdp": "v=0", "pc_id": MARK}),
    (OfferRequest, OFFER | {"sdp": "v=0", "offer_secret": ""}),
    (OfferRequest, OFFER | {"sdp": "v=0", "offer_secret": f"{MARK} x"}),
    (OfferRequest, OFFER | {"sdp": "v=0", "offer_secret": MARK * 8}),  # over its bound
    (CandidatesRequest, {"call_id": "c-1", "candidates": []}),
    (CandidatesRequest, {"call_id": "c-1", "candidates": [END] * (MAX_CANDIDATES + 1)}),
    (CandidatesRequest, {"call_id": "c-1", "candidates": {"0": END}}),  # an object, no list
    (CandidatesRequest, {"call_id": "c-1", "candidates": [END], "pc_id": MARK}),
    (CandidatesRequest, {"call_id": "c-1", "candidates": [END | {"sdp_mid": None}]}),
    (CandidatesRequest, {"call_id": "c-1", "candidates": [END | {"sdp_mid": ""}]}),
    (CandidatesRequest, {"call_id": "c-1", "candidates": [END | {"sdpMid": "0"}]}),
    (CandidatesRequest, {"call_id": "c-1", "candidates": [{"candidate": "", "sdp_mid": "0"}]}),
    (CandidatesRequest, {"call_id": "c-1", "candidates": [END | {"sdp_mline_index": -1}]}),
    (CandidatesRequest, {"call_id": "c-1", "candidates": [END | {"sdp_mline_index": "0"}]}),
    (CandidatesRequest, {"call_id": "c-1", "candidates": [END | {"candidate": f"{MARK}\r\n"}]}),
    (
        CandidatesRequest,
        {"call_id": "c-1", "candidates": [END | {"candidate": "c" * (MAX_CANDIDATE_CHARS + 1)}]},
    ),
]


def test_each_request_takes_what_a_browser_sends() -> None:
    join = JoinRequest.model_validate({"token": TOKEN, "protocol": 1})
    assert (join.token.get_secret_value(), join.protocol, join.language) == (TOKEN, 1, None)
    picked = JoinRequest.model_validate({"token": TOKEN, "protocol": 1, "language": "ar-SA"})
    assert picked.language == "ar-SA"
    sdp = "v=0\r\no=- 1 2 IN IP4 127.0.0.1\r\ns=-\r\na=msid-semantic:\tWMS {made-up}\r\n"
    offer = OfferRequest.model_validate(OFFER | {"sdp": sdp, "offer_secret": SECRET})
    assert offer.offer_secret is not None and offer.offer_secret.get_secret_value() == SECRET
    assert offer.sdp == sdp
    assert OfferRequest.model_validate(OFFER | {"sdp": "v=0"}).offer_secret is None
    trickled = CandidatesRequest.model_validate(
        {
            "call_id": "c-1",
            "candidates": [{"candidate": LINE, "sdp_mid": "0", "sdp_mline_index": 0}, END],
        }
    )
    assert [c.candidate for c in trickled.candidates] == [LINE, ""]
    assert OFFER_SECRET_HEADER == "X-T2V-Offer-Secret"


@pytest.mark.parametrize(("model", "body"), ADVERSARIAL)
def test_a_request_that_is_not_exactly_its_body_is_refused_and_answered_echoing_none_of_it(
    model: type[BaseModel], body: dict[str, Any]
) -> None:
    """As a route parses it (`model_validate_json` of the body's JSON text), and in python mode
    too: the model's refusal keeps the value out of its text, repr and traceback, but its
    `errors()` and `json()` may carry it, so the route answers with `refusal`, which holds none.
    A `/join` body whose `protocol` is not the integer 1 is answered earlier, by
    `version_mismatch`, which holds none either."""
    assert len(MARK * 500) > MAX_TOKEN_CHARS and len(MARK * 8) > MAX_OFFER_SECRET_CHARS
    text = json.dumps(body)
    with pytest.raises(ValidationError) as as_sent:
        model.model_validate_json(text)
    with pytest.raises(ValidationError) as as_given:
        model.model_validate(body)
    for error in (as_sent.value, as_given.value):
        assert set(holding(MARK, shown(error))) <= CARRIED
        answer = refusal(error, reference=REFERENCE)
        assert (answer.code, answer.notice) == ("invalid_request", None)
        assert MARK not in answer.model_dump_json() and MARK not in repr(answer)
    mismatch = version_mismatch(text.encode(), reference=REFERENCE)
    named = body.get("protocol", PROTOCOL)
    assert (mismatch is None) == (model is not JoinRequest or (type(named) is int and named == 1))
    assert mismatch is None or MARK not in mismatch.model_dump_json()


@pytest.mark.parametrize(
    "text",
    [
        f'{{"token": "{MARK} x", "protocol": 1}}',
        f'{{"token": "{TOKEN}", "protocol": 1, "{MARK}": 1}}',  # the client's own key
        f'{{"token": "{TOKEN}", "protocol": 1, "language": "{MARK}"}}',
        f'{{"token": "{MARK}"',  # not JSON
        f'["{MARK}"]',
    ],
)
def test_a_body_as_the_route_reads_it_is_answered_echoing_none_of_it(text: str) -> None:
    """As a route parses it (`model_validate_json`): the value, or a key the client sent, is in
    the error's `errors()` (a key in its text too), never in the answer, which names pydantic's
    error types alone."""
    assert version_mismatch(text.encode(), reference=REFERENCE) is None  # the version is 1
    with pytest.raises(ValidationError) as raised:
        JoinRequest.model_validate_json(text)
    assert set(holding(MARK, shown(raised.value))) >= CARRIED
    answer = refusal(raised.value, reference=REFERENCE).model_dump(mode="json")
    assert MARK not in json.dumps(answer) and answer["reference"] == REFERENCE
    problems = ", ".join(sorted({each["type"] for each in raised.value.errors()}))
    assert answer["message"] == f"The request's body is not one t2v/1 takes ({problems})."


@pytest.mark.parametrize(
    "body",
    [
        {"token": "x", "protocol": 2, "capabilities": []},  # another version adds a field
        {"join_token": MARK, "protocol": 2},  # renames one
        {"token": MARK, "protocol": 2, "language": "fr"},  # adds a language
        {"token": MARK, "protocol": 2},  # v1's own shape
        {"token": MARK, "protocol": "1"},
        {"token": MARK, "protocol": 1.0},
        {"token": MARK, "protocol": True},
        {"token": MARK, "protocol": None},
        {"token": MARK, "protocol": [1]},
    ],
)
def test_a_join_of_another_version_gets_the_notice_whatever_else_its_body_holds(
    body: dict[str, Any],
) -> None:
    """The design's 5.4: the version check is stable, so it reads the body's top-level
    `protocol` alone, before the strict parse; any value but the integer 1 is another version,
    answered with the notice and echoing nothing."""
    answer = version_mismatch(json.dumps(body).encode(), reference=REFERENCE)
    assert answer is not None
    assert (answer.code, answer.notice, answer.reference) == (
        "protocol_mismatch",
        MISMATCH_NOTICE,
        REFERENCE,
    )
    assert MARK not in answer.model_dump_json()
    assert BODIES["POST /join"].errors[400] == ("invalid_request", "protocol_mismatch")


@pytest.mark.parametrize(
    "text",
    [
        b'{"token": "x", "protocol": 1}',  # this version
        b'{"token": "x", "protocol": 1, "capabilities": []}',  # this version, refused later
        b'{"token": "x"}',  # none named
        b'{"protocol": 2',  # not JSON
        b'{"protocol": 2} x',
        b'\xef\xbb\xbf{"protocol": 2}',  # a byte-order mark, as the strict parse refuses it
        b'[{"protocol": 2}]',  # a list
        b'"protocol"',  # a string
        b"",
    ],
)
def test_a_body_that_names_this_version_or_none_goes_on_to_the_strict_parse(
    text: bytes,
) -> None:
    assert version_mismatch(text, reference=REFERENCE) is None


@pytest.mark.parametrize(
    ("content_type", "taken"),
    [
        ("application/json", True),
        ("application/json; charset=utf-8", True),
        ("Application/JSON ;charset=UTF-8", True),
        ("application/json\t", True),
        (None, False),  # none at all
        ("", False),
        ("text/plain", False),  # a form or text/plain skips the CORS preflight
        ("text/plain; charset=utf-8", False),
        ("application/x-www-form-urlencoded", False),
        ("multipart/form-data; boundary=x", False),
        ("text/plain; application/json", False),
        ("application/json, text/plain", False),
        ("application/jsonp", False),
        ("application/json-patch+json", False),
        ('"application/json"', False),
    ],
)
def test_a_route_takes_a_body_sent_as_json_alone(content_type: str | None, taken: bool) -> None:
    """A page on any origin may send a form or text/plain to another with no preflight, so every
    `t2v/1` route answers any other type 415 before it reads the body."""
    assert is_json(content_type) is taken
    assert all(route.errors[415] == ("unsupported_media_type",) for route in BODIES.values())


def test_no_secret_shows_in_a_bodys_repr_or_a_log_line(caplog: pytest.LogCaptureFixture) -> None:
    join = JoinRequest.model_validate({"token": TOKEN, "protocol": PROTOCOL})
    offer = OfferRequest.model_validate(
        {"call_id": "c-1", "sdp": "v=0", "type": "offer", "offer_secret": SECRET}
    )
    trickled = CandidatesRequest.model_validate(
        {"call_id": "c-1", "candidates": [END], "offer_secret": SECRET}
    )
    answer = JoinResponse(
        call_id="c-1",
        offer_secret=SecretStr(SECRET),
        ice_servers=(
            IceServer(
                urls=("turn:turn.example:3478",), username="9:c-1", credential=SecretStr(MARK)
            ),
        ),
    )
    logging.getLogger("tests.protocol").warning("bodies %r %s %r %s", join, offer, trickled, answer)
    for value in (TOKEN, SECRET, MARK):
        assert holding(value, shown(caplog=caplog)) == []


def test_no_secret_shows_in_a_python_mode_dump_or_a_line_built_from_it(
    caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    """A python-mode dump keeps each SecretStr: a line that logs a body's dump, in either format,
    holds neither the offer secret nor the TURN password."""
    caplog.set_level(logging.DEBUG)
    credential = SecretStr(MARK)
    answer = JoinResponse(
        call_id="c-1",
        offer_secret=SecretStr(SECRET),
        ice_servers=(IceServer(urls=("turn:turn.example:3478",), credential=credential),),
    )
    dumped = answer.model_dump()
    assert dumped["offer_secret"] == SecretStr(SECRET)
    assert dumped["ice_servers"][0]["credential"] == credential
    for fmt in ("json", "console"):
        configure_logging("DEBUG", fmt)
        get_logger("t2_agentic_voice.tests").debug("join_answered", body=dumped)
    surfaces = shown(caplog=caplog, capsys=capsys)
    assert "join_answered" in surfaces["stdout"]
    assert holding(SECRET, surfaces) == holding(MARK, surfaces) == []


def test_a_response_sends_its_own_secrets_as_they_are() -> None:
    """The join's answer carries the call's offer secret and the TURN password to the one client
    that joined: revealed only when the body is serialized to JSON, as it is sent."""
    answer = JoinResponse(
        call_id="c-1",
        offer_secret=SecretStr(SECRET),
        ice_servers=(
            IceServer(urls=("stun:stun.example:3478",)),
            IceServer(
                urls=("turns:turn.example:443?transport=tcp",),
                username="9:c-1",
                credential=SecretStr(MARK),
            ),
        ),
    )
    assert answer.model_dump(mode="json") == {
        "call_id": "c-1",
        "offer_secret": SECRET,
        "ice_servers": [
            {"urls": ["stun:stun.example:3478"], "username": None, "credential": None},
            {
                "urls": ["turns:turn.example:443?transport=tcp"],
                "username": "9:c-1",
                "credential": MARK,
            },
        ],
        "protocol": PROTOCOL,
    }
    assert json.loads(answer.model_dump_json()) == answer.model_dump(mode="json")
    assert OfferAnswer(sdp="v=0").model_dump() == {"sdp": "v=0", "type": "answer"}


def test_each_route_names_its_bodies_and_none_carries_a_pc_id() -> None:
    assert list(BODIES) == ["POST /join", "POST /offer", "PATCH /offer"]
    routes = BODIES.values()
    models = [m for r in routes for m in (r.request, r.response) if m is not None]
    assert all("pc_id" not in m.model_fields for m in [*models, IceCandidate, IceServer])
    assert all(m.model_config.get("extra") == "forbid" for m in [*models, ErrorBody])
    assert all(set(r.errors).isdisjoint({r.status}) for r in routes)


def test_the_error_body_carries_a_notice_only_with_a_protocol_mismatch() -> None:
    mismatch = ErrorBody(
        code="protocol_mismatch",
        message="This page speaks another version of the protocol.",
        notice="Reload the page to call again.",
        reference=REFERENCE,
    )
    assert mismatch.model_dump(mode="json") == {
        "code": "protocol_mismatch",
        "message": "This page speaks another version of the protocol.",
        "notice": "Reload the page to call again.",
        "reference": REFERENCE,
    }
    refused = [
        {"code": "protocol_mismatch"},  # with no notice
        {"code": "join_rejected", "notice": "Reload the page."},
        {"code": "join_rejected", "reference": "short"},
        {"code": "join_rejected", "reference": f"{REFERENCE}/x"},
        {"code": "made_up"},
        {"code": "join_rejected", "message": ""},
    ]
    for changed in refused:
        with pytest.raises(ValidationError):
            ErrorBody.model_validate({"message": "Refused.", "reference": REFERENCE} | changed)
