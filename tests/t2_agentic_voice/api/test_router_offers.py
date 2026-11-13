"""A call's set-up through the router (api/router.py; the design's 5.5; D-029; invariant 7): the
join, its token verified once and its consent version checked, the call's language fixed; the offer
and its candidates behind the call's own offer secret, in a header or the body and never in a URL;
one offer per call; the quiet 409s once ICE completed, the call ended or before the offer was
answered; and a 403 for any other secret, the same whether the call exists or not."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from pathlib import Path

import pytest
from t2_agentic_voice.api.protocol import OFFER_SECRET_HEADER
from t2_agentic_voice.core.errors import NotFoundError
from t2_agentic_voice.core.events import CallId
from t2_agentic_voice.core.identity import CONSENT_SEAL, Caller, SignedConsent
from t2_agentic_voice.core.settings.privacy import PrivacySettings
from t2_agentic_voice.core.settings.server import ServerSettings
from t2_agentic_voice.voice.calls import Candidate

from tests.t2_agentic_voice.api.runtime_support import (
    END,
    LINE,
    OFFER_SDP,
    PREFIX,
    TOKEN,
    FakeIdentity,
    Harness,
    candidates,
    dev_settings,
    joined,
    offered,
    post,
    refused,
    serving,
)
from tests.t2_agentic_voice.fakes import FakeCalls

pytestmark = pytest.mark.usefixtures("patched_stores")


def test_a_call_joins_offers_and_trickles_its_candidates(tmp_path: Path) -> None:
    harness = Harness(dev_settings(tmp_path))

    async def scene() -> None:
        async with serving(harness.app()) as http:
            call_id, secret = await joined(http)
            answer = await offered(http, call_id, secret)
            assert answer.json() == {"sdp": f"answer to {call_id}", "type": "answer"}
            trickled = await candidates(http, call_id, secret, LINE, END)
            assert (trickled.status_code, trickled.content) == (204, b"")
        assert harness.identity.asked[0][0] == TOKEN
        assert harness.calls.offers[call_id][0] == OFFER_SDP
        line = Candidate(**LINE)  # type: ignore[arg-type]
        assert harness.calls.candidates[call_id] == [line, Candidate(**END)]  # type: ignore[arg-type]

    asyncio.run(scene())


def test_a_join_answers_the_ice_servers_as_set_with_no_credential(tmp_path: Path) -> None:
    servers = ServerSettings(ice_servers=("stun:stun.example.test:3478", "turn:turn.example.test"))
    harness = Harness(dev_settings(tmp_path, server=servers))

    async def scene() -> None:
        async with serving(harness.app()) as http:
            answer = await post(http, "/join", {"token": TOKEN, "protocol": 1})
        body = answer.json()
        assert body["ice_servers"] == [
            {"urls": ["stun:stun.example.test:3478"], "username": None, "credential": None},
            {"urls": ["turn:turn.example.test"], "username": None, "credential": None},
        ]
        assert body["protocol"] == 1 and len(body["offer_secret"]) >= 32

    asyncio.run(scene())


@pytest.mark.parametrize(
    ("picked", "locale", "language"),
    [(None, None, "en"), ("ar-SA", None, "ar-SA"), (None, "AR-sa", "ar-SA"), ("ar", "ar", "ar-SA")],
)
def test_the_call_language_is_fixed_at_join(
    picked: str | None, locale: str | None, language: str, tmp_path: Path
) -> None:
    identity = FakeIdentity(caller=Caller(subject="caller-1", locale=locale))
    harness = Harness(dev_settings(tmp_path), identity=identity)

    async def scene() -> None:
        async with serving(harness.app()) as http:
            call_id, secret = await joined(http, **({} if picked is None else {"language": picked}))
            await offered(http, call_id, secret)
        assert harness.calls.offers[call_id][3].tag == language

    asyncio.run(scene())


def test_a_refused_token_is_answered_403_echoing_none_of_it(tmp_path: Path) -> None:
    harness = Harness(dev_settings(tmp_path), identity=FakeIdentity(refuse=True))

    async def scene() -> None:
        async with serving(harness.app()) as http:
            answer = await post(http, "/join", {"token": TOKEN, "protocol": 1})
        assert answer.status_code == 403
        body = refused(answer, "POST /join", "join_rejected")
        assert TOKEN not in answer.text and "fake" not in body["message"]

    asyncio.run(scene())


def _signed(version: str) -> SignedConsent:
    return SignedConsent.model_validate(
        {"version": version, "record_audio": True}, context=CONSENT_SEAL
    )


@pytest.mark.parametrize(("version", "joins"), [("m2-owner-test-1", True), ("other-1", False)])
def test_a_signed_consent_of_another_version_is_refused(
    version: str, joins: bool, tmp_path: Path
) -> None:
    privacy = PrivacySettings(consent_version="m2-owner-test-1")
    identity = FakeIdentity(consent=_signed(version))
    harness = Harness(dev_settings(tmp_path, privacy=privacy), identity=identity)

    async def scene() -> None:
        async with serving(harness.app()) as http:
            answer = await post(http, "/join", {"token": TOKEN, "protocol": 1})
        if joins:
            assert answer.status_code == 200
        else:
            assert answer.status_code == 403
            refused(answer, "POST /join", "join_rejected")

    asyncio.run(scene())


def test_a_plain_consent_is_not_compared_with_the_version(tmp_path: Path) -> None:
    """As `DevIdentity` gives it, in `dev`: it never lets audio be kept (D-029)."""
    privacy = PrivacySettings(consent_version="m2-owner-test-1")
    harness = Harness(dev_settings(tmp_path, privacy=privacy))

    async def scene() -> None:
        async with serving(harness.app()) as http:
            assert (await post(http, "/join", {"token": TOKEN, "protocol": 1})).status_code == 200

    asyncio.run(scene())


@pytest.mark.parametrize("where", ["none", "another call's", "the query string", "both, differing"])
def test_an_offer_without_the_calls_own_secret_is_forbidden(where: str, tmp_path: Path) -> None:
    harness = Harness(dev_settings(tmp_path))

    async def scene() -> None:
        async with serving(harness.app()) as http:
            call_id, secret = await joined(http)
            _, other = await joined(http)
            body: dict[str, object] = {"call_id": call_id, "sdp": OFFER_SDP, "type": "offer"}
            path, headers = "/offer", {}
            if where == "another call's":
                body["offer_secret"] = other
            elif where == "the query string":
                path = f"/offer?offer_secret={secret}"
            elif where == "both, differing":
                body["offer_secret"], headers = secret, {OFFER_SECRET_HEADER: other}
            answer = await post(http, path, body, **headers)
            assert answer.status_code == 403
            refused(answer, "POST /offer", "forbidden")
            patched = await candidates(http, call_id, other)
            assert patched.status_code == 403
            refused(patched, "PATCH /offer", "forbidden")
            unknown = await candidates(http, "no-such-call", secret)
            assert unknown.status_code == 403
            assert harness.calls.offers == {}

    asyncio.run(scene())


def test_the_secret_in_its_header_and_the_body_agreeing_is_taken(tmp_path: Path) -> None:
    harness = Harness(dev_settings(tmp_path))

    async def scene() -> None:
        async with serving(harness.app()) as http:
            call_id, secret = await joined(http)
            body = {"call_id": call_id, "sdp": OFFER_SDP, "type": "offer", "offer_secret": secret}
            answer = await post(http, "/offer", body, **{OFFER_SECRET_HEADER: secret})
            assert answer.status_code == 200

    asyncio.run(scene())


def _quiet(caplog: pytest.LogCaptureFixture, code: str) -> None:
    """The refusal `code` was logged at DEBUG, and nothing at a higher level named it."""
    found = [r for r in caplog.records if getattr(r, "fields", {}).get("code") == code]
    assert found and all(r.levelno == logging.DEBUG for r in found)


def test_a_patch_before_the_offer_is_a_quiet_409(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")
    harness = Harness(dev_settings(tmp_path))

    async def scene() -> None:
        async with serving(harness.app()) as http:
            call_id, secret = await joined(http)
            answer = await candidates(http, call_id, secret)
        assert answer.status_code == 409
        refused(answer, "PATCH /offer", "not_offered")
        _quiet(caplog, "not_offered")

    asyncio.run(scene())


def test_an_offer_voice_refuses_takes_no_second_and_no_candidates(tmp_path: Path) -> None:
    harness = Harness(dev_settings(tmp_path), calls=FakeCalls(refused=(OFFER_SDP,)))

    async def scene() -> None:
        async with serving(harness.app()) as http:
            call_id, secret = await joined(http)
            answer = await offered(http, call_id, secret)
            assert answer.status_code == 400
            refused(answer, "POST /offer", "invalid_request")
            refused(await candidates(http, call_id, secret), "PATCH /offer", "not_offered")
            again = await offered(http, call_id, secret)
            assert again.status_code == 409
            refused(again, "POST /offer", "already_offered")

    asyncio.run(scene())


class _Crashing(FakeCalls):
    """voice's entry point failing an offer with no refusal of its own."""

    async def answer(self, call_id: CallId, offer: str, **_: object) -> str:
        self.phases[call_id] = "connecting"
        raise RuntimeError("the pipeline failed to start")


