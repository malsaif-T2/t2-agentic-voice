"""The Ole5 app's token route (ole5_voice/token_route.py, plan 003's Q4): a join token only for
the owner's access code, compared in constant time; an address's repeated wrong codes slowed; the
route closed by the hour's 20th wrong code until a restart; at most 10 tokens a day; the consent
of the request passed into the token as it came, the customer the route was built for named in
it, and nothing else of the body taken. The address a proxy forwards is taken only from a
trusted one: tests/ole5_voice/test_server.py runs the route behind uvicorn's configuration."""

from __future__ import annotations

import hmac
import json
from collections.abc import Iterator, Mapping
from typing import Any, Protocol

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from ole5_voice.customer import CUSTOMER_EMAIL, customer_email
from ole5_voice.token_route import (
    DAY_S,
    HOUR_S,
    MAX_BODY_BYTES,
    SUBJECT,
    TOKENS_PER_DAY,
    WRONG_PER_HOUR,
    Guard,
    token_router,
)
from pydantic import SecretStr
from t2_agentic_voice import Caller, Consent

from tests.leaks import holding, shown

CODE = "made-up-access-code-0123"
WRONG = "not-the-code-at-all-0123"
CONSENT = {"version": "m2-owner-test-1", "record_audio": True}
CUSTOMER = "made-up.customer@example.com"
OTHER = "someone.else@example.com"


class Response(Protocol):
    """What the test client answers, as these tests read it."""

    status_code: int

    @property
    def headers(self) -> Mapping[str, str]: ...

    @property
    def text(self) -> str: ...

    def json(self) -> Any: ...


class Minter:
    """Mints made-up tokens, keeping what each was minted for."""

    def __init__(self) -> None:
        self.minted: list[tuple[Caller, Consent, str]] = []

    def mint(self, caller: Caller, *, consent: Consent) -> str:
        token = f"made-up-token-{len(self.minted)}"
        self.minted.append((caller, consent, token))
        return token


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def minter() -> Minter:
    return Minter()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def app(minter: Minter, clock: Clock) -> FastAPI:
    app = FastAPI()
    app.include_router(
        token_router(SecretStr(CODE), minter, customer_email=CUSTOMER, guard=Guard(clock=clock))
    )
    return app


def client(app: FastAPI, address: str = "203.0.113.7") -> TestClient:
    return TestClient(app, client=(address, 50000))


def ask(
    app: FastAPI, code: str = CODE, consent: object = None, address: str = "203.0.113.7"
) -> Response:
    body = {"code": code, "consent": CONSENT if consent is None else consent}
    return client(app, address).post("/token", json=body)


def test_the_right_code_mints_a_token_carrying_the_consent_given(
    app: FastAPI, minter: Minter
) -> None:
    answer = ask(app)
    assert answer.status_code == 200
    assert answer.json() == {"token": "made-up-token-0"}
    assert answer.headers["cache-control"] == "no-store"
    caller, consent, _ = minter.minted[0]
    assert caller == Caller(subject=SUBJECT, attributes={CUSTOMER_EMAIL: CUSTOMER})
    assert customer_email(caller) == CUSTOMER
    assert consent == Consent(version="m2-owner-test-1", record_audio=True)
    declined = {"version": "m2-owner-test-1", "record_audio": False}
    assert ask(app, consent=declined).status_code == 200
    assert minter.minted[1][1] == Consent(version="m2-owner-test-1", record_audio=False)
    unversioned = {"version": None, "record_audio": False}
    assert ask(app, consent=unversioned).status_code == 200
    assert minter.minted[2][1] == Consent(version=None, record_audio=False)


