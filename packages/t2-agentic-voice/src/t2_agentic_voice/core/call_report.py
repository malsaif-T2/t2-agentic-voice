"""What one call did, as `CallEnded` carries it to the team's observers (the design's 6.6): the
`CallReport` and the parts it is made of, each turn's `TurnRecord` and `TurnTimes`, each model's
`ModelUsage` and the browser's `ClientConnection`. core/events.py re-exports each, beside the
events, and so does the `events` facade. Provisional.

A report holds what was heard and said, so it is never logged (call content is logged at no
level, docs/SECURITY.md, invariant 8); its numbers are written apart, with no text.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from t2_agentic_voice.core.ids import MAX_MS, CallId, TurnId
from t2_agentic_voice.core.settings.tts import LanguageTag

_Ms = Annotated[float, Field(ge=0, le=MAX_MS, allow_inf_nan=False)]

# Why a call ended: the caller hung up; the caller's side closed the connection; the call
# reached `limits.max_call_s`, or `limits.idle_s` with nothing heard; the connection failed;
# the server stopped or failed.
EndReason = Literal["hangup", "caller_left", "max_call", "idle", "transport", "server"]
# How the language a turn was sent to speech-to-text in was chosen: the session's (`session`:
# no classifier runs), a classifier's verdict (`classified`), or the current language kept: the
# speech too short to classify, the verdict late, the classifier busy or failed, its best share
# under the rule's, or an overlap's part (domain/turn_language.py); or Whisper's own detection,
# which moved the call to the agent's other language (`detected`, domain/language_switch.py).
LanguageBy = Literal[
    "session", "classified", "short", "unsure", "late", "busy", "failed", "overlap", "detected"
]
# The kind of the ICE candidate the browser's call selected (host, server reflexive, peer
# reflexive, relayed), and how a relayed one reaches its TURN server.
CandidateType = Literal["host", "srflx", "prflx", "relay"]
RelayProtocol = Literal["udp", "tcp", "tls"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ClientConnection(_Frozen):
    """The browser's view of its connection, from its `client_stats` message: the selected
    candidate's type and, for a relay, how it reaches the TURN server and on which port; how
    long it took to connect; whether the microphone's echo cancellation applied; and how long
    after connecting the first audio played. A value the browser did not report is None."""

    candidate_type: CandidateType | None = None
    relay_protocol: RelayProtocol | None = None
    turn_port: int | None = Field(default=None, ge=1, le=65535)
    connect_ms: _Ms | None = None
    echo_cancellation: bool | None = None
    first_audio_ms: _Ms | None = None

    @model_validator(mode="after")
    def _relay_only(self) -> ClientConnection:
        if self.candidate_type != "relay" and (self.relay_protocol or self.turn_port):
            raise ValueError("relay_protocol and turn_port belong to a relay candidate only")
        return self


class TurnTimes(_Frozen):
    """How long a turn's steps took, in milliseconds, each None when it did not happen. From the
    end of the caller's speech (the speech detector's stop less its stop delay): to the first
    audible frame of the reply sent (`ttfa_ms`; a silent first chunk is not audible, TD-090; a
    call whose output taps no audio, a test's or `TextCall`'s, times its first audio queued), a
    progress line counted apart (`progress_ms`, the first audible frame of one); to the
    browser's playback of the reply (`played_ms`, from its `playback` report, when it sends
    one); to the chat model's first token (`llm_first_token_ms`, the talker's); to the turn's
    end, as the turn analyzer closed it (`end_of_turn_ms`: the detector's stop delay, Smart
    Turn's judgement and the hold after it); and to Smart Turn's "complete", where the hold
    began (`turn_complete_ms`, in a call with a talker, for a turn said while the agent was
    silent). From the detector's stop as it came, to the transcript (`stt_ms`: the turn's own
    request's, or its held request's when it took that one as its own, in a call with a
    talker); and from a text-to-speech request to its first audio (`tts_first_audio_ms`)."""

    ttfa_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    stt_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    llm_first_token_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    tts_first_audio_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    progress_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    played_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    end_of_turn_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    turn_complete_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class ModelUsage(_Frozen):
    """One provider model's use in one call: its requests, each counted once it went, answered
    or not (one the call's end cancelled included); for speech-to-text, the audio seconds sent
    and billed (at least 10 s a request, as Groq bills Whisper); for text-to-speech, the
    characters sent and the cache's hits, the phrases and the clauses played from the caches,
    which sent nothing; for the chat model, the tokens read (the cached ones counted again in
    `cached_tokens`) and written, as each request's provider reported them; and the last
    headroom the provider reported for its key."""

    model: str = Field(min_length=1)
    requests: int = Field(default=0, ge=0)
    audio_sent_s: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    billed_s: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    characters: int = Field(default=0, ge=0)
    cache_hits: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    remaining_requests: int | None = Field(default=None, ge=0)
    remaining_tokens: int | None = Field(default=None, ge=0)


class TurnRecord(_Frozen):
    """One turn of a call: what was heard, and the agent's tag of the language its request was
    sent in to speech-to-text (`language`: the call's, unless a classifier moved it) and how that
    was chosen (`language_by`); the tag the talker's reply to it was in as it began
    (`reply_language`: agent/language.py's `reply_language`, which the words' script can move
    from the heard one; None for a turn the talker did not answer) and each tag its clauses were
    said in, each once, in order (`spoken_languages`: an Arabic clause of an English reply is
    said in the Arabic voice under `tts.voice_by_script`, and the `switch_language` tool moves
    the rest of a reply), so a reply's language that is not the heard one shows in its own turn;
    what the agent said back; whether the turn was dropped (its speech began while the agent
    spoke, the greeting included, or just after), its reply stopped by the caller, or the turn
    left unfinished (the call ended before its transcript came, so nothing was heard); whether
    its first chat request went out on a kept-alive connection (`warm_connection`, None when no
    request went or the chat model does not say); and its times. Provisional."""

    turn_id: TurnId
    language: LanguageTag | None = None
    language_by: LanguageBy = "session"
    reply_language: LanguageTag | None = None
    spoken_languages: tuple[LanguageTag, ...] = ()
    heard: str
    said: str = ""
    dropped: bool = False
    stopped: bool = False
    unfinished: bool = False
    warm_connection: bool | None = None
    times: TurnTimes = Field(default_factory=TurnTimes)


class CallReport(_Frozen):
    """What one call did, given to `CallEnded`'s observers: who answered it (the agent's name),
    when it started and ended and why, the consent version the caller agreed to, each turn
    (what was heard and said, and its times), each model's usage (every request the call sent,
    one its end cancelled included, so a cap set from `requests_per_minute` counts what the key
    was asked), and the browser's view of the connection. Its tool calls and actions are not
    here: their own events report them as they happen (core/events.py)."""

    call_id: CallId
    agent: str = Field(min_length=1)
    started_at: AwareDatetime
    ended_at: AwareDatetime
    ended_by: EndReason
    consent_version: str | None = None
    turns: tuple[TurnRecord, ...] = ()
    usage: tuple[ModelUsage, ...] = ()
    client: ClientConnection | None = None

    @model_validator(mode="after")
    def _consistent(self) -> CallReport:
        if self.ended_at < self.started_at:
            raise ValueError("a call ends after it starts")
        models = [each.model for each in self.usage]
        if len(set(models)) != len(models):
            raise ValueError("each model's usage is counted in one entry")
        return self

    @property
    def duration_s(self) -> float:
        """How long the call lasted."""
        return (self.ended_at - self.started_at).total_seconds()

    def requests_per_minute(self) -> dict[str, float]:
        """Each model's requests per call minute, the measure a cap on live calls is set from;
        0 for a call that lasted no time."""
        minutes = self.duration_s / 60
        return {u.model: u.requests / minutes if minutes else 0.0 for u in self.usage}