class _Unending(_Crashing):
    """voice's entry point failing the offer, and then its end too."""

    async def end(self, call_id: CallId) -> None:
        raise RuntimeError("the end failed")

    async def aclose(self) -> None:
        self.closed += 1


@pytest.mark.parametrize("calls", [_Crashing(), _Unending()])
def test_an_offer_that_fails_is_a_500_and_the_call_is_ended(
    calls: FakeCalls, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    harness = Harness(dev_settings(tmp_path), calls=calls)

    async def scene() -> None:
        async with serving(harness.app()) as http:
            call_id, secret = await joined(http)
            answer = await offered(http, call_id, secret)
        assert answer.status_code == 500
        refused(answer, "POST /offer", "internal_error")
        if isinstance(calls, _Unending):
            assert "call_end_failed" in [r.getMessage() for r in caplog.records]
        else:
            assert harness.calls.ended == [call_id]

    asyncio.run(scene())


@pytest.mark.parametrize(
    ("step", "patch_code"),
    [("connect", "ice_completed"), ("end", "call_ended"), ("forget", "call_ended")],
)
def test_the_calls_own_secret_gets_a_409_after_ice_completed_or_the_call_ended(
    step: str, patch_code: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="t2_agentic_voice")
    harness = Harness(dev_settings(tmp_path))

    async def scene() -> None:
        async with serving(harness.app()) as http:
            call_id, secret = await joined(http)
            await offered(http, call_id, secret)
            if step == "connect":
                harness.calls.connect(call_id)
            else:
                await harness.calls.end(call_id)
            if step == "forget":
                harness.calls.forget(call_id)
            patched = await candidates(http, call_id, secret)
            again = await offered(http, call_id, secret)
        assert (patched.status_code, again.status_code) == (409, 409)
        refused(patched, "PATCH /offer", patch_code)
        refused(again, "POST /offer", "already_offered")
        _quiet(caplog, patch_code)

    asyncio.run(scene())


class _Vanishing(FakeCalls):
    """voice's entry point whose call ends between the router's look and its candidates."""

    async def add_candidates(self, call_id: CallId, candidates: Sequence[Candidate]) -> None:
        raise NotFoundError("No such call.")


@pytest.mark.parametrize(
    ("calls", "line", "status", "code"),
    [
        (_Vanishing(), END, 409, "call_ended"),
        (FakeCalls(), {**LINE, "candidate": "not a candidate"}, 400, "invalid_request"),
    ],
)
def test_candidates_voice_refuses_are_answered_in_the_one_shape(
    calls: FakeCalls, line: dict[str, object], status: int, code: str, tmp_path: Path
) -> None:
    harness = Harness(dev_settings(tmp_path), calls=calls)

    async def scene() -> None:
        async with serving(harness.app()) as http:
            call_id, secret = await joined(http)
            await offered(http, call_id, secret)
            answer = await candidates(http, call_id, secret, line)
        assert answer.status_code == status
        refused(answer, "PATCH /offer", code)

    asyncio.run(scene())


def test_the_records_are_dropped_once_their_time_has_passed(tmp_path: Path) -> None:
    """A join never offered after its token's window; an ended call, and a forgotten one, after
    `FORGOTTEN_KEPT_S` and a sweep's period; then each gets 403 `forbidden`."""
    from t2_agentic_voice.api.offers import FORGOTTEN_KEPT_S
    from t2_agentic_voice.api.runtime import SWEEP_PERIOD_S

    settings = dev_settings(tmp_path)
    harness = Harness(settings)
    window = settings.join.ttl_s + 2 * settings.join.max_clock_skew_s

    async def scene() -> None:
        async with serving(harness.app()) as http:
            await harness.clock.advance(0)  # the sweep's task sleeps on the clock from now on
            never = await joined(http)
            ended = await joined(http)
            await offered(http, *ended)
            live = await joined(http)
            await offered(http, *live)
            await harness.calls.end(ended[0])
            records = harness.runtime._records
            await harness.clock.advance(window + SWEEP_PERIOD_S)
            assert len(records) == 2  # the join never offered is gone
            harness.calls.forget(ended[0])
            await harness.clock.advance(FORGOTTEN_KEPT_S)
            refused(await candidates(http, *ended), "PATCH /offer", "call_ended")
            await harness.clock.advance(SWEEP_PERIOD_S)
            assert len(records) == 1  # the live call is kept
            for call_id, secret in (never, ended):
                refused(await candidates(http, call_id, secret), "PATCH /offer", "forbidden")
                refused(await offered(http, call_id, secret), "POST /offer", "forbidden")
            assert (await candidates(http, *live)).status_code == 204

    asyncio.run(scene())


def test_health_counts_the_live_calls(tmp_path: Path) -> None:
    harness = Harness(dev_settings(tmp_path))

    async def scene() -> None:
        async with serving(harness.app()) as http:
            first, second = await joined(http), await joined(http)
            await offered(http, *first)
            await offered(http, *second)
            harness.calls.connect(first[0])
            await harness.calls.end(second[0])
            await joined(http)  # never offered
            health = (await http.get(PREFIX + "/health")).json()
        assert health == {"env": "dev", "calls": 1}

    asyncio.run(scene())
