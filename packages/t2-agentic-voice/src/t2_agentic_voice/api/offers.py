"""The router's record of each call it joined (api/runtime.py, "The record of each call"; D-029):
the call's ID and its offer secret, and, until its offer, who joined and in which language.

`/join` mints each call's ID and its offer secret here, random and for that call only; `POST`
and `PATCH /offer` find the call's record with the secret the client sent, compared in constant
time, so a request with no secret, a wrong one or another call's gets the same 403, whether the
call exists or not. The records stay bounded: a sweep, on the runtime's clock, drops a join
never offered once its join token's window has passed (`join.ttl_s` plus twice
`join.max_clock_skew_s`, the longest a token valid at the join still verifies), and an offered
call `FORGOTTEN_KEPT_S` after the first sweep that finds voice holds it no longer (`phase`
None): an answered call voice forgot, or an offer voice refused. The offer secret is never
logged, traced or put in an event.
"""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final, Literal

from pydantic import SecretStr

from t2_agentic_voice.core.events import CallId
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.domain.declaration import Language
from t2_agentic_voice.voice.calls import CallPhase

# How long an offered call's record is kept once voice no longer holds the call, so a late
# PATCH still gets the quiet 409 `call_ended`; then a request for it gets 403 `forbidden`.
FORGOTTEN_KEPT_S: Final = 60.0
# A call's ID and its offer secret, in random bytes (URL-safe base64: 16 and 43 characters).
_ID_BYTES = 12
_SECRET_BYTES = 32
# What a secret is compared with when no record matches the call's ID, so the answer takes the
# same time whether the call exists or not.
_NO_SECRET = secrets.token_urlsafe(_SECRET_BYTES).encode("ascii")

# Where a call's offer stands: none yet; being answered by voice; answered; refused by voice
# (an offer it cannot read, or one that failed).
OfferState = Literal["none", "offering", "answered", "refused"]


@dataclass(frozen=True)
class Joined:
    """Who joined a call, and the language it is held in, as `/join` fixed them."""

    caller: Caller
    consent: Consent
    language: Language


@dataclass(kw_only=True)
class CallRecord:
    """One joined call: its ID and offer secret, when it joined, who joined and in which
    language (kept until its offer is taken, then dropped), where its offer stands, and when a
    sweep first found that voice holds it no longer."""

    call_id: CallId
    secret: SecretStr
    joined_at: float
    joined: Joined | None
    offer: OfferState = "none"
    gone_at: float | None = None

    def offering(self) -> Joined | None:
        """Take the call's one offer: who joined, now voice's to keep; None when an offer was
        taken already."""
        joined, self.joined = self.joined, None
        if self.offer != "none" or joined is None:
            return None
        self.offer = "offering"
        return joined


@dataclass
class CallRecords:
    """Every call the router joined and still keeps, by its ID; `window_s` is a join token's
    window, after which a join never offered is dropped."""

    window_s: float
    _records: dict[CallId, CallRecord] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self._records)

    def join(
        self, *, caller: Caller, consent: Consent, language: Language, now: float
    ) -> CallRecord:
        """A new call's record, with a fresh ID (96 random bits) and offer secret, joined at
        `now`."""
        record = CallRecord(
            call_id=secrets.token_urlsafe(_ID_BYTES),
            secret=SecretStr(secrets.token_urlsafe(_SECRET_BYTES)),
            joined_at=now,
            joined=Joined(caller, consent, language),
        )
        self._records[record.call_id] = record
        return record

    def find(self, call_id: CallId, secret: str | None) -> CallRecord | None:
        """The record of `call_id` when `secret` is its offer secret; None when the secret is
        missing or wrong, or no record has the ID, each compared in the same constant time."""
        record = self._records.get(call_id)
        given = (secret or "").encode("utf-8")
        held = _NO_SECRET if record is None else record.secret.get_secret_value().encode("ascii")
        matches = hmac.compare_digest(given, held)
        return record if record is not None and secret and matches else None

    def live(self, phase: Callable[[CallId], CallPhase | None]) -> int:
        """How many answered calls voice holds connecting or connected."""
        answered = (r for r in self._records.values() if r.offer == "answered")
        return sum(1 for r in answered if phase(r.call_id) in ("connecting", "connected"))

    def sweep(self, phase: Callable[[CallId], CallPhase | None], *, now: float) -> int:
        """Drop each record past its time at `now`; how many it dropped. A join never offered
        goes once `window_s` has passed since it joined; an offered call (answered or refused)
        once `FORGOTTEN_KEPT_S` has passed since the first sweep that found voice holds it no
        longer. A call being offered is left alone."""
        dropped = [
            call_id for call_id, record in self._records.items() if _past(record, phase, now, self)
        ]
        for call_id in dropped:
            del self._records[call_id]
        return len(dropped)


def _past(
    record: CallRecord,
    phase: Callable[[CallId], CallPhase | None],
    now: float,
    records: CallRecords,
) -> bool:
    """Whether `record` is past its time at `now`, noting when voice was first found to hold
    its call no longer."""
    if record.offer == "none":
        return now - record.joined_at > records.window_s
    if record.offer == "offering" or phase(record.call_id) is not None:
        record.gone_at = None
        return False
    if record.gone_at is None:
        record.gone_at = now
    return now - record.gone_at >= FORGOTTEN_KEPT_S
