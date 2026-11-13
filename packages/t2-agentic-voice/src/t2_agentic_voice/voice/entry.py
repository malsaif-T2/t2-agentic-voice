"""voice's entry point as api meets it: the `Calls` protocol (voice/calls.py's `VoiceCalls`, or
a test's fake), how the runtime builds it (`CallsFactory`), where a call stands (`CallPhase`) and
one trickled ICE candidate (`Candidate`). Apart from calls.py, which builds each call, so each
stays within the size a module may have (ARCH-SIZE); calls.py gives these names too, where api
and the tests import them.

api does the HTTP side: the offer secret, a second offer's 409, the quiet 409 for a PATCH before
voice answered the call's offer or after ICE completed or the call ended, and mapping each error
to its one shape; it never hands voice the candidates of a call whose offer voice has not
answered. It keeps its own record of the calls it joined (each one's offer secret, and the
call's language and identity until its offer), so a PATCH for a call whose offer was answered
and whose `phase` is `ended` or None gets the quiet 409 `call_ended`. It drops a record a
bounded time later (api/runtime.py): a join never offered once its join token's window has
passed, and an answered call `FORGOTTEN_KEPT_S` (60 s) after voice forgets it; a request for
the call then gets 403 `forbidden`, as for a call never joined.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import CallId
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.action_jobs import ActionJobs
from t2_agentic_voice.domain.ports.chat_model import ChatModel
from t2_agentic_voice.domain.ports.language_classifier import LanguageClassifier
from t2_agentic_voice.domain.ports.speech_to_text import SpeechToText
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK, Clock, EventSink, PhraseAudio
from t2_agentic_voice.voice.talkers import TalkerFactory

# Where a call stands, as api asks before it takes a PATCH: its offer answered and its
# connection being set up; connected (ICE completed, so the offer secret stops working); or
# ended, until voice forgets it (its peer closed).
CallPhase = Literal["connecting", "connected", "ended"]


@dataclass(frozen=True, kw_only=True)
class Candidate:
    """One trickled ICE candidate, as api parsed it from `PATCH /offer` (api/protocol.py's
    `IceCandidate`): its line, empty for the end of candidates; its media's ID; and its m-line's
    index."""

    candidate: str
    sdp_mid: str
    sdp_mline_index: int


class Calls(Protocol):
    """voice's entry point as api uses it: `VoiceCalls`, or a test's fake."""

    async def start(self) -> None:
        """Prepare what every call needs (`VoiceCalls` imports onnxruntime and warms one pair of
        models: calls.py's docstring); called once, at the runtime's start, before any offer."""

    async def answer(
        self, call_id: CallId, offer: str, *, caller: Caller, consent: Consent, language: Language
    ) -> str:
        """Answer the call's SDP offer with its SDP answer, the call's pipeline and session
        started, for `caller` with `consent`, held in `language` (the agent's, which api
        resolved at join with `VoiceAgent.call_language`). InvalidRequestError for an offer it
        refuses (one it cannot read, or the F7 offer), or for a call ID it already holds; the
        call is then not started."""

    async def add_candidates(self, call_id: CallId, candidates: Sequence[Candidate]) -> None:
        """Hand the call's peer its trickled candidates, in order. NotFoundError for a call it
        does not hold or that has ended; InvalidRequestError for a candidate line it cannot
        read, none of the candidates then given."""

    def phase(self, call_id: CallId) -> CallPhase | None:
        """Where the call stands; None for a call it does not hold, an ended call it has
        forgotten included (once its peer closed)."""

    async def end(self, call_id: CallId) -> None:
        """End the call now (`server`), if it holds it; return once its peer is closed."""

    async def aclose(self) -> None:
        """End every call and release what `start` built; called once, at the runtime's
        stop."""


class CallsFactory(Protocol):
    """How the runtime builds voice's entry point in its lifespan: `VoiceCalls` itself, or a
    test's function that returns a fake (the runtime's private `_calls`)."""

    def __call__(
        self,
        *,
        agent: VoiceAgent,
        settings: VoiceSettings,
        stt: SpeechToText,
        tts: TextToSpeech,
        phrases: PhraseAudio,
        tracing: Tracing,
        emit: EventSink,
        clock: Clock = SYSTEM_CLOCK,
        talker: TalkerFactory | None = None,
        chat: ChatModel | None = None,
        action_jobs: ActionJobs | None = None,
        classifier: LanguageClassifier | None = None,
    ) -> Calls:
        """voice's entry point for the runtime's calls, built with no IO."""
