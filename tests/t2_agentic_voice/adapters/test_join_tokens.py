"""Signed join tokens (adapters/join_tokens.py): invariant 7's adversarial cases, each refused with
a `JoinRejected` that holds no value of the token, the replays across a prune and a restart, and
the consent a verified token carries."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt
import pytest
from jwt.warnings import InsecureKeyLengthWarning
from pydantic import SecretStr
from t2_agentic_voice.adapters.join_tokens import SignedJoinTokens
from t2_agentic_voice.adapters.used_tokens import MemoryUsedTokens, SqliteUsedTokens
from t2_agentic_voice.core.errors import ConfigurationError, JoinRejected
from t2_agentic_voice.core.identity import Caller, Consent, SignedConsent, allows_recording
from t2_agentic_voice.core.settings.join import JoinSettings
from t2_agentic_voice.domain.ports.identity import IdentityVerifier, JoinContext, UsedTokens

from tests.leaks import holding, shown

KEY = "made-up-join-key-of-at-least-32-bytes-0123"
OTHER_KEY = "another-made-up-join-key-of-32-bytes-or-more"
LONG_KEY = "a-made-up-join-key-of-at-least-64-bytes-for-hs512-0123456789abcdef"
NOW = datetime(2026, 11, 3, 10, 0, tzinfo=UTC)
T0 = int(NOW.timestamp())
SUBJECT = "made-up-subject-7f3"
JTI = "made-up-jti-a91c"
CLAIMS: dict[str, Any] = {
    "sub": SUBJECT,
    "name": "سارة الأحمد",
    "locale": "ar-SA",
    "attrs": {"dept": "made-up-dept"},
    "consent": {"version": "m2-owner-test-1", "record_audio": True},
    "jti": JTI,
    "iat": T0,
    "exp": T0 + 60,
}


class Clock:
    """A clock that moves only when a test sets it."""

    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _tokens(clock: Clock | None = None, **given: Any) -> SignedJoinTokens:
    keys = {"k1": SecretStr(KEY), "k2": SecretStr(LONG_KEY)}
    return SignedJoinTokens(keys=given.pop("keys", keys), _now=clock or Clock(), **given)


def _token(*, key: str = KEY, kid: object = "k1", alg: str = "HS256", **claims: Any) -> str:
    """A token of CLAIMS, each given claim replaced (None: left out), signed as given."""
    payload = {name: value for name, value in {**CLAIMS, **claims}.items() if value is not None}
    return jwt.encode(payload, key, algorithm=alg, headers={"kid": kid})


def _segment(data: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def _signed(header: dict[str, Any], claims: dict[str, Any] = CLAIMS) -> str:
    """A token of `header` and `claims` signed with KEY by hand, as no library would sign it."""
    signing_input = f"{_segment(header)}.{_segment(claims)}"
    mac = hmac.new(KEY.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{base64.urlsafe_b64encode(mac).rstrip(b'=').decode()}"


def _join(store: UsedTokens | None = None) -> JoinContext:
    """A join from another machine in prod, its store on the test's clock unless given."""
    store = store or MemoryUsedTokens(_now=Clock())
    return JoinContext(env="prod", client_host="203.0.113.7", used_tokens=store)


def _verify(
    tokens: SignedJoinTokens, token: str, join: JoinContext | None = None
) -> tuple[Caller, Consent]:
    return asyncio.run(tokens.verify(token, join=join or _join()))


def _refused(
    tokens: SignedJoinTokens, token: str, reason: str, join: JoinContext | None = None
) -> None:
    """`token` refused for `reason`, the refusal holding no value of it and chaining nothing."""
    with pytest.raises(JoinRejected) as refused:
        _verify(tokens, token, join)
    error = refused.value
    assert error.details == {"reason": reason}
    surfaces = shown(error)
    values = [SUBJECT, JTI, CLAIMS["name"], *([token] if len(token) > 8 else [])]
    assert [where for value in values for where in holding(value, surfaces)] == []
    assert error.__cause__ is None and error.__context__ is None


