"""Each turn's language in a file-fed call of an agent of two languages (D-086, run H's H1):
`turn_languages`, which `poe eval-languages` runs over the golden set, and `chosen`, the language
each of those turns would go in for a call held in any of them; provisional, re-exported by the
`evals` facade, since an app imports only public modules.

Shaped as testing/turns.py's `turn_ends`: each clip a fresh call of one `VoiceCalls`, started
once, fed at real-time pace with `lead_s` of silence before it and `tail_s` after it; a
speech-to-text that answers at once with nothing heard, and a text-to-speech and phrase audio
that say every text as silence of no length (turns.py's), so no request leaves the machine.
Every call is an echo call held in the first of `languages`. Under `stt.live_language =
"classified"` the calls hear each turn's language through `classifier` (voice/stt_language.py),
loaded once with the languages' codes before the first call and closed by its owner, the caller.
The helper wraps it to keep when each classification was asked and came, on the calls' clock,
and what it gave. One call runs at a time, so a turn finds the classifier busy only when an
earlier turn of its own call still holds it.

Each turn's record (`LanguageTurn`), its times in milliseconds from the clip's first frame (the
silence fed before it left out): its end, as `TurnEnd` gives it; the language its request named
and how (`by`); when the turn's language was decided, and the seconds of its speech then (its
hold's start, when a talker call's held request goes, or its close when no hold began: the
bridge decides at that moment in a call with no talker too); and its classification's ask,
verdict and time.

`chosen` reads those records with the library's pure rule (domain/turn_language.py) as a call
held in `current` decides them, at the same moments, so a verdict counts as in hand only when it
came by the decision. The language a call was held in changes only the language its requests
name, never `by`, so one record gives every call language's choices, and for the language the
calls were held in they are what the calls named.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict

from t2_agentic_voice.core.clock import SYSTEM_CLOCK, Clock
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.events import Event, LanguageBy
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.language_classifier import (
    LanguageClassifier,
    LanguageScores,
    scores_for,
)
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip
from t2_agentic_voice.domain.turn_language import (
    LanguageChoice,
    LanguageRule,
    Verdict,
    choose_language,
    current_after,
    spoken_codes,
)
from t2_agentic_voice.testing.turns import CLIP_RATE, HearsNothing, SaysSilence
from t2_agentic_voice.voice.calls import VoiceCalls
from t2_agentic_voice.voice.session.session_events import Transcribing, TurnClosed, TurnOpened

if TYPE_CHECKING:  # Pipecat's side, imported at first use
    from t2_agentic_voice.voice.file_transport import FedCall

_CALLER = Caller(subject="turn-languages")
_CONSENT = Consent(version=None, record_audio=False)
# What a classification gave: its scores, or the classifier busy, or failed (an error, or an
# answer that does not parse), as voice/stt_language.py reads it.
type Answered = LanguageScores | Literal["busy", "failed"]


class LanguageTurn(BaseModel):
    """One turn of a call `turn_languages` fed (the module's docstring), its times in ms from the
    clip's first frame: when the speech detector last heard the speech stop before its end and
    when the turn ended; the language its request named and how (`by`: None when no request
    went); when its language was decided and the seconds of its speech then (none under
    `session`, or for an overlap); and when its classification was asked and came, and what it
    gave (none when it was not asked, and no verdict for one the call's end cancelled)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    speech_stop_ms: float
    end_ms: float
    named: str | None = None
    by: LanguageBy | None = None
    decided_ms: float | None = None
    speech_s: float | None = None
    asked_ms: float | None = None
    verdict_ms: float | None = None
    verdict: Answered | None = None


@dataclass
class _Ask:
    """One classification: when it was asked and came, on the calls' clock, and what it gave."""

    asked_at: float
    came_at: float | None = None
    verdict: Answered | None = None


class _Recording:
    """The caller's classifier, each classification it makes kept (`asks`, the call's), its
    answer handed on unchanged."""

    def __init__(self, classifier: LanguageClassifier, clock: Clock) -> None:
        self.name = classifier.name
        self._classifier, self._clock = classifier, clock
        self.asks: list[_Ask] = []

    async def load(self, among: Sequence[str]) -> None:
        await self._classifier.load(among)

    async def classify(self, clip: AudioClip, *, among: Sequence[str]) -> LanguageScores | None:
        ask = _Ask(asked_at=self._clock.now())
        self.asks.append(ask)
        try:
            answer = await self._classifier.classify(clip, among=among)
        except Exception:
            ask.came_at, ask.verdict = self._clock.now(), "failed"
            raise
        ask.came_at = self._clock.now()
        try:
            found = scores_for(answer, among=among)
        except ProviderError:
            ask.verdict = "failed"
        else:
            ask.verdict = "busy" if found is None else found
        return answer

    async def aclose(self) -> None:
        """Nothing: the caller closes the classifier it gave."""


def _ignored(event: Event) -> None:
    """Where a measured call's public events go: nowhere, since only its turns count."""


async def turn_languages(
    clips: Iterable[AudioClip],
    *,
    languages: Sequence[Language],
    settings: VoiceSettings,
    classifier: LanguageClassifier | None,
    lead_s: float,
    tail_s: float,
    _clock: Clock = SYSTEM_CLOCK,
) -> AsyncIterator[tuple[LanguageTurn, ...]]:
    """Each clip's turns, clip by clip, in the order they ended: each clip (mono PCM16 at
    16 kHz) fed as a fresh call of an echo agent of `languages`, held in the first of them,
    with `settings`, through `classifier` under `stt.live_language = "classified"` (the
    module's docstring). The calls are one `VoiceCalls`, started before the first clip and
    closed after the last, or when the caller stops iterating and closes the iterator.
    ValueError, before any call: a clip at another rate; languages of one code; a setting
    other than `session` and `classified`; a classifier under `session`, or none under
    `classified`."""
    from t2_agentic_voice.voice.file_transport import feed_file  # Pipecat's side, at first use

    clips = list(clips)
    if any(clip.sample_rate != CLIP_RATE for clip in clips):
        raise ValueError(f"a file-fed call's caller is mono PCM16 at {CLIP_RATE} Hz")
    agent = VoiceAgent(name="turn-languages", languages=list(languages))
    codes = spoken_codes(agent)
    if len(codes) < 2:
        raise ValueError("the calls' agent speaks two languages or more, each its own code")
    live = settings.stt.live_language
    if live not in ("session", "classified"):
        raise ValueError("the calls are held under stt.live_language session or classified")
    if (live == "classified") != (classifier is not None):
        raise ValueError("a classifier is heard under stt.live_language classified, and only there")
    recording = None if classifier is None else _Recording(classifier, _clock)
    if recording is not None:
        await recording.load(codes)
    silence = SaysSilence()
    calls = VoiceCalls(
        agent=agent,
        settings=settings,
        stt=HearsNothing(),
        tts=silence,
        phrases=silence,
        tracing=Tracing(),
        emit=_ignored,
        clock=_clock,
        classifier=recording,
    )
    await calls.start()
    try:
        for number, clip in enumerate(clips):
            if recording is not None:
                recording.asks = []
            fed = await feed_file(
                calls,
                clip,
                call_id=f"turn-languages-{number}",
                caller=_CALLER,
                consent=_CONSENT,
                language=agent.languages[0],
                lead_s=lead_s,
                tail_s=tail_s,
            )
            yield _turns(fed, () if recording is None else recording.asks)
    finally:
        await calls.aclose()


def _turns(fed: FedCall, asks: Sequence[_Ask]) -> tuple[LanguageTurn, ...]:
    """The call's turns, each with its first request's language and its classification: the
    one asked while it was the turn last opened."""
    start = fed.started_at

    def ms(at: float | None) -> float | None:
        return None if at is None else (at - start) * 1000

    opened = [event for event in fed.events if isinstance(event, TurnOpened)]
    sent: dict[int, Transcribing] = {}
    for event in fed.events:
        if isinstance(event, Transcribing):
            sent.setdefault(event.turn_id, event)
    asked: dict[int, _Ask] = {}
    for ask in asks:
        before = [turn for turn in opened if turn.at <= ask.asked_at]
        if before:
            asked.setdefault(before[-1].turn_id, ask)
    turns: list[LanguageTurn] = []
    for event in fed.events:
        if not isinstance(event, TurnClosed):
            continue
        request, made = sent.get(event.turn_id), asked.get(event.turn_id)
        turns.append(
            LanguageTurn(
                speech_stop_ms=(event.speech_ended_at - start) * 1000,
                end_ms=(event.at - start) * 1000,
                named=None if request is None else request.language,
                by=None if request is None else request.language_by,
                decided_ms=None if request is None else ms(request.decided_at),
                speech_s=None if request is None else request.speech_s,
                asked_ms=None if made is None else ms(made.asked_at),
                verdict_ms=None if made is None else ms(made.came_at),
                verdict=None if made is None else made.verdict,
            )
        )
    return tuple(turns)


def chosen(
    turns: Sequence[LanguageTurn], *, current: str, from_s: float, min_share: float
) -> tuple[LanguageChoice, ...]:
    """The language each of one call's `turns`, in order, would be sent in by a call held in
    `current`, and how, under the rule of `from_s` and `min_share` (the module's docstring): a
    session's turn and an overlap's keep the current language as the call did."""
    rule = LanguageRule(from_s=from_s, min_share=min_share)
    language: str | None = current
    found: list[LanguageChoice] = []
    for turn in turns:
        if turn.by == "session" or turn.by == "overlap":
            choice = LanguageChoice(language=language, by=turn.by)
        else:
            speech_s = turn.speech_s or 0.0
            choice = choose_language(language, _in_hand(turn), speech_s=speech_s, rule=rule)
        language = current_after(language, choice)
        found.append(choice)
    return tuple(found)


def _in_hand(turn: LanguageTurn) -> Verdict:
    """What the turn's decision had in hand: its verdict when it came by then, else none yet."""
    came, decided = turn.verdict_ms, turn.decided_ms
    if turn.verdict is None or came is None or decided is None or came > decided:
        return "pending"
    return turn.verdict
