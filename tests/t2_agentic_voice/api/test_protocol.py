"""The HTTP bodies of `t2v/1` (the design's 5.5): each request parsed strictly and bounded, refused
without echoing a value (GP-19); every secret out of a body's repr, and a response's own sent as
it is; no `pc_id` in any body (plan 003's appendix, item 10)."""

from __future__ import annotations

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
    OFFER_SECRET_HEADER,
    CandidatesRequest,
    IceCandidate,
    IceServer,
    JoinRequest,
    JoinResponse,
    OfferAnswer,
    OfferRequest,
)
from t2_agentic_voice.core.events import MAX_INDEX
from t2_agentic_voice.voice.protocol import PROTOCOL

from tests.leaks import holding, shown

MARK = "zx-made-up-mark-58"  # a value no refusal may repeat
TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJlLTEifQ.zx-made-up-signature"
SECRET = "zx-made-up-offer-secret-0123456789"
END = {"candidate": "", "sdp_mid": "0", "sdp_mline_index": 0}  # the end of candidates
LINE = "candidate:1 1 udp 2122260223 192.0.2.10 50000 typ host generation 0"


def test_each_request_takes_what_a_browser_sends() -> None:
    join = JoinRequest.model_validate({"token": TOKEN, "protocol": 1})
    assert (join.token.get_secret_value(), join.protocol) == (TOKEN, 1)
    offer = OfferRequest.model_validate(
        {"call_id": "c-1", "sdp": "v=0\r\n", "type": "offer", "offer_secret": SECRET}
    )
    assert offer.offer_secret is not None and offer.offer_secret.get_secret_value() == SECRET
    assert (
        OfferRequest.model_validate({"call_id": "c-1", "sdp": "v=0", "type": "offer"}).offer_secret
        is None
    )
    trickled = CandidatesRequest.model_validate(
        {
            "call_id": "c-1",
            "candidates": [{"candidate": LINE, "sdp_mid": "0", "sdp_mline_index": 0}, END],
        }
    )
    assert [c.candidate for c in trickled.candidates] == [LINE, ""]
    assert OFFER_SECRET_HEADER == "X-T2V-Offer-Secret"


def _refused(model: type[BaseModel], body: dict[str, Any]) -> ValidationError:
    with pytest.raises(ValidationError) as raised:
        model.model_validate(body)
    return raised.value


@pytest.mark.parametrize(
    ("model", "body"),
    [
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
        (OfferRequest, {"call_id": "c-1", "sdp": "v=0", "type": "answer"}),  # never an answer
        (OfferRequest, {"call_id": "c-1", "sdp": "v=0"}),
        (OfferRequest, {"call_id": "c-1", "sdp": "", "type": "offer"}),
        (OfferRequest, {"call_id": "c-1", "sdp": "v" * (MAX_SDP_CHARS + 1), "type": "offer"}),
        (OfferRequest, {"call_id": f"{MARK}/x", "sdp": "v=0", "type": "offer"}),
        (OfferRequest, {"call_id": "c-1", "sdp": "v=0", "type": "offer", "pc_id": MARK}),
        (OfferRequest, {"call_id": "c-1", "sdp": "v=0", "type": "offer", "offer_secret": ""}),
        (
            OfferRequest,
            {"call_id": "c-1", "sdp": "v=0", "type": "offer", "offer_secret": f"{MARK} x"},
        ),
        (
            OfferRequest,
            {"call_id": "c-1", "sdp": "v=0", "type": "offer", "offer_secret": MARK * 8},
        ),  # over MAX_OFFER_SECRET_CHARS
        (CandidatesRequest, {"call_id": "c-1", "candidates": []}),
        (CandidatesRequest, {"call_id": "c-1", "candidates": [END] * (MAX_CANDIDATES + 1)}),
        (CandidatesRequest, {"call_id": "c-1", "candidates": (END,)}),
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
            {
                "call_id": "c-1",
                "candidates": [END | {"candidate": "c" * (MAX_CANDIDATE_CHARS + 1)}],
            },
        ),
    ],
)
def test_a_request_that_is_not_exactly_its_body_is_refused_echoing_none_of_it(
    model: type[BaseModel], body: dict[str, Any]
) -> None:
    assert len(MARK * 500) > MAX_TOKEN_CHARS and len(MARK * 8) > MAX_OFFER_SECRET_CHARS
    assert holding(MARK, shown(_refused(model, body))) == []


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


def test_a_response_sends_its_own_secrets_as_they_are() -> None:
    """The join's answer carries the call's offer secret and the TURN password to the one client
    that joined: revealed only when the body is sent."""
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
    assert OfferAnswer(sdp="v=0").model_dump() == {"sdp": "v=0", "type": "answer"}


def test_each_route_names_its_bodies_and_none_carries_a_pc_id() -> None:
    assert list(BODIES) == ["POST /join", "POST /offer", "PATCH /offer"]
    models = [m for pair in BODIES.values() for m in pair if m is not None]
    assert all("pc_id" not in m.model_fields for m in [*models, IceCandidate, IceServer])
    assert all(m.model_config.get("extra") == "forbid" for m in models)