def test_the_body_can_set_nothing_but_the_code_and_the_consent(
    app: FastAPI, minter: Minter
) -> None:
    """No caller, subject, customer or other claim is taken from the request: the token names
    the owner as the customer the route was built for (invariant 3), and its consent is the one
    the request carried, which no later message changes."""
    extra = {"code": CODE, "consent": CONSENT, "subject": "someone-else"}
    assert client(app).post("/token", json=extra).json()["code"] == "invalid_request"
    nested = {"code": CODE, "consent": {**CONSENT, "subject": "someone-else"}}
    assert client(app).post("/token", json=nested).json()["code"] == "invalid_request"
    for named in (
        {CUSTOMER_EMAIL: OTHER},
        {"attributes": {CUSTOMER_EMAIL: OTHER}},
        {"attrs": {CUSTOMER_EMAIL: OTHER}},
        {"consent": {**CONSENT, CUSTOMER_EMAIL: OTHER}},
    ):
        answer = client(app).post("/token", json={"code": CODE, "consent": CONSENT, **named})
        assert answer.json()["code"] == "invalid_request"
        assert holding(OTHER, {"answer": answer.text}) == []
    assert minter.minted == []


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[]",
        b'{"code": "' + CODE.encode() + b'"}',
        b'{"consent": {"version": null, "record_audio": true}}',
        b'{"code": 12345678901234567, "consent": {"version": null, "record_audio": true}}',
        b'{"code": "", "consent": {"version": null, "record_audio": true}}',
        b'{"code": "' + b"x" * 257 + b'", "consent": {"version": null, "record_audio": true}}',
        b'{"code": "c", "consent": {"version": "has a space", "record_audio": true}}',
        b'{"code": "c", "consent": {"record_audio": true}}',
    ]
    + [
        b'{"code": "c", "consent": {"version": null, "record_audio": ' + value + b"}}"
        for value in (b'"true"', b'"false"', b"1", b"0", b"null")
    ],
)
def test_a_body_that_is_not_a_code_and_a_consent_is_refused(
    app: FastAPI, minter: Minter, body: bytes, caplog: pytest.LogCaptureFixture
) -> None:
    answer = client(app).post("/token", content=body, headers={"content-type": "application/json"})
    assert answer.status_code == 400
    assert answer.json() == {
        "code": "invalid_request",
        "message": "The request's body is not a code and a consent.",
    }
    assert minter.minted == []
    assert holding("has a space", {"answer": answer.text, **shown(caplog=caplog)}) == []


@pytest.mark.parametrize(
    "content_type", [None, "text/plain", "application/x-www-form-urlencoded", "multipart/form-data"]
)
def test_a_body_not_sent_as_json_is_refused_unread(
    app: FastAPI, minter: Minter, content_type: str | None
) -> None:
    headers = {} if content_type is None else {"content-type": content_type}
    body = json.dumps({"code": CODE, "consent": CONSENT}).encode()
    answer = client(app).post("/token", content=body, headers=headers)
    assert (answer.status_code, answer.json()["code"]) == (415, "unsupported_media_type")
    sent_as = {"content-type": "application/json; charset=utf-8"}
    assert client(app).post("/token", content=body, headers=sent_as).status_code == 200
    assert len(minter.minted) == 1


def test_a_body_over_the_cap_is_refused(app: FastAPI, minter: Minter) -> None:
    padded = json.dumps({"code": CODE, "consent": CONSENT, "pad": "x" * MAX_BODY_BYTES}).encode()
    headers = {"content-type": "application/json"}
    answer = client(app).post("/token", content=padded, headers=headers)
    assert (answer.status_code, answer.json()["code"]) == (413, "too_large")

    def chunks() -> Iterator[bytes]:  # no length given: refused as it streams past the cap
        yield padded[:600]
        yield padded[600:]

    streamed = client(app).post("/token", content=chunks(), headers=headers)
    assert (streamed.status_code, streamed.json()["code"]) == (413, "too_large")
    assert minter.minted == []


