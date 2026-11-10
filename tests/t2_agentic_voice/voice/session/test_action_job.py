"""A confirmed action's write and its outcome (voice/session/action_job.py; plan 007, Track C;
docs/SECURITY.md, invariant 6): a write that definitely failed or whose end is unknown is
reported `ActionUnconfirmed` of that kind, never `ActionCompleted`, its own line still said once
at a turn boundary; and a job that raises (a bug: a failed write is an outcome) is logged by its
kind alone and told as the `error` notice, never as done. The yes rule and the port are the
tests' fakes (yes_support.py)."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import ActionCompleted, ActionUnconfirmed
from t2_agentic_voice.domain.ports.action_jobs import OutcomeKind
from t2_agentic_voice.domain.text.invisible import provider_text
from t2_agentic_voice.voice.protocol import Notice

from tests.leaks import holding, shown
from tests.t2_agentic_voice.voice.session.read_back_support import ACTION
from tests.t2_agentic_voice.voice.session.session_support import emitted, sent, speaks
from tests.t2_agentic_voice.voice.session.talker_support import talked
from tests.t2_agentic_voice.voice.session.yes_support import (
    OUTCOME,
    REQUEST_ID,
    FakeJobs,
    FakeYesRule,
    confirm_call,
    play_reply,
    read_back_played,
)

YES = "made-up-yes"


@pytest.mark.parametrize("kind", ["failed", "unknown"])
def test_a_write_not_done_is_reported_unconfirmed_and_its_own_line_said_once(
    settings: VoiceSettings, yes_rule: FakeYesRule, kind: OutcomeKind
) -> None:
    jobs = FakeJobs(kind=kind)
    io, _, _ = confirm_call(settings, jobs)

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, YES)
        await play_reply(io, 2)
        await play_reply(io, 3)

    asyncio.run(drive())
    assert emitted(io, ActionCompleted) == []
    (unconfirmed,) = emitted(io, ActionUnconfirmed)
    assert (unconfirmed.action, unconfirmed.request_id, unconfirmed.kind) == (
        ACTION,
        REQUEST_ID,
        kind,
    )
    said = [speak.text for speak in speaks(io)]
    assert said.count(provider_text(OUTCOME.spoken)) == 1


def test_a_job_that_raises_is_told_as_the_error_notice_and_logged_by_its_kind(
    settings: VoiceSettings, yes_rule: FakeYesRule, caplog: pytest.LogCaptureFixture
) -> None:
    jobs = FakeJobs(error=RuntimeError("made-up runner failure"))
    io, _, _ = confirm_call(settings, jobs)

    async def drive() -> None:
        await read_back_played(io)
        await talked(io, 1, YES)
        assert sent(io, Notice) == []  # not over the sending line
        await play_reply(io, 2)

    asyncio.run(drive())
    assert [notice.kind for notice in sent(io, Notice)] == ["error"]
    assert emitted(io, ActionCompleted) == [] and emitted(io, ActionUnconfirmed) == []
    assert all(speak.text != provider_text(OUTCOME.spoken) for speak in speaks(io))
    failed = [r for r in caplog.records if r.getMessage() == "action_job_failed"]
    assert len(failed) == 1
    assert holding("made-up runner failure", shown(caplog=caplog)) == []  # GP-19
