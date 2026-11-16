"""Whose tickets a call sees (ole5_voice/customer.py; plan 007's Q3; docs/SECURITY.md,
invariant 3): the customer the settings name, carried by the join token the app's token route
(the library's, as server.py builds it) mints and the library verifies, read only from then on.
Nothing the request or the call says changes it: a tool bound to it and an action reading it get
the session's customer alone. The route mints at most Ole5's 10 tokens a day."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from ole5_voice.customer import CUSTOMER_EMAIL, CUSTOMER_FIELD, SUBJECT, customer_email
from ole5_voice.server import TOKENS_PER_DAY, build_app
from ole5_voice.settings import AppSettings, Settings
from pydantic import SecretStr, ValidationError
from t2_agentic_voice import Caller, VoiceSettings, from_caller
from t2_agentic_voice.identity import SignedJoinTokens
from t2_agentic_voice.ports import JoinContext
from t2_agentic_voice.stores import MemoryUsedTokens

from tests.ole5_voice.tickets.ticket_support import CUSTOMER, OTHER

CODE = "made-up-access-code-0123"
KEY = "a-made-up-join-key-of-forty-bytes-0123456"
CONSENT = {"version": None, "record_audio": False}


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _client(tokens: SignedJoinTokens, clock: Clock | None = None) -> TestClient:
    """Ole5's app, its demo customer CUSTOMER, minting with `tokens`."""
    app = AppSettings(access_code=SecretStr(CODE), demo_customer_email=CUSTOMER)
    settings = Settings(app=app, voice=VoiceSettings(env="dev"))
    built = build_app(settings, router=APIRouter(), minter=tokens, clock=clock or Clock())
    return TestClient(built, client=("127.0.0.1", 50000))


def _verified(body: dict[str, object]) -> tuple[int, Caller | None]:
    """The token route's answer to `body`, and the caller the library verifies in the token it
    minted, if any."""
    tokens = SignedJoinTokens(keys={"k1": SecretStr(KEY)}, current_kid="k1")
    answer = _client(tokens).post("/token", json=body)
    if answer.status_code != 200:
        return answer.status_code, None
    join = JoinContext(env="dev", client_host="127.0.0.1", used_tokens=MemoryUsedTokens())
    caller, _ = asyncio.run(tokens.verify(answer.json()["token"], join=join))
    return answer.status_code, caller


def test_a_verified_token_names_the_customer_the_route_was_built_for() -> None:
    status, caller = _verified({"code": CODE, "consent": CONSENT})
    assert status == 200 and caller is not None
    assert caller.subject == SUBJECT
    assert customer_email(caller) == CUSTOMER
    assert from_caller(CUSTOMER_FIELD).value(caller) == CUSTOMER  # a tool bound to it


@pytest.mark.parametrize(
    "named",
    [
        {CUSTOMER_EMAIL: OTHER},
        {"attrs": {CUSTOMER_EMAIL: OTHER}},
        {"sub": OTHER},
        {"consent": {**CONSENT, CUSTOMER_EMAIL: OTHER}},
    ],
)
def test_a_request_naming_another_customer_gets_no_token(named: dict[str, object]) -> None:
    status, caller = _verified({"code": CODE, "consent": CONSENT, **named})
    assert (status, caller) == (400, None)


def test_the_callers_customer_cannot_be_changed_once_verified() -> None:
    _, caller = _verified({"code": CODE, "consent": CONSENT})
    assert caller is not None
    with pytest.raises(TypeError):
        caller.attributes[CUSTOMER_EMAIL] = OTHER  # type: ignore[index]
    with pytest.raises(ValidationError):
        caller.attributes = {CUSTOMER_EMAIL: OTHER}  # type: ignore[misc]
    assert customer_email(caller) == CUSTOMER


def test_a_caller_whose_token_named_no_customer_has_none() -> None:
    assert customer_email(Caller(subject="dev")) is None
    assert from_caller(CUSTOMER_FIELD).value(Caller(subject="dev")) is None


def test_ole5s_route_mints_ten_tokens_a_day() -> None:
    clock = Clock()
    test = _client(SignedJoinTokens(keys={"k1": SecretStr(KEY)}, current_kid="k1"), clock)
    for _ in range(TOKENS_PER_DAY):
        assert test.post("/token", json={"code": CODE, "consent": CONSENT}).status_code == 200
        clock.now += 60.0
    refused = test.post("/token", json={"code": CODE, "consent": CONSENT})
    assert (refused.status_code, refused.json()["code"]) == (429, "daily_limit")
    assert TOKENS_PER_DAY == 10
