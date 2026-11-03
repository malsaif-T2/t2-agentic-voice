"""What came of a clip replayed over a reply (testing/overlap_replay.py's `replay_of`), read from
hand-made calls as the file-fed transport hands them: a stop the window decided, timed from the
labelled word end to the last agent frame before the echo's audio; a reply that went on once the
whole overlap's transcript came; a transcript that came while the session was deciding, which did
not decide; a repeat; speech after a go on that stopped the agent on the turn's own transcript;
a clip of two overlaps, each request carrying its turn; and a clip whose speech opened no
overlap. The results are frozen."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from t2_agentic_voice.core.events import Interrupted, InterruptionKind, InterruptionReason
from t2_agentic_voice.domain.ports.speech_to_text import Transcript
from t2_agentic_voice.evals import OverlapReplay, OverlapRequest
from t2_agentic_voice.testing.overlap_replay import replay_of
from t2_agentic_voice.voice.file_transport import FedCall
from t2_agentic_voice.voice.protocol import Duck, Unduck
from t2_agentic_voice.voice.session.commands import (
    Command,
    HearOverlap,
    Send,
    Speak,
    StopSpeaking,
)
from t2_agentic_voice.voice.session.session_events import (
    AgentAudio,
    ClauseQueued,
    SessionEvent,
    Transcribed,
    Transcribing,
    TranscriptPart,
    TurnClosed,
    TurnOpened,
)

WALL = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
START = 20.0  # the clip's first frame, on the call's clock


def _interrupted(kind: InterruptionKind, reason: InterruptionReason) -> Interrupted:
    return Interrupted(call_id="audio-call-0", at=WALL, kind=kind, reason=reason)


def _heard(part: TranscriptPart, at: float, text: str, *, turn: int = 0) -> list[SessionEvent]:
    """A request of `part` sent 0.2 s before `at` and answered at `at`, hearing `text`."""
    heard = Transcript(text=text, language="ar", no_speech_prob=0.02)
    return [
        Transcribing(turn_id=turn, at=at - 0.2, audio_s=0.75, part=part),
        Transcribed(
            turn_id=turn, at=at, audio_s=0.75, sent_at=at - 0.2, transcript=heard, part=part
        ),
    ]


def _frames(*ats: float) -> list[SessionEvent]:
    return [AgentAudio(pcm16=b"\x01\x00" * 4, sample_rate=24_000, at=at) for at in ats]


def _fed(
    events: list[SessionEvent],
    commands: list[tuple[float, Command]],
    *,
    late: float = 0.001,
) -> FedCall:
    """A call whose session took each event `late` seconds after it happened."""
    handed = tuple(event.at + late for event in events)
    return FedCall(
        started_at=START, events=tuple(events), commands=tuple(commands), handed_at=handed
    )


def _opened(at: float = 20.5) -> list[tuple[float, Command]]:
    return [(at, Send(message=Duck(level=0.25))), (at, HearOverlap(turn_id=0, window_ms=750))]


def test_a_stop_the_window_decided_is_timed_to_the_last_frame_before_the_echo() -> None:
    events = [
        TurnOpened(turn_id=0, at=20.5, speech_at=20.2),
        *_frames(20.6, 21.0),
        *_heard("window", 21.1, "made-up words"),
        *_frames(21.12, 21.14),
        *_heard("overlap", 21.4, "made-up words here"),
        TurnClosed(turn_id=0, at=22.0, speech_ended_at=21.2),
        ClauseQueued(reply_id=1, clause=0, at=22.3, requested_at=None),
        *_frames(22.32, 22.34),
    ]
    stop: list[tuple[float, Command]] = [(21.102, StopSpeaking(reply_id=0))]
    stop.append((21.102, Send(message=Unduck())))
    echo: list[tuple[float, Command]] = [
        (22.25, Speak(reply_id=1, clause=0, turn_id=0, text="echo", language="ar-SA"))
    ]
    fed = _fed(events, [*_opened(), *stop, *echo])
    replay = replay_of(fed, [_interrupted("new_words", "enough_words")], word_end_ms=1000.0)
    assert (replay.opened, replay.action, replay.kind, replay.reason, replay.decided_by) == (
        True,
        "stop",
        "new_words",
        "enough_words",
        "window",
    )
    assert (replay.overlap_turns, replay.decided_turn) == ((0,), 0)
    assert replay.last_audio_ms == pytest.approx(1140.0)
    assert replay.stop_ms == pytest.approx(140.0)
    assert replay.speech_stop_ms == pytest.approx(1200.0)
    window, whole = replay.requests
    assert (window.turn_id, window.part, whole.turn_id) == (0, "window", 0)
    assert (window.sent_ms, window.answered_ms) == pytest.approx((900.0, 1100.0))
    assert (whole.part, whole.text, whole.no_speech_prob, whole.failure) == (
        "overlap",
        "made-up words here",
        0.02,
        None,
    )


def test_a_reply_that_went_on_was_decided_by_the_whole_overlap() -> None:
    events = [
        TurnOpened(turn_id=0, at=20.5, speech_at=20.2),
        *_heard("window", 21.1, "made-up"),
        *_heard("overlap", 21.4, "made-up"),
        TurnClosed(turn_id=0, at=22.0, speech_ended_at=21.2),
        *_frames(21.5, 26.0),
    ]
    fed = _fed(events, [*_opened(), (21.402, Send(message=Unduck()))])
    replay = replay_of(fed, [_interrupted("false", "listening")], word_end_ms=900.0)
    assert (replay.action, replay.kind, replay.reason, replay.decided_by) == (
        "go_on",
        "false",
        "listening",
        "overlap",
    )
    assert (replay.last_audio_ms, replay.stop_ms) == (None, None)


def test_a_transcript_handed_while_the_session_decided_did_not_decide() -> None:
    """The overlap part's answer came before the stop's command, but its session took it only
    after: the window decided."""
    events = [
        TurnOpened(turn_id=0, at=20.5, speech_at=20.2),
        *_heard("window", 21.1, "made-up words"),
        *_heard("overlap", 21.105, "made-up words here"),
    ]
    late = (20.501, 20.901, 21.101, 21.2, 21.3)  # the overlap's answer taken at 21.3
    fed = FedCall(
        started_at=START,
        events=tuple(events),
        commands=(*_opened(), (21.12, StopSpeaking(reply_id=0))),
        handed_at=late,
    )
    replay = replay_of(fed, [_interrupted("new_words", "enough_words")])
    assert replay.decided_by == "window" and replay.stop_ms is None
    assert replay.speech_stop_ms is None  # its turn has not closed


def test_a_repeat_word_is_a_repeat() -> None:
    events = [TurnOpened(turn_id=0, at=20.5, speech_at=20.2), *_heard("overlap", 21.0, "made-up")]
    fed = _fed(events, [*_opened(), (21.01, StopSpeaking(reply_id=0))])
    replay = replay_of(fed, [_interrupted("new_words", "repeat_word")])
    assert (replay.action, replay.kind, replay.decided_by) == ("repeat", "new_words", "overlap")
    assert replay.last_audio_ms is None  # no frame was ever sent


def test_speech_after_a_go_on_stops_the_agent_on_the_turns_own_transcript() -> None:
    events = [
        TurnOpened(turn_id=0, at=20.5, speech_at=20.2),
        *_heard("overlap", 21.0, "made-up"),
        *_frames(21.5),
        *_heard("turn", 23.0, "made-up and then some"),
        *_frames(23.02),
    ]
    commands = [
        *_opened(),
        (21.01, Send(message=Unduck())),
        (23.01, StopSpeaking(reply_id=0)),
    ]
    heard = [_interrupted("false", "listening"), _interrupted("stop", "stop_word")]
    replay = replay_of(_fed(events, commands), heard)
    assert (replay.action, replay.reason, replay.decided_by) == ("stop", "stop_word", "turn")
    assert replay.last_audio_ms == pytest.approx(3020.0)


def test_a_clip_of_two_overlaps_names_each_requests_turn_and_the_one_that_decided() -> None:
    """A long clip opens one overlap that goes on, then another that stops the agent: four
    requests, two a turn, each carrying its turn, the second turn's whole overlap deciding."""
    events = [
        TurnOpened(turn_id=0, at=20.5, speech_at=20.2),
        *_heard("window", 21.1, "made-up"),
        *_heard("overlap", 21.4, "made-up"),
        TurnClosed(turn_id=0, at=22.0, speech_ended_at=21.2),
        TurnOpened(turn_id=1, at=23.5, speech_at=23.2),
        *_heard("window", 24.1, "made-up", turn=1),
        *_heard("overlap", 24.4, "made-up words here", turn=1),
        TurnClosed(turn_id=1, at=25.0, speech_ended_at=24.2),
    ]
    commands = [
        *_opened(),
        (21.402, Send(message=Unduck())),
        (23.5, Send(message=Duck(level=0.25))),
        (23.5, HearOverlap(turn_id=1, window_ms=750)),
        (24.402, StopSpeaking(reply_id=0)),
    ]
    heard = [_interrupted("false", "listening"), _interrupted("new_words", "enough_words")]
    replay = replay_of(_fed(events, commands), heard)
    assert (replay.overlap_turns, replay.action, replay.decided_by, replay.decided_turn) == (
        (0, 1),
        "stop",
        "overlap",
        1,
    )
    assert [(r.turn_id, r.part) for r in replay.requests] == [
        (0, "window"),
        (0, "overlap"),
        (1, "window"),
        (1, "overlap"),
    ]
    assert replay.speech_stop_ms == pytest.approx(4200.0)


