"""The test console (api/dev_console.py, D-083): its feed keeps the runtime's events in memory,
bounded by calls and records, and answers a page's long poll at once, on a new record, or when
its wait ends; its routes come with the dev page alone and answer only a loopback client that
names a loopback host, under `env` dev; its setup holds no secret; and its page holds no script
or style of its own, every id its script reads among the page's."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from t2_agentic_voice.api import dev_console
from t2_agentic_voice.api.dev_console import DevFeed, FeedQuery, loopback_host, setup_of
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import (
    CallStarted,
    Event,
    ToolFinished,
    ToolStarted,
    UserTurnEnded,
)
from t2_agentic_voice.core.settings.groq import GroqSettings
from t2_agentic_voice.core.settings.server import ServerSettings

from tests.leaks import holding, shown
from tests.t2_agentic_voice.api.runtime_support import (
    AGENT,
    LOOPBACK,
    PREFIX,
    Harness,
    dev_settings,
)

pytestmark = pytest.mark.usefixtures("patched_stores")

AT = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
STATIC = Path(dev_console.__file__).parent / "static"
LOCAL = "http://127.0.0.1:7860"
HEARD_AR = "ابغى افتح تذكرة"  # what a caller said: call content


def _started(call_id: str) -> CallStarted:
    return CallStarted(call_id=call_id, at=AT)


def _heard(call_id: str, turn_id: int, heard: str = "hello") -> UserTurnEnded:
    return UserTurnEnded(call_id=call_id, turn_id=turn_id, at=AT, heard=heard)


def test_the_feed_numbers_each_record_and_keeps_the_event_whole() -> None:
    feed = DevFeed()
    feed.add(_started("c-1"))
    tool = ToolFinished(
        call_id="c-1",
        turn_id=0,
        at=AT,
        tool="search",
        tool_call_id="t-1",
        arguments='{"query": "reset"}',
        ok=True,
        ms=12.5,
        result='{"passages": []}',
    )
    feed.add(tool)
    first, second = feed.after(0)
    assert (first["seq"], first["type"], first["call_id"]) == (1, "CallStarted", "c-1")
    assert second["seq"] == 2 == feed.last
    assert second["event"] == json.loads(tool.model_dump_json())
    assert feed.after(1) == [second]
    assert feed.after(2) == []


def test_a_number_past_the_newest_is_an_earlier_feeds_and_gets_every_record() -> None:
    feed = DevFeed()
    feed.add(_started("c-1"))
    assert [record["seq"] for record in feed.after(99)] == [1]
    assert DevFeed().name != feed.name


def test_the_feed_keeps_the_newest_calls_and_records_alone() -> None:
    feed = DevFeed(calls=2, records=5)
    for call in ("c-1", "c-2", "c-3"):
        feed.add(_started(call))
        feed.add(_heard(call, 0))
    assert {record["call_id"] for record in feed.after(0)} == {"c-2", "c-3"}
    for turn in range(1, 4):
        feed.add(_heard("c-3", turn))
    records = feed.after(0)
    assert len(records) == 5
    assert [record["seq"] for record in records] == list(range(feed.last - 4, feed.last + 1))


def test_a_poll_answers_at_once_on_a_new_record_or_when_its_wait_ends() -> None:
    feed = DevFeed()

    async def scene() -> None:
        assert await feed.wait_after(0, wait_s=0.01) == []
        waiting = asyncio.create_task(feed.wait_after(0, wait_s=5.0))
        await asyncio.sleep(0.01)
        assert not waiting.done()
        await feed.observe(_started("c-1"))
        records = await asyncio.wait_for(waiting, 1.0)
        assert [record["type"] for record in records] == ["CallStarted"]
        assert await feed.wait_after(0, wait_s=5.0) == records  # at once

    asyncio.run(scene())


def _aged(folder: Path, *names: str) -> None:
    """Give the call files `names` mtimes in that order, oldest first."""
    for age, name in enumerate(reversed(names)):
        stamp = 1_800_000_000 - 60 * age
        os.utime(folder / f"{name}.jsonl", (stamp, stamp))


def test_each_event_is_saved_in_its_calls_file_and_a_new_feed_reads_them_back(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    folder = tmp_path / "dev-console"
    feed = DevFeed(folder=folder)

    async def observed() -> None:
        for event in (_started("c-1"), _heard("c-1", 0, HEARD_AR), _started("c-2")):
            await feed.observe(event)

    asyncio.run(observed())
    assert sorted(path.name for path in folder.iterdir()) == ["c-1.jsonl", "c-2.jsonl"]
    lines = (folder / "c-1.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["type"] for line in lines] == ["CallStarted", "UserTurnEnded"]
    assert HEARD_AR in lines[1]  # as said, not escaped
    _aged(folder, "c-1", "c-2")
    again = DevFeed(folder=folder)
    records = asyncio.run(again.wait_after(0, wait_s=0))
    assert [(r["call_id"], r["type"]) for r in records] == [
        ("c-1", "CallStarted"),
        ("c-1", "UserTurnEnded"),
        ("c-2", "CallStarted"),
    ]
    assert [r["event"] for r in records] == [r["event"] for r in feed.after(0)]
    assert [r["seq"] for r in records] == [1, 2, 3] and again.name != feed.name
    asyncio.run(again.observe(_heard("c-2", 0)))  # read once: the saved calls are not doubled
    assert [r["seq"] for r in again.after(0)] == [1, 2, 3, 4]
    assert holding(HEARD_AR, shown(caplog=caplog)) == []  # saved and read, never logged


def test_a_new_feed_reads_the_newest_calls_alone_and_skips_lines_that_are_no_event(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "dev-console"
    feed = DevFeed(folder=folder)
    for call in ("c-1", "c-2", "c-3"):
        asyncio.run(feed.observe(_started(call)))
    with (folder / "c-3.jsonl").open("a", encoding="utf-8", newline="\n") as file:
        file.write("not json\n")
        file.write(json.dumps({"type": "Unknown", "event": {}}) + "\n")
        file.write(json.dumps({"type": "UserTurnEnded", "event": {"call_id": "c-3"}}) + "\n")
        file.write("\n")
    asyncio.run(feed.observe(_heard("c-3", 0)))
    _aged(folder, "c-1", "c-2", "c-3")
    again = DevFeed(folder=folder, calls=2)
    records = asyncio.run(again.wait_after(0, wait_s=0))
    assert [(r["call_id"], r["type"]) for r in records] == [
        ("c-2", "CallStarted"),
        ("c-3", "CallStarted"),
        ("c-3", "UserTurnEnded"),
    ]


def test_a_file_that_cannot_be_written_is_logged_by_its_kind_and_the_event_kept(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    blocked = tmp_path / "dev-console"
    blocked.write_text("a file where the folder would be", encoding="utf-8")
    feed = DevFeed(folder=blocked)
    asyncio.run(feed.observe(_heard("c-1", 0, HEARD_AR)))
    assert [r["type"] for r in feed.after(0)] == ["UserTurnEnded"]
    assert "dev_console_not_saved" in caplog.text
    assert holding(HEARD_AR, shown(caplog=caplog)) == []


def test_a_runtimes_feed_saves_under_its_data_folder(tmp_path: Path) -> None:
    harness, app = _app(tmp_path)
    folder = harness.settings.storage.var_dir / dev_console.CONSOLE_FOLDER

    async def scene() -> None:
        async with _serving(app):
            _emit(harness, _started("c-9"))
            for _ in range(100):  # the observers run off the call's path
                if (folder / "c-9.jsonl").exists():
                    break
                await asyncio.sleep(0.02)

    asyncio.run(scene())
    assert [path.name for path in folder.iterdir()] == ["c-9.jsonl"]
    _, restarted = _app(tmp_path)

    async def after_restart() -> list[str]:
        async with _serving(restarted) as http:
            answer = await http.get(PREFIX + "/dev/feed", params={"wait": 0})
        return [record["call_id"] for record in answer.json()["records"]]

    assert asyncio.run(after_restart()) == ["c-9"]


@pytest.mark.parametrize(
    ("host", "local"),
    [
        ("127.0.0.1", True),
        ("127.0.0.1:7860", True),
        ("localhost", True),
        ("LOCALHOST:7861", True),
        ("[::1]:7860", True),
        ("[::1]", True),
        ("t2v.test", False),
        ("evil.example:7860", False),
        ("127.0.0.1.nip.io", False),
        ("localhost.evil.example", False),
        ("[::ffff:10.0.0.1]", False),
        ("", False),
        (None, False),
    ],
)
def test_a_loopback_host_names_this_machine_alone(host: str | None, local: bool) -> None:
    assert loopback_host(host) is local


def test_the_feed_query_is_parsed_strictly() -> None:
    assert FeedQuery.model_validate({"after": "3", "wait": "0"}) == FeedQuery(after=3, wait=0)
    for bad in ({"after": "-1"}, {"wait": "11"}, {"after": "x"}, {"other": "1"}):
        with pytest.raises(ValueError):
            FeedQuery.model_validate(bad)


def test_the_setup_holds_no_secret_and_names_what_shapes_a_turn() -> None:
    secret = "gsk_made_up_secret_value_0123456789"
    settings = VoiceSettings(env="dev", groq=GroqSettings(api_key=SecretStr(secret)))
    setup = setup_of(AGENT, settings)
    text = json.dumps(setup)
    assert secret not in text
    assert setup["agent"] == AGENT.name and setup["env"] == "dev"
    assert set(setup["settings"]) == set(dev_console.SETUP_GROUPS)  # type: ignore[arg-type]
    assert setup["settings"]["turns"]["vad_stop_ms"] == settings.turns.vad_stop_ms  # type: ignore[index,call-overload]
    for group in dev_console.SETUP_GROUPS:
        fields = type(getattr(settings, group)).model_fields.values()
        assert all("SecretStr" not in str(info.annotation) for info in fields), group


def _app(tmp_path: Path, *, dev: bool = False, dev_page: bool = True) -> tuple[Harness, FastAPI]:
    settings = dev_settings(tmp_path, server=ServerSettings(dev_page=dev_page))
    harness = Harness(settings)
    return harness, harness.app(dev=dev)


@asynccontextmanager
async def _serving(
    app: FastAPI, *, peer: tuple[str, int] = LOOPBACK, base: str = LOCAL
) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, client=peer)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url=base) as http,
    ):
        yield http


def _emit(harness: Harness, event: Event) -> None:
    harness.built[0]["emit"](event)


def test_the_console_shows_the_runtimes_events_to_a_long_poll(tmp_path: Path) -> None:
    harness, app = _app(tmp_path)

    async def scene() -> None:
        async with _serving(app) as http:
            waiting = asyncio.create_task(http.get(PREFIX + "/dev/feed", params={"after": 0}))
            await asyncio.sleep(0.05)
            _emit(harness, _started("c-1"))
            _emit(harness, ToolStarted(call_id="c-1", turn_id=0, at=AT, tool="s", tool_call_id="t"))
            first = (await asyncio.wait_for(waiting, 5.0)).json()
            await asyncio.sleep(0.05)
            rest = await http.get(PREFIX + "/dev/feed", params={"after": 0, "wait": 0})
            setup = await http.get(PREFIX + "/dev/setup")
        assert first["records"][0]["type"] == "CallStarted"
        types = [record["type"] for record in rest.json()["records"]]
        assert types == ["CallStarted", "ToolStarted"]
        assert rest.json()["last"] == 2 and rest.json()["feed"] == first["feed"]
        assert rest.headers["cache-control"] == "no-store"
        assert setup.json()["agent"] == AGENT.name

    asyncio.run(scene())


@pytest.mark.parametrize(
    "path", ["/dev/console", "/dev/console.js", "/dev/console.css", "/dev/setup", "/dev/feed"]
)
@pytest.mark.parametrize(
    ("peer", "base", "dev_page", "served"),
    [
        ("127.0.0.1", LOCAL, True, True),
        ("::1", "http://localhost:7860", True, True),
        ("192.0.2.7", LOCAL, True, False),  # not this machine
        ("127.0.0.1", "http://t2v.test", True, False),  # a name pointed at this machine
        ("127.0.0.1", LOCAL, False, False),  # no dev page: not mounted
    ],
)
def test_the_console_answers_this_machine_by_a_loopback_name_alone(
    path: str, peer: str, base: str, dev_page: bool, served: bool, tmp_path: Path
) -> None:
    _, app = _app(tmp_path, dev_page=dev_page)

    async def scene() -> None:
        async with _serving(app, peer=(peer, 50000), base=base) as http:
            answer = await http.get(PREFIX + path, params={"wait": 0} if "feed" in path else None)
        if not served:
            assert (answer.status_code, answer.json()) == (404, {"detail": "Not Found"})
            return
        assert answer.status_code == 200
        assert answer.headers["x-content-type-options"] == "nosniff"
        assert answer.headers["cache-control"] == "no-store"

    asyncio.run(scene())


def test_the_console_page_has_its_policy_and_t2v_dev_mounts_it(tmp_path: Path) -> None:
    _, app = _app(tmp_path, dev=True, dev_page=False)

    async def scene() -> None:
        async with _serving(app) as http:
            page = await http.get(PREFIX + "/dev/console")
            bad = await http.get(PREFIX + "/dev/feed", params={"after": "-1"})
        assert page.headers["content-type"] == "text/html; charset=utf-8"
        policy = page.headers["content-security-policy"]
        assert "script-src 'self'" in policy and "frame-ancestors 'none'" in policy
        assert "unsafe" not in policy
        assert (bad.status_code, bad.json()["code"]) == (400, "invalid_request")

    asyncio.run(scene())


def test_the_feed_is_no_observer_without_the_dev_page(tmp_path: Path) -> None:
    harness, _ = _app(tmp_path, dev_page=False)
    assert harness.runtime._observers == []
    harness, _ = _app(tmp_path, dev=True, dev_page=False)
    assert [kind for kind, _ in harness.runtime._observers] == [Event]


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.inline: list[str] = []
        self._in: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))
        self._in = tag

    def handle_data(self, data: str) -> None:
        if self._in in ("script", "style") and data.strip():
            self.inline.append(data)

    def handle_endtag(self, tag: str) -> None:
        self._in = None


def test_the_console_page_holds_no_script_or_style_of_its_own() -> None:
    page = _Page()
    page.feed((STATIC / dev_console.PAGE).read_text(encoding="utf-8"))
    attrs: list[dict[str, Any]] = [a for _, a in page.tags]
    assert page.inline == []
    assert [a for t, a in page.tags if t == "script"] == [{"type": "module", "src": "console.js"}]
    assert all(t != "style" and "style" not in a for t, a in page.tags)
    assert all(not name.startswith("on") for a in attrs for name in a)
    script = (STATIC / dev_console.SCRIPT).read_text(encoding="utf-8")
    read = set(re.findall(r'\$\("([a-z-]+)"\)', script))
    ids = {a["id"] for a in attrs if a.get("id")}
    assert read and read <= ids
    assert 'from "../client/1/t2v-client.js"' in script
