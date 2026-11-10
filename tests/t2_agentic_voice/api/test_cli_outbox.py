"""`t2v outbox list`, `show` and `reconcile` (api/cli.py, api/actions.py; the design's 10.6;
docs/SECURITY.md, invariant 6): the rows of APP's agent's outbox, oldest first, of one state when
asked, and one row as JSON, each with its request ID, action, state, note and times and never
its draft, its result or the caller's subject (invariant 8); no outbox made by reading one;
`reconcile` looking the rows left sending and the flagged ones up again, never sending one, and
refused while a server holds the folder's lock; the logs on the standard error, the report on
the standard output; and a refusal naming no value."""

from __future__ import annotations

import asyncio
import json
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, get_args

import pytest
from t2_agentic_voice.actions.memory_outbox import MemoryOutbox
from t2_agentic_voice.adapters.outbox import SqliteOutbox
from t2_agentic_voice.api.actions import outbox_path
from t2_agentic_voice.api.cli import OUTBOX_STATES, main
from t2_agentic_voice.api.lockfile import LockFile
from t2_agentic_voice.api.runtime import VoiceRuntime
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.outbox import OutboxEntry, OutboxState

from tests.t2_agentic_voice.actions.action_support import Backend, RequestOpened, an_action
from tests.t2_agentic_voice.api.runtime_support import dev_settings
from tests.t2_agentic_voice.fakes import FakeClock

APP = "zx_outbox_app:make_runtime"
SUBJECT = "made-up-subject-4471"
SUMMARY = "made-up summary 5309 of the laptop"
NUMBER = "2026111082000123"
START = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


def _row(n: int, state: OutboxState, note: str | None, result: str | None = None) -> OutboxEntry:
    values: dict[str, Any] = {
        "request_id": f"r-{n}",
        "call_id": f"call-{n}",
        "subject": SUBJECT,
        "action": "open_request",
        "draft_json": json.dumps({"category": "software", "summary": SUMMARY}),
        "state": state,
        "note": note,
        "result_json": result,
        "created_at": START + timedelta(minutes=n),
        "updated_at": START + timedelta(minutes=n, seconds=5),
    }
    return OutboxEntry.model_validate(values)


ROWS = (
    _row(1, "done", None, json.dumps({"number": NUMBER})),
    _row(2, "flagged", "timed_out, not_found"),
    _row(3, "sending", None),
)


class _App:
    """APP's runtime, its agent's action over a made-up backend, its outbox under the test's
    own folder."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.settings = dev_settings(tmp_path)
        self.backend = Backend(outbox=MemoryOutbox(), clock=FakeClock())
        self.agent = VoiceAgent(
            name="acting",
            languages=[Language.english(greeting="Hello.")],
            tools=[an_action(self.backend)],
        )
        runtime = VoiceRuntime(self.agent, settings=self.settings)
        module = types.ModuleType("zx_outbox_app")
        module.make_runtime = lambda: runtime  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "zx_outbox_app", module)
        monkeypatch.setattr(sys, "path", list(sys.path))
        self.path = outbox_path(self.settings, self.agent)

    def write(self, *rows: OutboxEntry) -> None:
        async def written() -> None:
            store = await SqliteOutbox.open(self.path)
            for row in rows:
                await store.add(row)
            await store.aclose()

        asyncio.run(written())

    def rows(self) -> dict[str, OutboxEntry]:
        async def read() -> tuple[OutboxEntry, ...]:
            store = await SqliteOutbox.open(self.path)
            try:
                return await store.entries()
            finally:
                await store.aclose()

        return {row.request_id: row for row in asyncio.run(read())}


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _App:
    return _App(tmp_path, monkeypatch)


def _no_content(out: str) -> None:
    for value in (SUBJECT, SUMMARY, "5309", NUMBER, "draft_json", "result_json"):
        assert value not in out, value


def test_the_states_are_the_outboxs() -> None:
    assert get_args(OutboxState) == OUTBOX_STATES


def test_list_prints_each_row_oldest_first_and_never_its_content(
    app: _App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.write(*ROWS)
    assert main(["outbox", "list", APP]) == 0
    shown = capsys.readouterr()
    lines = shown.out.splitlines()
    assert lines[0].split() == ["request_id", "action", "state", "created_at", "updated_at", "note"]
    assert [line.split()[:3] for line in lines[1:]] == [
        ["r-1", "open_request", "done"],
        ["r-2", "open_request", "flagged"],
        ["r-3", "open_request", "sending"],
    ]
    assert "2026-11-10T09:02:00+00:00" in lines[2] and lines[2].endswith("timed_out, not_found")
    _no_content(shown.out + shown.err)


def test_list_prints_the_rows_of_one_state_when_asked(
    app: _App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.write(*ROWS)
    assert main(["outbox", "list", APP, "--state", "flagged"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[0] for line in lines[1:]] == ["r-2"]


def test_list_of_an_outbox_not_made_yet_says_so_and_makes_none(
    app: _App, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["outbox", "list", APP]) == 0
    assert capsys.readouterr().out == "no rows\n"
    assert not app.path.exists()


def test_show_prints_one_row_as_json_never_its_content(
    app: _App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.write(*ROWS)
    assert main(["outbox", "show", APP, "r-1"]) == 0
    shown = capsys.readouterr()
    assert json.loads(shown.out) == {
        "request_id": "r-1",
        "call_id": "call-1",
        "action": "open_request",
        "state": "done",
        "note": None,
        "created_at": "2026-11-10T09:01:00+00:00",
        "updated_at": "2026-11-10T09:01:05+00:00",
        "holds_result": True,
    }
    _no_content(shown.out + shown.err)


def test_show_of_a_row_the_outbox_does_not_hold_is_refused_naming_no_value(
    app: _App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.write(*ROWS)
    assert main(["outbox", "show", APP, "zx-missing-7"]) == 1
    shown = capsys.readouterr()
    assert shown.out == "" and "FIX:" in shown.err and "zx-missing-7" not in shown.err


def test_reconcile_looks_the_rows_up_again_and_never_sends_one(
    app: _App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.write(*ROWS)
    app.backend.held["r-2"] = RequestOpened(number=NUMBER)  # the system had done it
    assert main(["outbox", "reconcile", APP]) == 0
    shown = capsys.readouterr()
    assert shown.out == "2 rows looked up; 1 flagged rows wait for a person\n"
    rows = app.rows()
    assert (rows["r-2"].state, rows["r-2"].note) == ("done", "looked_up")
    assert (rows["r-3"].state, rows["r-3"].note) == ("flagged", "left, not_found")
    assert rows["r-1"] == ROWS[0]
    assert app.backend.writes == [] and sorted(app.backend.lookups) == ["r-2", "r-3"]
    _no_content(shown.out + shown.err)


def test_reconcile_is_refused_while_a_server_holds_the_folders_lock(
    app: _App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.write(*ROWS)
    lock = LockFile.take(app.settings.storage.var_dir)
    try:
        assert main(["outbox", "reconcile", APP]) == 1
    finally:
        lock.release()
    shown = capsys.readouterr()
    assert "lock" in shown.err and "FIX:" in shown.err and "looked up" not in shown.out
    assert app.rows()["r-3"].state == "sending" and app.backend.lookups == []
