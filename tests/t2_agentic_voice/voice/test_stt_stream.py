"""A call heard over its stream (`stt.streaming`; voice/stt_stream.py, stt_streamed.py; plan 010's
5.1), on ElevenLabs' adapter and a fake Scribe v3 Live socket: a turn's held request is a commit
and its answer the committed words, with no request; at the detector's stop the commit goes and
its words wait for Smart Turn's verdict; a pause called unfinished leaves its commit's words to
the next commit, never handed alone (D-120's drop), as speech resumed in the hold does; every
frame is fed, the commit after it, and what no turn holds as silence of its length; another
language opens another stream; and with the setting off, or a switch rule, the call is heard by
request as before."""

from __future__ import annotations

import base64
from urllib.parse import parse_qs, urlsplit

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.domain.language_switch import DetectRule
from t2_agentic_voice.voice.session.session_events import (
    HoldResumed,
    Transcribed,
    Transcribing,
    TurnHeld,
)
from t2_agentic_voice.voice.stt_stream import CallStream, StreamHooks
from t2_agentic_voice.voice.turn_hold import TurnHeldFrame, TurnUnfinishedFrame

from tests.t2_agentic_voice.adapters.live_support import BATCH_WORDS, FakeScribe
from tests.t2_agentic_voice.voice.kit import audio_frames
from tests.t2_agentic_voice.voice.stream_kit import (
    Step,
    closed,
    heard,
    held_turn,
    loud_s,
    opened,
    resumed,
    stopped,
)

FULL = "I want to reset my password"


def _at(events: list[object], kind: type[object], part: str | None = None) -> int:
    for index, event in enumerate(events):
        if isinstance(event, kind) and (part is None or getattr(event, "part", None) == part):
            return index
    raise AssertionError(f"no {kind.__name__}")


def test_the_setting_is_off_by_default() -> None:
    """GP-18: no call streams until a live check keeps it."""
    assert SttSettings().streaming is False
    assert VoiceSettings(env="test").stt.streaming is False


def test_a_held_request_is_a_commit_and_its_answer_the_committed_words() -> None:
    scribe = FakeScribe([FULL])
    call = heard(scribe, held_turn())
    assert call.words("held") == [FULL] and call.words("turn") == [FULL]  # the turn reuses it
    assert call.sent() == ["held"] and call.batch.requests == []  # no request went
    assert scribe.commits() == 1 and len(scribe.opened) == 1
    (sent,) = call.session.of(Transcribing)
    (held,) = call.of("held")
    assert (sent.language, held.transcript and held.transcript.language) == ("en", "en")
    assert held.sent_at == sent.at and held.audio_s == sent.audio_s > 0
    query = parse_qs(urlsplit(scribe.opened[0][0]).query)
    assert query["language_code"] == ["en"] and query["model_id"] == ["scribe_v3_live"]


def test_every_frame_is_fed_and_the_commit_goes_after_the_turns_audio() -> None:
    scribe = FakeScribe([FULL])
    call = heard(scribe, held_turn())
    messages = scribe.messages()
    commit = next(i for i, message in enumerate(messages) if message["commit"])
    assert isinstance(call.stt.stream, CallStream) and messages[commit]["audio_base_64"] == ""
    assert len(scribe.audio()) >= 2 * 16_000 * 2  # the lead and the turn, silence included
    before = b"".join(base64.b64decode(str(m["audio_base_64"])) for m in messages[:commit])
    after = b"".join(base64.b64decode(str(m["audio_base_64"])) for m in messages[commit:])
    assert any(before) and not any(after)  # the turn's speech, then only the hold's silence


def test_the_audio_no_turn_holds_reaches_the_stream_as_silence_of_its_length() -> None:
    """What the detector never called speech between turns (the agent's echo, a television)
    goes as silence of its length, a pre-roll late: the turn's commit holds the turn's speech
    from its pre-roll, as its request would, and nothing heard before."""
    scribe = FakeScribe([FULL])
    call = heard(scribe, [*audio_frames(3.0), *held_turn()])  # 3 s of sound, no speech start
    assert call.words("held") == [FULL] and call.batch.requests == []
    assert loud_s(scribe) == [0.5]  # the pre-roll's 0.1 s of speech and the turn's 0.4 s
    assert len(scribe.audio()) >= round(6.0 * 16_000) * 2  # the lead, the 3 s, the turn's


