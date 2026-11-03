"""The session's overlaps (voice/session/overlap.py), on their own, the rule a fake (conftest.py's
`rule`): the call's words are the preset's, the agent's and the settings' additions; an overlap
opens with `duck` then `HearOverlap`; a window's verdict to go on leaves it open and any other
decides it, as the whole overlap's does whatever it says; each transcript's speech time, words,
bounds and filter reach the rule; the `unduck`s wait until no overlap is undecided; and the turn's
own transcript is judged again only after a verdict to go on that speech followed. The overlaps
in a call are test_overlap_session.py's."""

from __future__ import annotations

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.core.settings.words import WordSettings
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.speech_to_text import Transcript
from t2_agentic_voice.domain.words import PRESET_WORDS, Phrases
from t2_agentic_voice.voice.protocol import Duck
from t2_agentic_voice.voice.session.commands import HearOverlap, Send
from t2_agentic_voice.voice.session.overlap import Overlaps, OverlapState, call_words
from t2_agentic_voice.voice.session.session_events import (
    Transcribed,
    Transcribing,
    TranscriptPart,
)

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.overlap_support import (
    LISTENING,
    LISTENING_TEXT,
    NEW_TEXT,
    STOP,
    STOP_TEXT,
    FakeRule,
    two_step,
)


def _heard(
    turn_id: int,
    text: str | None,
    *,
    part: TranscriptPart,
    sent_at: float | None,
    at: float = 3.0,
    no_speech_prob: float | None = None,
) -> Transcribed:
    transcript = None
    if text is not None:
        transcript = Transcript(text=text, language="en", no_speech_prob=no_speech_prob)
    return Transcribed(
        turn_id=turn_id, at=at, audio_s=1.0, sent_at=sent_at, transcript=transcript, part=part
    )


def _asked(turn_id: int, part: TranscriptPart) -> Transcribing:
    return Transcribing(turn_id=turn_id, at=2.0, audio_s=1.0, part=part)


def test_the_calls_words_are_the_presets_the_agents_and_the_settings_additions(
    settings: VoiceSettings,
) -> None:
    phrases = Phrases.defaults().extend(stop={"en": ["made-up halt"], "ar": ["كلمة مختلقة"]})
    english = Language.english(greeting="A made-up greeting")
    agent = VoiceAgent(name="words-test", languages=[english], phrases=phrases)
    added = WordSettings(stop={"en": ("made-up halt", "made-up cease")}, no={"en": ("nah-ish",)})
    io = FakeSessionIO(settings.model_copy(update={"words": added}), agent=agent)
    words, preset = call_words(io.setup), PRESET_WORDS["en"]
    assert words.stop == tuple(dict.fromkeys((*preset.stop, "made-up halt", "made-up cease")))
    assert words.no == tuple(dict.fromkeys((*preset.no, "nah-ish")))
    assert (words.repeat, words.backchannel, words.wait) == (
        preset.repeat,
        preset.backchannel,
        preset.wait,
    )
    assert "كلمة مختلقة" not in words.stop  # another language's


def test_an_overlap_opens_with_duck_then_hear_overlap(settings: VoiceSettings) -> None:
    custom = two_step(settings, duck_level=0.4, first_window_ms=600)
    overlaps = Overlaps(FakeSessionIO(custom).setup)
    assert (overlaps.get(3), overlaps.open_turns) == (None, ())
    commands = overlaps.open(3, reply_id=2, speech_at=10.0, at=10.34)
    assert commands == [Send(message=Duck(level=0.4)), HearOverlap(turn_id=3, window_ms=600)]
    assert overlaps.get(3) == OverlapState(turn_id=3, reply_id=2, speech_at=10.0, ducked_at=10.34)
    assert overlaps.open_turns == (3,) and overlaps.settle() == 0  # undecided: no unduck yet