def test_a_minted_token_verifies_once_into_its_caller_and_a_signed_consent() -> None:
    tokens = _tokens(current_kid="k1")
    verifier: IdentityVerifier = tokens  # mypy checks the port's shape
    caller = Caller(
        subject=SUBJECT, display_name="سارة الأحمد", locale="ar-SA", attributes={"a": "b"}
    )
    for record_audio in (True, False):
        token = tokens.mint(caller, consent=Consent(version="v1", record_audio=record_audio))
        assert jwt.get_unverified_header(token) == {"alg": "HS256", "kid": "k1", "typ": "JWT"}
        got, consent = asyncio.run(verifier.verify(token, join=_join()))
        assert got == caller
        assert type(consent) is SignedConsent
        assert (consent.version, consent.record_audio) == ("v1", record_audio)
        assert allows_recording(consent) is record_audio
    bare = tokens.mint(Caller(subject="e-2"), consent=Consent(version=None, record_audio=False))
    claims = jwt.decode(bare, options={"verify_signature": False})
    assert set(claims) == {"sub", "consent", "jti", "iat", "exp"}
    assert _verify(tokens, bare)[0] == Caller(subject="e-2")


def test_a_token_lives_ttl_s_from_the_clock_and_each_has_its_own_jti() -> None:
    tokens = _tokens(current_kid="k1", ttl_s=90)
    minted = [tokens.mint(Caller(subject="e"), consent=Consent(version=None, record_audio=False))]
    minted.append(
        tokens.mint(Caller(subject="e"), consent=Consent(version=None, record_audio=False))
    )
    claims = [jwt.decode(t, options={"verify_signature": False}) for t in minted]
    assert [(c["iat"], c["exp"]) for c in claims] == [(T0, T0 + 90)] * 2
    assert claims[0]["jti"] != claims[1]["jti"]


def test_a_token_used_twice_is_refused() -> None:
    tokens, join = _tokens(), _join()
    _verify(tokens, _token(), join)
    _refused(tokens, _token(), "used", join)


def test_a_key_rotates_by_listing_both() -> None:
    old = _token(kid="k1")
    rotated = _tokens(current_kid="k2")
    assert _verify(rotated, old)[0].subject == SUBJECT
    new = rotated.mint(Caller(subject="e"), consent=Consent(version=None, record_audio=False))
    assert jwt.get_unverified_header(new)["kid"] == "k2"


@pytest.mark.parametrize(
    ("now", "reason"),
    [
        (NOW + timedelta(seconds=60 + 30), "expired"),  # exp plus the allowance
        (NOW + timedelta(seconds=60 + 31), "expired"),
        (NOW - timedelta(seconds=31), "not_yet_valid"),  # issued beyond the allowance ahead
    ],
)
def test_a_token_outside_its_times_is_refused(now: datetime, reason: str) -> None:
    _refused(_tokens(Clock(now)), _token(), reason)


@pytest.mark.parametrize("seconds", [-30, 0, 60 + 29])
def test_a_token_within_the_allowance_verifies(seconds: int) -> None:
    assert _verify(_tokens(Clock(NOW + timedelta(seconds=seconds))), _token())[0].subject == SUBJECT


@pytest.mark.parametrize(("ttl_s", "lifetime"), [(120, 121), (60, 61), (60, 0), (60, -5)], ids=str)
def test_a_lifetime_over_ttl_s_or_none_is_refused(ttl_s: int, lifetime: int) -> None:
    _refused(_tokens(ttl_s=ttl_s), _token(exp=T0 + lifetime), "lifetime")


def test_a_token_signed_otherwise_is_refused() -> None:
    tokens = _tokens()
    _refused(tokens, _token(key=OTHER_KEY), "signature")  # another key, a listed kid
    for alg in ("HS384", "HS512"):  # any algorithm but HS256, with a key long enough for it
        _refused(tokens, _token(key=LONG_KEY, kid="k2", alg=alg), "signature")
    unsigned = f"{_segment({'alg': 'none', 'kid': 'k1', 'typ': 'JWT'})}.{_segment(CLAIMS)}."
    _refused(tokens, unsigned, "signature")
    quiet = {**CLAIMS, "consent": {"version": "m2-owner-test-1", "record_audio": False}}
    header, _, signature = _token(consent=quiet["consent"]).split(".")
    for changed in ({**quiet, "consent": CLAIMS["consent"]}, {**quiet, "sub": "x"}):
        _refused(tokens, f"{header}.{_segment(changed)}.{signature}", "signature")


