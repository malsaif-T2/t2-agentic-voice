"""The test console's Start for Ole5 (ole5_voice/settings.py, customer.py; the library's
api/dev_console.py, D-083): under `env` dev alone, Ole5's settings declare its demo customer as
the console's dev caller, so a call the console starts is the demo customer's, as a widget's call
is, its tickets theirs; under another `env`, or without the dev page, the console mints nothing;
and the token route's daily count of 10 counts the widget's tokens alone. The app is
`make_app`'s, its runtime the library's on fake providers and fake calls."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from ole5_voice import server
from ole5_voice.customer import CUSTOMER_EMAIL, CUSTOMER_FIELD, SUBJECT, customer_email
from ole5_voice.settings import DEMO_CUSTOMER_EMAIL, load
from ole5_voice.token_route import TOKENS_PER_DAY
from t2_agentic_voice import (
    Caller,
    ConfigurationError,
    Providers,
    VoiceRuntime,
    VoiceSettings,
    from_caller,
)
from t2_agentic_voice.voice.calls import Calls

from tests.t2_agentic_voice.api.runtime_support import OFFER_SDP, patch_stores
from tests.t2_agentic_voice.fakes import FakeCalls, FakeSpeechToText, FakeTextToSpeech

CODE = "made-up-access-code-0123"
KEY = "a-made-up-join-key-of-forty-bytes-0123456"
VERSION = "m2-owner-test-1"  # the widget's consent version
LOOPBACK = ("127.0.0.1", 50000)
LOCAL = "http://127.0.0.1:7861"
DEMO_CALLER = Caller(subject=SUBJECT, attributes={CUSTOMER_EMAIL: DEMO_CUSTOMER_EMAIL})


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> pytest.MonkeyPatch:
    """Ole5's settings under `env` dev with the dev page, under the test's own folder."""
    patch_stores(monkeypatch)
    for name, value in {
        "T2V_ENV": "dev",
        "T2V_SERVER__DEV_PAGE": "true",
        "T2V_JOIN__KEYS": f'{{"k1": "{KEY}"}}',
        "T2V_JOIN__CURRENT_KID": "k1",
        "T2V_PRIVACY__CONSENT_VERSION": VERSION,
        "T2V_STORAGE__VAR_DIR": str(tmp_path / "var"),
        "OLE5_VOICE_ACCESS_CODE": CODE,
        "OLE5_VOICE_TICKETS_DIR": str(tmp_path / "tickets"),
    }.items():
        monkeypatch.setenv(name, value)
    return monkeypatch


def _runtime(calls: FakeCalls) -> Callable[..., VoiceRuntime]:
    """`VoiceRuntime` as `make_app` builds it, on fake providers, its calls `calls`."""

    def built(agent: Any, *, settings: VoiceSettings, identity: Any) -> VoiceRuntime:
        def made(**given: Any) -> Calls:
            return calls

        providers = Providers(stt=FakeSpeechToText(), tts=FakeTextToSpeech())
        return VoiceRuntime(
            agent, settings=settings, identity=identity, providers=providers, _calls=made
        )

    return built


def test_under_dev_the_consoles_start_calls_as_the_demo_customer(
    environment: pytest.MonkeyPatch,
) -> None:
    calls = FakeCalls()
    environment.setattr(server, "VoiceRuntime", _runtime(calls))
    loaded = load()
    assert loaded.voice.server.dev_caller == DEMO_CALLER
    with TestClient(server.make_app(loaded), client=LOOPBACK, base_url=LOCAL) as test:
        minted = test.post("/voice/dev/token", json={"record_audio": False})
        assert minted.status_code == 200, minted.text
        joined = test.post("/voice/join", json={"token": minted.json()["token"], "protocol": 1})
        assert joined.status_code == 200, joined.text
        call = joined.json()
        offer = {"call_id": call["call_id"], "sdp": OFFER_SDP, "type": "offer"}
        offered = test.post("/voice/offer", json={**offer, "offer_secret": call["offer_secret"]})
        assert offered.status_code == 200, offered.text
    [(_, caller, consent, _)] = calls.offers.values()
    assert caller == DEMO_CALLER  # as the widget's token names it
    assert customer_email(caller) == DEMO_CUSTOMER_EMAIL
    assert from_caller(CUSTOMER_FIELD).value(caller) == DEMO_CUSTOMER_EMAIL  # a ticket tool's
    assert (consent.version, consent.record_audio) == (VERSION, False)


def test_console_tokens_leave_the_token_routes_daily_count_alone(
    environment: pytest.MonkeyPatch,
) -> None:
    environment.setattr(server, "VoiceRuntime", _runtime(FakeCalls()))
    with TestClient(server.make_app(load()), client=LOOPBACK, base_url=LOCAL) as test:
        for _ in range(TOKENS_PER_DAY + 2):  # no access code, no count
            assert test.post("/voice/dev/token", json={"record_audio": False}).status_code == 200
        consent = {"version": VERSION, "record_audio": False}
        widget = test.post("/token", json={"code": CODE, "consent": consent})
    assert widget.status_code == 200, widget.text


@pytest.mark.parametrize(("env", "dev_page"), [("dev", "false"), ("staging", ""), ("prod", "")])
def test_without_dev_and_its_page_the_console_mints_nothing(
    env: str, dev_page: str, environment: pytest.MonkeyPatch
) -> None:
    environment.setenv("T2V_ENV", env)
    environment.setenv("T2V_SERVER__DEV_PAGE", dev_page)
    environment.setattr(server, "VoiceRuntime", _runtime(FakeCalls()))
    loaded = load()
    assert (loaded.voice.server.dev_caller is not None) == (env == "dev")
    test = TestClient(server.make_app(loaded), client=LOOPBACK, base_url=LOCAL)
    answer = test.post("/voice/dev/token", json={"record_audio": False})
    assert (answer.status_code, answer.json()) == (404, {"detail": "Not Found"})


def test_under_env_test_no_dev_caller_is_declared_and_no_server_is_built(
    environment: pytest.MonkeyPatch,
) -> None:
    environment.setenv("T2V_ENV", "test")
    environment.setenv("T2V_SERVER__DEV_PAGE", "")
    environment.setattr(server, "VoiceRuntime", _runtime(FakeCalls()))
    loaded = load()
    assert loaded.voice.server.dev_caller is None
    with pytest.raises(ConfigurationError):
        server.make_app(loaded)


def test_the_dev_caller_is_the_only_setting_ole5_adds(environment: pytest.MonkeyPatch) -> None:
    loaded = load()
    plain = VoiceSettings.from_env()
    assert loaded.voice.model_dump(exclude={"server": {"dev_caller"}}) == plain.model_dump(
        exclude={"server": {"dev_caller"}}
    )
    assert plain.server.dev_caller is None and loaded.voice.prefix == plain.prefix
