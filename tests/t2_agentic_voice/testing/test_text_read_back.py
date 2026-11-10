"""Where a text call's read-backs play (testing/text_read_back.py; plan 007, Track D), read from a
real `Playback` against the plans the talker asked for: a read-back said in one clause each, or
cut into clauses captioned as said; a corrected draft's reading told from the first's; a
summary that played whole, or was cut short, said with no audio or failed, and one whose reply a
stop cut over the closing question, which still played whole; and the runtime's own lines told
from the talker's."""

from __future__ import annotations

from t2_agentic_voice.testing.text_read_back import (
    fold,
    is_template,
    part_at,
    playing,
    readings,
    summary_played_at,
    templates,
)
from t2_agentic_voice.voice.session.commands import Speak
from t2_agentic_voice.voice.session.echo import Line
from t2_agentic_voice.voice.session.playback import Playback, Reply
from t2_agentic_voice.voice.session.session_events import ClauseFailed, ClausePlayed, ClauseQueued

from tests.t2_agentic_voice.testing.action_support import VISIT, Visit, line, plan_of


def _said(playback: Playback, captions: list[str], *, turn_id: int = 0) -> Reply:
    reply = playback.open("answer", turn_id=turn_id)
    for caption in captions:
        speak = Speak(
            reply_id=reply.reply_id,
            clause=len(reply.clauses),
            turn_id=turn_id,
            text=caption,
            language="en",
        )
        playback.add(reply, Line(speak=speak, caption=caption))
    return reply


def _play(playback: Playback, reply: Reply, index: int, at: float, **ended: object) -> None:
    playback.queued(ClauseQueued(reply_id=reply.reply_id, clause=index, at=at, requested_at=at))
    played = {"audio_s": 1.0, "chunks": 1} | ended
    playback.done(ClausePlayed(reply_id=reply.reply_id, clause=index, at=at + 1.0, **played))  # type: ignore[arg-type]


def test_a_read_back_said_in_one_clause_each_is_found_and_its_parts_told() -> None:
    plan = plan_of()
    playback = Playback()
    hello = _said(playback, ["Hello."], turn_id=0)
    _play(playback, hello, 0, 0.0)
    playback.close(hello, 1.0)
    reply = _said(playback, ["Sure.", plan.summary.text, plan.question.text, "Bye."], turn_id=1)
    (reading,) = readings(playback, [plan])
    assert (reading.reply_id, reading.summary, reading.question) == (reply.reply_id, (1,), (2,))
    assert part_at([reading], reply.reply_id, 1) == "summary"
    assert part_at([reading], reply.reply_id, 2) == "question"
    assert part_at([reading], reply.reply_id, 3) is None and part_at([reading], 0, 1) is None
    assert playing(playback, [plan]) is None  # nothing queued yet
    playback.queued(ClauseQueued(reply_id=reply.reply_id, clause=0, at=0.0, requested_at=0.0))
    playback.done(ClausePlayed(reply_id=reply.reply_id, clause=0, at=1.0, audio_s=1.0, chunks=1))
    playback.queued(ClauseQueued(reply_id=reply.reply_id, clause=1, at=1.0, requested_at=1.0))
    assert playing(playback, [plan]) == "summary"


def test_a_summary_cut_into_clauses_captioned_as_said_is_one_reading() -> None:
    plan = plan_of()
    as_said = ["I'll book room R two zero four", "for: the projector is broken."]
    playback = Playback()
    _said(playback, [*as_said, plan.question.text])
    (reading,) = readings(playback, [plan])
    assert (reading.summary, reading.question) == ((0, 1), (2,))
    assert readings(playback, []) == ()


def test_a_corrected_drafts_reading_is_told_from_the_firsts() -> None:
    first = plan_of()
    second = plan_of(Visit(room="R-204", note="the screen is broken"), call_id="t-2")
    playback = Playback()
    old = _said(playback, [first.summary.text, first.question.text])
    new = _said(playback, [second.summary.text, second.question.text])
    found = readings(playback, [first, second])
    assert [(r.reply_id, r.plan.tool_call_id) for r in found] == [
        (old.reply_id, "t-1"),
        (new.reply_id, "t-2"),
    ]


def test_a_summary_played_whole_says_when_and_any_fault_says_none() -> None:
    plan = plan_of()
    faults: list[dict[str, object]] = [{"cut_short": True}, {"audio_s": 0.0, "chunks": 0}]
    for fault in [{}, *faults]:
        playback = Playback()
        reply = _said(playback, [plan.summary.text, plan.question.text])
        (reading,) = readings(playback, [plan])
        assert summary_played_at(playback, reading) is None  # still to play
        _play(playback, reply, 0, 2.0, **fault)
        assert summary_played_at(playback, reading) == (None if fault else 3.0)
    playback = Playback()
    reply = _said(playback, [plan.summary.text, plan.question.text])
    (reading,) = readings(playback, [plan])
    playback.queued(ClauseQueued(reply_id=reply.reply_id, clause=0, at=0.0, requested_at=0.0))
    failed = ClauseFailed(
        reply_id=reply.reply_id, clause=0, at=1.0, failure="server_error", retryable=True
    )
    playback.done(failed)
    assert summary_played_at(playback, reading) is None
    playback = Playback()
    reply = _said(playback, [plan.summary.text, plan.question.text])
    (reading,) = readings(playback, [plan])
    _play(playback, reply, 0, 0.0)
    reply.stopped = True  # a stop over the closing question, the summary played whole
    assert summary_played_at(playback, reading) == 1.0


def test_the_runtimes_own_lines_are_told_from_the_talkers() -> None:
    plan = plan_of()
    own = templates([plan], [(line("Done, number 5101."), "en")])
    for text in (plan.summary.text, "for: the projector is broken.", plan.sending.text):
        assert is_template(text, own), text
    assert is_template("Done, number 5101.", own)
    assert not is_template("Your visit is booked, number 5101.", own)
    assert not is_template("...", own)  # nothing to compare
    assert fold(" R-204, OK! ") == "r204ok"
    assert VISIT.room in plan.summary.text