@pytest.mark.parametrize("kid", ["k9", None, ""], ids=["unknown", "none", "empty"])
def test_a_token_naming_no_listed_key_is_refused(kid: str | None) -> None:
    no_kid = jwt.encode(CLAIMS, KEY, algorithm="HS256")
    token = no_kid if kid is None else _token(kid=kid)
    _refused(_tokens(), token, "unknown_key")


MALFORMED: dict[str, dict[str, Any]] = {
    "no jti": {"jti": None},
    "no sub": {"sub": None},
    "no consent": {"consent": None},
    "no iat": {"iat": None},
    "no exp": {"exp": None},
    "record_audio 'true'": {"consent": {"version": None, "record_audio": "true"}},
    "record_audio 'false'": {"consent": {"version": None, "record_audio": "false"}},
    "record_audio 1": {"consent": {"version": None, "record_audio": 1}},
    "record_audio null": {"consent": {"version": None, "record_audio": None}},
    "no record_audio": {"consent": {"version": "v1"}},
    "a consent claim of more": {"consent": {"version": None, "record_audio": True, "x": 1}},
    "a version too long": {"consent": {"version": "v" * 65, "record_audio": True}},
    "a version with a space": {"consent": {"version": "v 1", "record_audio": True}},
    "iat a string": {"iat": str(T0)},
    "iat a float": {"iat": T0 + 0.5, "exp": T0 + 60.5},
    "iat a boolean": {"iat": True},
    "sub a number": {"sub": 7},
    "sub with a line break": {"sub": "a\nb"},
    "sub too long": {"sub": "s" * 257},
    "a locale that is no tag": {"locale": "arabic language"},
    "attrs of 17": {"attrs": {f"k{n}": "v" for n in range(17)}},
    "attrs not an object": {"attrs": ["a"]},
    "a jti with a space": {"jti": "a b"},
    "a jti too long": {"jti": "j" * 129},
    "nbf": {"nbf": T0},
    "aud": {"aud": "made-up-audience"},
    "iss": {"iss": "made-up-issuer"},
    "a claim of its own": {"role": "admin"},
}


@pytest.mark.parametrize("claims", MALFORMED.values(), ids=MALFORMED.keys())
def test_a_token_whose_claims_are_not_strictly_the_design_s_is_refused(
    claims: dict[str, Any],
) -> None:
    store = MemoryUsedTokens()
    _refused(_tokens(), _token(**claims), "malformed", _join(store))
    assert store._used == {}  # a refused join spends nothing


@pytest.mark.parametrize("token", ["", "x", "a.b", "a.b.c", "a.b.c.d", "!!.??.**"])
def test_a_token_that_is_no_jwt_is_refused(token: str) -> None:
    _refused(_tokens(), token, "malformed")


def test_a_kid_that_is_no_string_is_refused() -> None:
    _refused(_tokens(), _signed({"alg": "HS256", "kid": 5, "typ": "JWT"}), "malformed")
    assert _verify(_tokens(), _signed({"alg": "HS256", "kid": "k1"}))[0].subject == SUBJECT


def test_the_store_keeps_each_jti_until_exp_plus_the_bound_whatever_the_allowance() -> None:
    seen: list[tuple[str, datetime]] = []

    class Recording(MemoryUsedTokens):
        async def use(self, token_id: str, *, expires_at: datetime) -> bool:
            seen.append((token_id, expires_at))
            return await super().use(token_id, expires_at=expires_at)

    _verify(_tokens(max_clock_skew_s=0), _token(), _join(Recording(_now=Clock())))
    assert seen == [(JTI, datetime.fromtimestamp(T0 + 60 + 60, UTC))]


def test_a_token_the_store_finds_past_its_last_instant_is_refused_as_used() -> None:
    verifier_clock = Clock(NOW + timedelta(seconds=60 + 29))  # within the 30 s allowance
    store = MemoryUsedTokens(_now=Clock(NOW + timedelta(seconds=60 + 61)))
    _refused(_tokens(verifier_clock), _token(), "used", _join(store))


def test_a_token_replayed_after_the_store_pruned_at_its_exp_is_refused() -> None:
    clock, store_clock = Clock(), Clock()
    store = MemoryUsedTokens(_now=store_clock)
    tokens = _tokens(clock)
    _verify(tokens, _token(), _join(store))
    store_clock.now = NOW + timedelta(seconds=60)  # the token's exp: the store prunes
    asyncio.run(store.use("made-up-other", expires_at=store_clock.now + timedelta(minutes=5)))
    assert JTI in store._used  # kept until its exp plus 60 s
    clock.now = store_clock.now = NOW + timedelta(seconds=60 + 10)  # within exp plus 30 s
    _refused(tokens, _token(), "used", _join(store))