def test_a_clip_that_opened_no_overlap_has_no_verdict() -> None:
    """Under `interruptions.mode = "drop"` no `HearOverlap` comes: the turn's own request is
    listed, and nothing decided; a call made by hand, with no handing times, reads its events'
    own."""
    events = [
        TurnOpened(turn_id=0, at=20.5, speech_at=20.2),
        TurnClosed(turn_id=0, at=21.5, speech_ended_at=21.2),
        *_heard("turn", 21.8, "made-up"),
    ]
    fed = FedCall(started_at=START, events=tuple(events), commands=())
    replay = replay_of(fed, [])
    (request,) = replay.requests
    assert replay.model_copy(update={"requests": ()}) == OverlapReplay(opened=False)
    assert (request.turn_id, request.part, request.text) == (0, "turn", "made-up")
    assert (request.sent_ms, request.answered_ms) == pytest.approx((1600.0, 1800.0))


def test_a_request_with_no_answer_and_a_failed_one() -> None:
    failed = Transcribed(
        turn_id=0,
        at=21.3,
        audio_s=0.75,
        sent_at=21.1,
        transcript=None,
        failure="rate_limited",
        retryable=True,
        part="window",
    )
    events: list[SessionEvent] = [
        Transcribing(turn_id=0, at=21.1, audio_s=0.75, part="window"),
        failed,
        Transcribing(turn_id=0, at=21.5, audio_s=1.0, part="overlap"),
    ]
    first, second = replay_of(_fed(events, _opened()), []).requests
    assert (first.failure, first.text, second.answered_ms) == ("rate_limited", None, None)


def test_a_replays_results_are_frozen() -> None:
    request = OverlapRequest(turn_id=0, part="window", sent_ms=1750.0, audio_s=0.75, text="made-up")
    replay = OverlapReplay(opened=True, action="stop", kind="stop", requests=(request,))
    with pytest.raises(ValidationError):
        replay.action = "go_on"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        OverlapRequest.model_validate(request.model_dump() | {"part": "middle"})
    assert (replay.decided_by, replay.stop_ms, OverlapReplay(opened=False).requests) == (
        None,
        None,
        (),
    )