def test_a_window_that_goes_on_waits_and_the_whole_overlap_decides(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    """The window's verdict to go on leaves the overlap open; the whole overlap's decides it, a
    verdict to go on included; once decided, nothing more is judged. The window's speech runs
    to its request, the whole overlap's to its request less the detector's stop delay."""
    overlaps = Overlaps(FakeSessionIO(two_step(settings)).setup)
    overlaps.open(0, reply_id=1, speech_at=1.0, at=1.34)
    overlaps.requested(_asked(0, "window"))
    overlaps.requested(_asked(0, "overlap"))
    overlaps.requested(_asked(5, "overlap"))  # no overlap: nothing kept
    assert overlaps.get(0) is not None and overlaps.get(0).waiting  # type: ignore[union-attr]
    window = overlaps.judge(_heard(0, LISTENING_TEXT, part="window", sent_at=1.45), played=())
    assert window == LISTENING and overlaps.open_turns == (0,)
    whole = overlaps.judge(_heard(0, LISTENING_TEXT, part="overlap", sent_at=2.6), played=("a",))
    state = overlaps.get(0)
    assert state is not None and not state.waiting
    assert (state.window, state.overlap, state.decided, state.decided_by) == (
        LISTENING,
        LISTENING,
        whole,
        "overlap",
    )
    assert overlaps.judge(_heard(0, STOP_TEXT, part="turn", sent_at=3.0), played=()) is None
    assert overlaps.judge(_heard(4, STOP_TEXT, part="window", sent_at=1.0), played=()) is None
    window_s, whole_s = (overlap.speech_s for overlap in rule.judged)
    assert window_s == pytest.approx(0.45) and whole_s == pytest.approx(2.6 - 1.0 - 0.2)
    assert rule.judged[1].played == ("a",) and rule.judged[1].language == "en"
    assert overlaps.settle() == 1 and overlaps.settle() == 0  # one unduck, once


def test_a_window_that_stops_decides_and_the_rule_reads_the_calls_words_bounds_and_filter(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    stt = SttSettings(no_speech_max=0.6, caption_filter=True)
    custom = two_step(settings, min_words=3, short_words=1, short_s=1.2)
    setup = FakeSessionIO(custom.model_copy(update={"stt": stt})).setup
    overlaps = Overlaps(setup)
    overlaps.open(0, reply_id=1, speech_at=1.0, at=1.3)
    heard = _heard(0, STOP_TEXT, part="window", sent_at=None, at=1.2, no_speech_prob=0.1)
    assert overlaps.judge(heard, played=()) == STOP
    assert overlaps.get(0).decided_by == "window"  # type: ignore[union-attr]
    (given,) = rule.given
    assert given["words"] == call_words(setup) and given["no_speech_max"] == 0.6
    assert given["bounds"] == (3, 1, 1.2) and given["captions"] == ()  # the list is Track A's
    assert rule.judged[0].no_speech_prob == 0.1 and rule.judged[0].speech_s == pytest.approx(0.2)


def test_unducks_wait_until_no_overlap_is_undecided(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    overlaps = Overlaps(FakeSessionIO(two_step(settings)).setup)
    overlaps.open(0, reply_id=1, speech_at=1.0, at=1.3)
    overlaps.open(1, reply_id=1, speech_at=3.0, at=3.3)
    overlaps.judge(_heard(0, LISTENING_TEXT, part="overlap", sent_at=2.5), played=())
    assert overlaps.open_turns == (1,) and overlaps.settle() == 0
    overlaps.judge(_heard(1, None, part="overlap", sent_at=None, at=4.0), played=())
    assert rule.texts == [LISTENING_TEXT, ""] and overlaps.settle() == 2


@pytest.mark.parametrize(
    ("asked", "decided_by", "judged"),
    [(("overlap", "turn"), "overlap", True), (("overlap",), "overlap", False)],
    ids=["speech-followed", "no-speech-followed"],
)
def test_the_turns_own_transcript_is_judged_again_only_when_speech_followed(
    settings: VoiceSettings,
    rule: FakeRule,
    asked: tuple[TranscriptPart, ...],
    decided_by: TranscriptPart,
    judged: bool,
) -> None:
    overlaps = Overlaps(FakeSessionIO(two_step(settings)).setup)
    overlaps.open(0, reply_id=1, speech_at=1.0, at=1.3)
    turn = _heard(0, f"{LISTENING_TEXT} {NEW_TEXT}", part="turn", sent_at=4.0)
    assert overlaps.judge_after(turn, played=(), ended_at=3.5) is None  # not decided yet
    for part in asked:
        overlaps.requested(_asked(0, part))
    overlaps.judge(_heard(0, LISTENING_TEXT, part=decided_by, sent_at=2.4), played=())
    again = overlaps.judge_after(turn, played=("b",), ended_at=3.5)
    assert (again is not None) is judged
    assert (
        overlaps.judge_after(_heard(7, "x", part="turn", sent_at=1.0), played=(), ended_at=None)
        is None
    )
    if judged:
        assert rule.judged[-1].speech_s == pytest.approx(2.5)


def test_a_turn_that_decided_its_overlap_is_not_judged_again(
    settings: VoiceSettings, rule: FakeRule
) -> None:
    """The whole overlap's request never went, so the turn's own transcript decided it: no
    second verdict on the same words; nor after a verdict that stopped the agent."""
    rule.script[NEW_TEXT] = LISTENING
    overlaps = Overlaps(FakeSessionIO(two_step(settings)).setup)
    overlaps.open(0, reply_id=1, speech_at=1.0, at=1.3)
    overlaps.requested(_asked(0, "turn"))
    turn = _heard(0, NEW_TEXT, part="turn", sent_at=3.0)
    assert overlaps.judge(turn, played=(), ended_at=2.0) == LISTENING
    assert overlaps.judge_after(turn, played=(), ended_at=2.0) is None
    overlaps.open(1, reply_id=1, speech_at=5.0, at=5.3)
    overlaps.requested(_asked(1, "turn"))
    overlaps.judge(_heard(1, STOP_TEXT, part="window", sent_at=5.5), played=())
    assert (
        overlaps.judge_after(
            _heard(1, NEW_TEXT, part="turn", sent_at=7.0), played=(), ended_at=None
        )
        is None
    )
