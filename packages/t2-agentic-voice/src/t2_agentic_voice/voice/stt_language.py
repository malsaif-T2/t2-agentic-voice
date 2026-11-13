"""Each turn's language in one call's speech-to-text bridge (voice/stt_bridge.py), under
`stt.live_language = "classified"`: `TurnLanguages`.

Built with the agent's codes, a classifier and the rule (domain/turn_language.py), it keeps, by
turn, what it heard and decided. With no classifier (any other setting, or an agent of one
code) every request names the session's language (`ListenIn`), `session`.

- **While the caller speaks.** Once a turn's audio holds `from_s` from where the speech detector
  heard its speech begin, counted in bytes, never on the clock, those seconds go to the
  classifier, once a turn, on a task of its own (the adapter works on a thread), so the verdict
  has the rest of the turn, the detector's stop and Smart Turn's decision to arrive. A turn the
  session marked an overlap is never classified.
- **Never waiting.** A turn's language is decided when its hold begins (in a call with no
  talker too, with no event of its own), or, with no hold, when the turn closes; each request
  then names the language in hand as it goes (`named`), its `Transcribing` carrying it, with
  when it was decided and the speech held then (run H's record, testing/turn_languages.py): the
  held request and the turn's own name the same, so a reused held result agrees with it. A verdict
  not in by then is `late`, and the turn keeps the current language. Speech resumed in the
  hold cancels the decision, and the next hold decides again.
- **Overlaps.** Every request of a turn marked an overlap (`hear_overlap`), its `window` and
  `overlap` parts and its own, names the current language, `overlap`, whatever verdict is in
  hand, their timing being the two-step rule's (D-061), so a turn is sent in one language.
- **The current language** moves only on `classified`; at first it is the session's.
- **The call's end** (`drop`) cancels the classifications in flight, and a result that comes
  after is dropped unread.

It never makes a request, the hold or a turn's end wait on the classifier, and the seconds it
hears live in memory with the turn (invariant 8).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from t2_agentic_voice.core.clock import Clock
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.events import LanguageBy
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.language_classifier import (
    LanguageClassifier,
    LanguageScores,
    scores_for,
)
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip
from t2_agentic_voice.domain.turn_language import (
    LanguageRule,
    Verdict,
    choose_language,
    current_after,
    spoken_codes,
)
from t2_agentic_voice.voice.session.session_events import Transcribing, TranscriptPart
from t2_agentic_voice.voice.stt_turn import HeldTurn

log = get_logger(__name__)


@dataclass(frozen=True, kw_only=True)
class Named:
    """The language a request names (None: none) and how it was chosen, with the verdict's best
    share and when it came when one was in hand, and, for a turn decided, when and on how many
    seconds of speech."""

    language: str | None
    by: LanguageBy
    share: float | None = None
    verdict_at: float | None = None
    decided_at: float | None = None
    speech_s: float | None = None

    def transcribing(
        self, turn_id: int, *, at: float, audio_s: float, part: TranscriptPart
    ) -> Transcribing:
        """The request's `Transcribing`, naming this language."""
        return Transcribing(
            turn_id=turn_id,
            at=at,
            audio_s=audio_s,
            part=part,
            language=self.language,
            language_by=self.by,
            share=self.share,
            verdict_at=self.verdict_at,
            decided_at=self.decided_at,
            speech_s=self.speech_s,
        )


@dataclass
class _Turn:
    """What `TurnLanguages` keeps of one turn."""

    asked: bool = False
    verdict: Verdict = "pending"
    verdict_at: float | None = None
    decided: Named | None = None
    before: str | None = None  # the current language before the decision moved it
    overlap: bool = False


def turn_languages(
    agent: VoiceAgent,
    settings: VoiceSettings,
    classifier: LanguageClassifier | None,
    clock: Clock,
) -> TurnLanguages:
    """A call's `TurnLanguages`: on `classifier` under `stt.live_language = "classified"`
    for an agent of two codes or more, with the settings' rule; otherwise with none."""
    codes = spoken_codes(agent)
    stt = settings.stt
    if stt.live_language != "classified" or classifier is None or len(codes) < 2:
        return TurnLanguages(clock=clock)
    rule = LanguageRule(from_s=stt.classifier_from_s, min_share=stt.classifier_min_share)
    return TurnLanguages(clock=clock, classifier=classifier, codes=codes, rule=rule)


