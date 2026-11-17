"""The requests of one call's speech-to-text bridge (voice/stt_bridge.py): `SttRequests`, which
sends the `SpeechToText` port each request the bridge asks for, on a task of its own, and hands
its `Transcribing` as it goes and its one `Transcribed`, an empty, failed or unusable result
included.

Every request, each part's, names the language `languages` gives it as it goes (voice/
stt_language.py's `TurnLanguages`: the one last named, `listen_in`, unless a classifier chose
another for the turn), its `Transcribing` carrying it, and carries that language's Whisper
prompt: the call's `prompts`, built once a call by `call_prompts`, the prompt run W's arm W1
measured and kept (plan 006, Q23). A request that names no language, or one whose prompt holds no
word, carries none, as W1 sent none; with `stt.send_prompt` off, none carries one.

Under `stt.live_language = "detected"` (`detect_rule`), a turn's `held` or `turn` request whose
turn held at least `stt.detect_from_s` seconds of voiced speech, and is no overlap, goes twice at
once: as above, and naming no language with no prompt, for Whisper to detect it, its
`Transcribing` by `detected`, so no time is lost waiting for one before the other; the language
it heard is the transcript's `heard_language` where the provider reports one (D-100), else its
`language` (Whisper's; an adapter names none for a request naming none unless it heard one, as
the port says). A provider that reports no language heard (core/settings/stt.py's
`HEARS_NO_LANGUAGE`: Speechmatics, Cohere, Telnyx, Nabrah) gets no second request. When
domain/language_switch.py's `switch_to` says the turn moves the call, the turn's `Transcribed`
is the detecting request's (`switched`), and once it is the turn's own, the call's current
language moves to it (`TurnLanguages.listen_in`), so every later request names it; otherwise
the request in the current language stands, its failure the turn's. A failed detecting request
is logged by its kind alone and changes nothing.

Under `stt.live_language = "hinted"` (D-115; `detect_rule` gives its `HintRule` where the
provider gives a language probability, `SttSettings.hints`), every request goes once, its clip
giving the agent's other languages beside the one it names (`AudioClip.other_languages`, which
Scribe v3 takes as secondary languages); when domain/language_hint.py's `hinted_switch` says the
answer of a turn's `held` or `turn` request, no overlap's, moves the call (the language it heard,
its probability, its words), that answer, its language the code moved to, is the turn's
`Transcribed` (`switched`), and the call's current language moves as above.

Under `stt.live_language = "single"` (D-117; its `SingleRule` where the provider gives a language
probability, `SttSettings.single_holds`), every request goes once too: a turn's `held` or `turn`
request whose turn passes `detected`'s gate (the rule's `gate`; never an overlap's) names no
language, with the current language's prompt (Scribe's keyterms, as run H's arm (c) sent it), its
`Transcribing` naming the current language its answer is read in. When `hinted_switch` (the rule's
`hint`) says that answer moves the call, it is the turn's `Transcribed` (`switched`) and the call
moves as above; else its words stand, in the current language. Every other request names the
current language and never moves the call.

`drop` cancels every request in flight at the call's end, its `Transcribing` already handed.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Mapping
from dataclasses import replace
from typing import Any

from pipecat.services.stt_service import STTService

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError, ProviderErrorKind
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.settings.stt import HEARS_NO_LANGUAGE
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.language_hint import HintRule, SingleRule, hinted_switch
from t2_agentic_voice.domain.language_switch import DetectRule, switch_to
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, SpeechToText, Transcript
from t2_agentic_voice.domain.turn_language import spoken_codes
from t2_agentic_voice.domain.whisper_prompt import COMMAND_SPELLINGS, whisper_prompt
from t2_agentic_voice.domain.words import heard_code
from t2_agentic_voice.voice.pipecat_events import FailureReport
from t2_agentic_voice.voice.session.session_events import Transcribed, TranscriptPart
from t2_agentic_voice.voice.session_bridge import EventStream
from t2_agentic_voice.voice.stt_language import Named, TurnLanguages

log = get_logger(__name__)

# What a detecting request's `Transcribing` names: no language, by Whisper's own detection.
DETECTING = Named(language=None, by="detected")
# How a call follows the caller into another of the agent's languages from its answers: a long
# turn's second request naming none (`detected`), each turn's one request (`hinted`), or a long
# turn's one request naming none (`single`).
type SwitchRule = DetectRule | HintRule | SingleRule
type _Asked = tuple[Transcript | None, ProviderErrorKind | None, bool]


def call_prompts(agent: VoiceAgent, settings: VoiceSettings) -> dict[str, str]:
    """The Whisper prompt of each language a call of `agent` may name, by its primary code:
    `whisper_prompt` of the declaration's vocabulary, the `words.vocabulary` setting's terms
    after it, as run W's arm W1 built it (its `--prompt-agent`); none with `stt.send_prompt`
    off, and none for a language whose prompt holds no word."""
    if not settings.stt.send_prompt:
        return {}
    terms = (*agent.vocabulary.terms, *settings.words.vocabulary)
    prompts = {code: whisper_prompt(terms, code).text for code in COMMAND_SPELLINGS}
    return {code: text for code, text in prompts.items() if text}


def detect_rule(agent: VoiceAgent, settings: VoiceSettings) -> SwitchRule | None:
    """How a call of `agent`, of two codes or more, follows the caller from its answers: under
    `stt.live_language = "detected"` a long turn's second request naming none, from
    `stt.detect_from_s`, never on a provider that reports no language it heard
    (`HEARS_NO_LANGUAGE`); under `hinted` where it holds (`SttSettings.hints`), each turn's one
    request, from `stt.switch_min_probability`; under `single` where it holds
    (`SttSettings.single_holds`), a long turn's one request naming none, from both; else never
    (None)."""
    codes = tuple(code for code in map(heard_code, spoken_codes(agent)) if code is not None)
    stt = settings.stt
    if len(set(codes)) < 2:
        return None
    gate = DetectRule(from_s=stt.detect_from_s, codes=codes)
    hint = HintRule(min_probability=stt.switch_min_probability, codes=codes)
    if stt.live_language == "detected" and stt.provider not in HEARS_NO_LANGUAGE:
        return gate
    if stt.hints():
        return hint
    return SingleRule(gate=gate, hint=hint) if stt.single_holds() else None


class SttRequests:
    """The requests of the bridge `processor` (its tasks, its sample rate, whether it is
    usable): each to `stt`, its events to `events`, its failures to `report`, each naming the
    language `languages` gives it with that language's prompt of `prompts`, and a long turn's
    also naming none under a `DetectRule`, each with the agent's other languages under a
    `HintRule`, or a long turn's naming none instead under a `SingleRule` (`detect`; the
    module's)."""

    def __init__(
        self,
        processor: STTService,
        *,
        stt: SpeechToText,
        events: EventStream,
        report: FailureReport,
        prompts: Mapping[str, str],
        languages: TurnLanguages,
        detect: SwitchRule | None = None,
    ) -> None:
        self._processor = processor
        self._stt = stt
        self._events = events
        self._report = report
        self._prompts = dict(prompts)
        self._languages = languages
        self._detect = detect
        self._requests: set[asyncio.Task[Transcribed]] = set()

    def send(
        self,
        turn_id: int,
        audio: bytes,
        part: TranscriptPart,
        *,
        voiced_s: float | None = None,
        hand: bool = True,
    ) -> asyncio.Task[Transcribed]:
        """One request of the turn's `part`, on a task of its own (`transcribe`), also sent
        naming no language when its turn held `voiced_s` seconds of voiced speech enough to
        detect (None: an overlap's part, never); under a `HintRule`, its answer read for a
        move when it is a turn's own or held one and no overlap's; under a `SingleRule`, sent
        naming none instead, its answer read so, when such a turn passes the gate; with `hand`
        off, its `Transcribed` only returned (a `reuse` of it hands it)."""
        rule, own = self._detect, part in ("held", "turn")
        if isinstance(rule, SingleRule):
            alone = own and rule.gate.detects(voiced_s)
            read = rule.hint if alone else None
            asked = self.transcribe(turn_id, audio, part, read=read, alone=alone, hand=hand)
            return self._track(asked)
        detect = isinstance(rule, DetectRule) and own and rule.detects(voiced_s)
        read = rule if isinstance(rule, HintRule) and own and voiced_s is not None else None
        asked = self.transcribe(turn_id, audio, part, detect=detect, read=read, hand=hand)
        return self._track(asked)

    def reuse(
        self, source: asyncio.Task[Transcribed], part: TranscriptPart
    ) -> asyncio.Task[Transcribed]:
        """`source`'s result again, once it came, as the turn's `part`, with no request, on a
        task of its own."""
        return self._track(self._reused(source, part))

    def _track(self, work: Coroutine[Any, Any, Transcribed]) -> asyncio.Task[Transcribed]:
        """Run `work` on a task of its own, cancelled at the call's end."""
        request: asyncio.Task[Transcribed] = self._processor.create_task(
            work, name="t2v-stt-request"
        )
        self._requests.add(request)
        request.add_done_callback(self._requests.discard)
        return request

    async def transcribe(
        self,
        turn_id: int,
        audio: bytes,
        part: TranscriptPart,
        *,
        detect: bool = False,
        read: HintRule | None = None,
        alone: bool = False,
        hand: bool = True,
    ) -> Transcribed:
        """One request of the turn's `part`, its `Transcribing` handed as it goes, and its one
        `Transcribed`, handed (unless `hand` is off) and returned; none goes for no audio or an
        unusable bridge. With `detect`, a second naming no language, at the same time; with
        `read`, its answer read by that rule for a move; `alone`, it names no language (the
        module's)."""
        events, clock, rule = self._events, self._events.clock, self._detect
        heard = Transcribed(
            turn_id=turn_id, at=0.0, audio_s=0.0, sent_at=None, transcript=None, part=part
        )
        if not audio or not self._processor.is_usable:
            heard = replace(heard, at=clock.now())
            if hand:
                events.hand(heard)
            return heard
        sent_at, named = clock.now(), self._languages.named(turn_id, part)
        language = named.language
        others = rule.others(language) if isinstance(rule, HintRule) else ()
        rate = self._processor.sample_rate
        clip = AudioClip(pcm16=audio, sample_rate=rate, other_languages=others)
        events.hand(named.transcribing(turn_id, at=sent_at, audio_s=clip.seconds, part=part))
        prompt = None if language is None else self._prompts.get(language)
        asked = self._ask(turn_id, clip, None if alone else language, prompt)
        moved = None
        if detect and isinstance(rule, DetectRule):
            detecting = DETECTING.transcribing(turn_id, at=sent_at, audio_s=clip.seconds, part=part)
            events.hand(detecting)
            (transcript, failure, retryable), found = await asyncio.gather(
                asked, self._detecting(turn_id, clip)
            )
            if found is not None:
                said = None if transcript is None else transcript.text
                moved = switch_to(
                    language,
                    found.heard_language or found.language,
                    codes=rule.codes,
                    named_text=said,
                    detected_text=found.text,
                )
            if moved is not None and found is not None:
                transcript = found.model_copy(update={"language": moved})
                failure, retryable = None, False
        else:
            transcript, failure, retryable = await asked
            if read is not None and transcript is not None:
                moved = hinted_switch(
                    language,
                    transcript.heard_language,
                    transcript.language_probability,
                    text=transcript.text,
                    rule=read,
                )
            if transcript is not None and (moved is not None or alone):
                transcript = transcript.model_copy(update={"language": moved or language})
        if failure is not None:
            self._report.provider_failed("speech_to_text", failure, retryable, turn_id=turn_id)
        heard = replace(
            heard,
            at=clock.now(),
            audio_s=clip.seconds,
            sent_at=sent_at,
            transcript=transcript,
            failure=failure,
            retryable=retryable,
            switched=moved is not None,
        )
        if moved is not None and part == "turn":
            self._languages.listen_in(moved)
        if hand:
            events.hand(heard)
        return heard

    async def _ask(
        self, turn_id: int, clip: AudioClip, language: str | None, prompt: str | None
    ) -> _Asked:
        """One request to the provider: its transcript, or its failure's kind and whether asking
        again may succeed."""
        try:
            return await self._stt.transcribe(clip, language=language, prompt=prompt), None, False
        except ProviderError as error:
            return None, error.kind, error.retryable
        except Exception as error:  # an adapter's bug: still exactly one result for the part
            log.error("stt_request_failed", turn_id=turn_id, error=type(error).__name__)
            return None, "server_error", False

    async def _detecting(self, turn_id: int, clip: AudioClip) -> Transcript | None:
        """The turn naming no language, with no prompt, for Whisper to detect it; None when it
        failed, logged by its kind alone."""
        transcript, failure, _ = await self._ask(turn_id, clip, None, None)
        if failure is not None:
            log.warning("stt_detect_failed", turn_id=turn_id, kind=failure)
        return transcript

    async def _reused(self, source: asyncio.Task[Transcribed], part: TranscriptPart) -> Transcribed:
        heard = replace(await asyncio.shield(source), part=part, at=self._events.clock.now())
        moved = None if heard.transcript is None else heard_code(heard.transcript.language)
        if heard.switched and part == "turn" and moved is not None:
            self._languages.listen_in(moved)
        self._events.hand(heard)
        return heard

    async def drop(self) -> None:
        """The call has ended: every request in flight cancelled."""
        for request in list(self._requests):
            await self._processor.cancel_task(request)