def test_the_code_is_compared_in_constant_time(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    compared: list[tuple[bytes, bytes]] = []
    original = hmac.compare_digest

    def compare(given: bytes, expected: bytes) -> bool:
        compared.append((given, expected))
        return original(given, expected)

    monkeypatch.setattr(hmac, "compare_digest", compare)  # as the route reads it
    assert ask(app, code=WRONG).status_code == 403
    assert ask(app, address="198.51.100.1").status_code == 200
    assert compared == [(WRONG.encode(), CODE.encode()), (CODE.encode(), CODE.encode())]


def test_a_wrong_code_is_refused_and_nothing_shows_either_code(
    app: FastAPI, minter: Minter, caplog: pytest.LogCaptureFixture
) -> None:
    answer = ask(app, code=WRONG)
    assert answer.status_code == 403
    assert answer.json() == {"code": "wrong_code", "message": "The access code is not right."}
    assert minter.minted == []
    right = ask(app, address="198.51.100.1")
    surfaces = {"answers": answer.text + right.text, **shown(caplog=caplog)}
    assert holding(WRONG, surfaces) == holding(CODE, surfaces) == []
    assert holding("made-up-token-0", shown(caplog=caplog)) == []
    assert [r.fields.get("reason") for r in caplog.records if r.msg == "token_refused"] == [  # type: ignore[attr-defined]
        "wrong_code"
    ]


def test_repeated_wrong_codes_from_one_address_are_slowed(app: FastAPI, clock: Clock) -> None:
    assert ask(app, code=WRONG).status_code == 403
    slowed = ask(app, code=WRONG)
    assert (slowed.status_code, slowed.json()["code"]) == (429, "slowed")
    assert slowed.headers["retry-after"] == "1"
    assert ask(app, code=CODE).status_code == 429  # the right code too: it is not read
    assert ask(app, code=WRONG, address="198.51.100.1").status_code == 403  # another address
    clock.now += 1.0
    assert ask(app, code=WRONG).status_code == 403  # its second: the next waits 2 s
    clock.now += 1.0
    assert ask(app).headers["retry-after"] == "1"
    clock.now += 1.0
    assert ask(app).status_code == 200


def test_the_delay_doubles_to_a_minute_and_an_hour_forgets_it(app: FastAPI, clock: Clock) -> None:
    delays = []
    for _ in range(8):
        assert ask(app, code=WRONG).status_code == 403
        delays.append(int(ask(app, code=WRONG).headers["retry-after"]))
        clock.now += delays[-1]
    assert delays == [1, 2, 4, 8, 16, 32, 60, 60]
    clock.now += HOUR_S
    assert ask(app, code=WRONG).status_code == 403
    assert ask(app, code=WRONG).headers["retry-after"] == "1"


def test_the_hours_20th_wrong_code_closes_the_route_until_a_restart(
    app: FastAPI, minter: Minter, clock: Clock
) -> None:
    for each in range(WRONG_PER_HOUR - 1):
        assert ask(app, code=WRONG, address=f"192.0.2.{each}").status_code == 403
    assert ask(app, address="198.51.100.1").status_code == 200  # 19 in the hour: still open
    assert ask(app, code=WRONG, address="192.0.2.200").status_code == 403
    for address in ("192.0.2.201", "198.51.100.1"):
        closed = ask(app, address=address)
        assert (closed.status_code, closed.json()["code"]) == (503, "closed")
        assert "retry-after" not in closed.headers
    clock.now += DAY_S
    assert ask(app, address="198.51.100.2").status_code == 503
    assert len(minter.minted) == 1
    restarted = FastAPI()
    restarted.include_router(
        token_router(SecretStr(CODE), minter, customer_email=CUSTOMER, guard=Guard(clock=clock))
    )
    assert ask(restarted).status_code == 200


def test_wrong_codes_older_than_an_hour_do_not_count(app: FastAPI, clock: Clock) -> None:
    for each in range(WRONG_PER_HOUR - 1):
        assert ask(app, code=WRONG, address=f"192.0.2.{each}").status_code == 403
    clock.now += HOUR_S
    for each in range(WRONG_PER_HOUR - 1):
        assert ask(app, code=WRONG, address=f"192.0.2.{each}").status_code == 403
    assert ask(app, address="198.51.100.1").status_code == 200


def test_at_most_ten_tokens_a_day(app: FastAPI, minter: Minter, clock: Clock) -> None:
    for _ in range(TOKENS_PER_DAY):
        assert ask(app).status_code == 200
        clock.now += 60.0
    refused = ask(app)
    assert (refused.status_code, refused.json()["code"]) == (429, "daily_limit")
    assert refused.headers["retry-after"] == str(int(DAY_S - TOKENS_PER_DAY * 60.0))
    assert len(minter.minted) == TOKENS_PER_DAY
    clock.now = 1000.0 + DAY_S  # the first token's day has passed
    assert ask(app).status_code == 200
    assert TOKENS_PER_DAY == 10