class TurnLanguages:
    """Each turn's language in one call (the module's docstring), on the call's `clock`."""

    def __init__(
        self,
        *,
        clock: Clock,
        classifier: LanguageClassifier | None = None,
        codes: Sequence[str] = (),
        rule: LanguageRule | None = None,
    ) -> None:
        self._codes = tuple(dict.fromkeys(codes))
        on = classifier is not None and rule is not None and len(self._codes) > 1
        self._classifier = classifier if on else None
        self._rule = rule if on else None
        self._clock = clock
        self._current: str | None = None
        self._turns: dict[int, _Turn] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._dropped = False

    @property
    def classifies(self) -> bool:
        """Whether the call's turns are classified."""
        return self._classifier is not None

    def listen_in(self, language: str | None) -> None:
        """The session named the call's language (`ListenIn`): the current one from now on."""
        self._current = language

    def heard(self, turn: HeldTurn, sample_rate: int) -> None:
        """The open turn's audio grew: its first `from_s` of speech go to the classifier once it
        holds them, once a turn."""
        if self._classifier is None or self._rule is None or self._dropped:
            return
        state = self._turn(turn.turn_id)
        if state.asked or state.overlap or state.decided is not None or turn.overlap is not None:
            return
        if _speech_s(turn, sample_rate) < self._rule.from_s:
            return
        state.asked = True
        end = turn.speech + round(self._rule.from_s * sample_rate) * 2
        clip = AudioClip(pcm16=bytes(turn.audio[turn.speech : end]), sample_rate=sample_rate)
        task = asyncio.create_task(self._classify(state, clip), name="t2v-language")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def held(self, turn: HeldTurn, sample_rate: int, *, began: bool) -> None:
        """The turn's hold began (`began`: its language decided now) or the caller spoke again
        within it (the decision cancelled, the current language as it was before it)."""
        if self._classifier is None or turn.overlap is not None:
            return
        state = self._turn(turn.turn_id)
        if began and state.decided is None:
            self._decide(state, turn, sample_rate)
        elif not began and state.decided is not None:
            self._undo(state)

    def overlap(self, turn_id: int) -> None:
        """The session marked the turn an overlap: every request of it names the current
        language, and a decision it had made is undone."""
        state = self._turn(turn_id)
        state.overlap = True
        if state.decided is not None:
            self._undo(state)

    def closed(self, turn: HeldTurn, sample_rate: int) -> None:
        """The turn closed: decided now unless its hold decided it; older turns forgotten."""
        if self._classifier is None:
            return
        state = self._turn(turn.turn_id)
        if state.decided is None and not state.overlap and turn.overlap is None:
            self._decide(state, turn, sample_rate)
        for older in [n for n in self._turns if n < turn.turn_id - 1]:
            del self._turns[older]

    def named(self, turn_id: int, part: TranscriptPart) -> Named:
        """The language the turn's request of `part` names as it goes (the module's
        docstring)."""
        if self._classifier is None:
            return Named(language=self._current, by="session")
        state = self._turns.get(turn_id)
        if part in ("window", "overlap") or (state is not None and state.overlap):
            return Named(language=self._current, by="overlap")
        if state is None or state.decided is None:  # never so: decided before its request
            return Named(language=self._current, by="late")
        return state.decided

    async def drop(self) -> None:
        """The call has ended: every classification in flight cancelled, none read after."""
        self._dropped = True
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _turn(self, turn_id: int) -> _Turn:
        return self._turns.setdefault(turn_id, _Turn())

    def _decide(self, state: _Turn, turn: HeldTurn, sample_rate: int) -> None:
        verdict: Verdict = state.verdict if state.asked else "pending"
        speech_s = _speech_s(turn, sample_rate)
        choice = choose_language(self._current, verdict, speech_s=speech_s, rule=self._rule)
        share = verdict.best[1] if isinstance(verdict, LanguageScores) else None
        state.before = self._current
        self._current = current_after(self._current, choice)
        at = state.verdict_at if share is not None else None
        state.decided = Named(
            language=choice.language,
            by=choice.by,
            share=share,
            verdict_at=at,
            decided_at=self._clock.now(),
            speech_s=speech_s,
        )

    def _undo(self, state: _Turn) -> None:
        if state.decided is not None and state.decided.by == "classified":
            self._current = state.before
        state.decided = None

    async def _classify(self, state: _Turn, clip: AudioClip) -> None:
        """The classifier's verdict on `clip`, kept for its turn unless the call has ended."""
        classifier = self._classifier
        if classifier is None:
            return
        verdict: Verdict
        try:
            answer = await classifier.classify(clip, among=self._codes)
            found = scores_for(answer, among=self._codes)
            verdict = "busy" if found is None else found
        except ProviderError as error:
            log.warning("language_failed", classifier=classifier.name, kind=error.kind)
            verdict = "failed"
        except Exception as error:  # an adapter's bug: the turn keeps its language
            log.error("language_failed", classifier=classifier.name, error=type(error).__name__)
            verdict = "failed"
        if not self._dropped:
            state.verdict, state.verdict_at = verdict, self._clock.now()


def _speech_s(turn: HeldTurn, sample_rate: int) -> float:
    """The seconds of the turn's audio held from where its speech began, counted in bytes."""
    return max(0, len(turn.audio) - turn.speech) / (2 * sample_rate)