def test_a_token_replayed_after_a_restart_with_a_larger_allowance_is_refused(
    tmp_path: Path,
) -> None:
    path = tmp_path / "var" / "used_tokens.db"
    store_clock = Clock()

    async def first_use() -> None:
        store = await SqliteUsedTokens.open(path, _now=store_clock)
        try:
            await _tokens(max_clock_skew_s=30).verify(_token(), join=_join(store))
        finally:
            await store.aclose()

    asyncio.run(first_use())
    later = NOW + timedelta(seconds=60 + 45)  # the token's exp plus 45 s
    store_clock.now = later

    async def replay() -> None:
        store = await SqliteUsedTokens.open(path, _now=store_clock)
        try:
            # every row whose time had passed is pruned first
            assert await store.use("made-up-other", expires_at=later + timedelta(minutes=5))
            await _tokens(Clock(later), max_clock_skew_s=60).verify(_token(), join=_join(store))
        finally:
            await store.aclose()

    with pytest.raises(JoinRejected, match="used before"):
        asyncio.run(replay())


@pytest.mark.parametrize(
    "given",
    [
        {"ttl_s": 121},
        {"ttl_s": 0},
        {"max_clock_skew_s": 61},
        {"max_clock_skew_s": -1},
        {"keys": {}},
        {"keys": {"k1": SecretStr("short-made-up-key")}},
        {"keys": {"k1": SecretStr(KEY + " " + KEY)}},
        {"keys": {"no spaces in an ID": SecretStr(KEY)}},
        {"current_kid": "k9"},
    ],
    ids=str,
)
def test_tokens_built_outside_the_bounds_are_refused(given: dict[str, Any]) -> None:
    with pytest.raises(ConfigurationError, match="FIX: ") as refused:
        _tokens(**given)
    assert "made-up" not in str(refused.value)


def test_a_key_under_32_bytes_is_refused_at_verify_and_at_mint_too() -> None:
    tokens = _tokens(current_kid="k1")
    tokens._keys = {"k1": SecretStr("short-made-up-key")}  # past the constructor's check
    with pytest.warns(InsecureKeyLengthWarning):
        short = _token(key="short-made-up-key")
    _refused(tokens, short, "signature")
    with pytest.raises(jwt.InvalidKeyError):
        tokens.mint(Caller(subject="e"), consent=Consent(version=None, record_audio=False))


def test_an_instance_with_no_current_kid_only_verifies() -> None:
    with pytest.raises(ConfigurationError, match="only verifies"):
        _tokens().mint(Caller(subject="e"), consent=Consent(version=None, record_audio=False))


def test_the_settings_build_the_tokens_inline_or_from_a_file(tmp_path: Path) -> None:
    inline = JoinSettings(keys={"k1": SecretStr(KEY)}, current_kid="k1", ttl_s=30)
    tokens = SignedJoinTokens.from_settings(inline)
    claims = jwt.decode(
        tokens.mint(Caller(subject="e"), consent=Consent(version=None, record_audio=False)),
        options={"verify_signature": False},
    )
    assert claims["exp"] - claims["iat"] == 30
    keys_file = tmp_path / "join_keys.json"
    keys_file.write_text(json.dumps({"k1": KEY}), encoding="utf-8")
    from_file = SignedJoinTokens.from_settings(JoinSettings(keys_file=keys_file))
    issued = int(time.time())  # the settings' tokens run on the system's clock
    token = _token(iat=issued, exp=issued + 60)
    assert _verify(from_file, token, _join(MemoryUsedTokens()))[0].subject == SUBJECT


def test_settings_with_no_key_are_refused_naming_the_setting() -> None:
    with pytest.raises(ConfigurationError, match="HELPDESK_VOICE_JOIN__KEYS holds no join key"):
        SignedJoinTokens.from_settings(JoinSettings(), prefix="HELPDESK_VOICE_")
    with pytest.raises(ConfigurationError, match="T2V_JOIN__KEYS_FILE"):
        SignedJoinTokens.from_settings(JoinSettings())