def test_at_the_detectors_stop_the_commit_goes_and_its_words_wait_for_the_verdict() -> None:
    scribe = FakeScribe([FULL])
    steps: list[Step] = [*opened(), *stopped(), 0.1, TurnHeldFrame(), *closed()]
    call = heard(scribe, steps, at_stop=True)
    events: list[object] = list(call.session.events)
    assert _at(events, Transcribing) < _at(events, TurnHeld) < _at(events, Transcribed, "held")
    assert call.words("held") == [FULL] and call.words("turn") == [FULL]
    assert scribe.commits() == 1 and call.batch.requests == []


def test_a_pause_called_unfinished_leaves_its_words_to_the_next_commit() -> None:
    scribe = FakeScribe(["I want to", "reset my password"])
    steps: list[Step] = [*opened(), *stopped(), 0.1, TurnUnfinishedFrame()]
    steps += [*resumed(held=False), *stopped(), 0.1, TurnHeldFrame(), *closed()]
    call = heard(scribe, steps, at_stop=True)
    assert call.words("held") == [FULL]  # handed once, the whole turn's words
    assert call.words("turn") == [FULL] and call.sent() == ["held", "held"]
    assert scribe.commits() == 2 and call.batch.requests == []
    assert len(call.session.of(TurnHeld)) == 1 and call.session.of(HoldResumed) == []


def test_speech_resumed_in_the_hold_joins_the_turns_next_commit() -> None:
    scribe = FakeScribe(["I want to", "reset my password"], delay_s=0.3)
    steps: list[Step] = [*opened(), *stopped(), 0.05, TurnHeldFrame()]
    steps += [*resumed(held=True), *stopped(), 0.05, TurnHeldFrame(), *closed()]
    call = heard(scribe, steps)
    assert len(call.session.of(HoldResumed)) == 1
    assert call.words("held") == [FULL] and call.words("turn") == [FULL]
    assert scribe.commits() == 2 and call.batch.requests == []


def test_a_turns_close_with_no_speech_since_its_commit_commits_nothing_more() -> None:
    """A pause called unfinished, then the fallback's end: the close's request joins the
    turn's one commit."""
    scribe = FakeScribe([FULL])
    steps: list[Step] = [*opened(), *stopped(), 0.1, TurnUnfinishedFrame(), *closed()]
    call = heard(scribe, steps, at_stop=True)
    assert call.words("turn") == [FULL] and call.sent() == ["held", "turn"]
    assert scribe.commits() == 1 and call.batch.requests == []


def test_another_language_opens_another_stream_in_it() -> None:
    scribe = FakeScribe([FULL])
    switch: Step = lambda stt: stt.listen_in("ar")  # noqa: E731
    call = heard(scribe, [switch, 0.05, *held_turn()])
    assert len(scribe.opened) == 2 and scribe.closes >= 1  # the first closed
    languages = [parse_qs(urlsplit(url).query)["language_code"] for url, _, _ in scribe.opened]
    assert languages == [["en"], ["ar"]]
    assert call.words("turn") == [BATCH_WORDS]  # before the new stream heard its lead


def test_with_the_setting_off_the_call_is_heard_by_request_as_before() -> None:
    scribe = FakeScribe([FULL])
    call = heard(scribe, held_turn(), streaming=False)
    assert type(call.stt.stream) is StreamHooks and scribe.opened == []
    assert call.words("held") == [BATCH_WORDS] and len(call.batch.requests) == 1


def test_a_call_with_a_switch_rule_is_heard_by_request() -> None:
    """Under live_language detected (and hinted, single or classified) every request goes by
    request as today: a stream's committed words name no language but the one it opened in."""
    scribe = FakeScribe([FULL])
    rule = DetectRule(from_s=1.2, codes=("ar", "en"))
    call = heard(scribe, held_turn(), detect=rule)
    assert type(call.stt.stream) is StreamHooks and scribe.opened == []
    assert call.words("held") == [BATCH_WORDS]
