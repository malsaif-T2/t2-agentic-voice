"""The mock ticket system's page (ole5_voice/tickets/page.py), as the Ole5 app serves it
(ole5_voice/server.py): every ticket, newest first, with its number, type, priority, status,
summary and time; every value escaped; the widget's page headers with no framing and no cache;
no write route; only for a client on this machine; and its style from the widget's folder."""

from __future__ import annotations

from datetime import timedelta
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi import APIRouter
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from ole5_voice.server import WEB, build_app, page_headers
from ole5_voice.settings import AppSettings, Settings
from ole5_voice.tickets.mock import FILE_NAME, MockTicketSystem
from ole5_voice.tickets.page import COLUMNS, PAGE, REFRESH_S, STYLE, render, tickets_router
from pydantic import SecretStr
from t2_agentic_voice import Caller, Consent, VoiceSettings

from tests.ole5_voice.tickets.ticket_support import (
    MORNING,
    SUMMARY,
    Clock,
    mock,
    new_ticket,
    run,
)

HERE = ("127.0.0.1", 50000)
MARKUP = "<script>alert('x')</script> & \"quoted\" <b>bold</b>"
ARABIC = "التقرير فاضي"  # the report is empty
# Every tag the page may hold: no form, script, style, frame or link but its own two.
PAGE_TAGS = {
    "html", "head", "meta", "title", "link", "body", "header", "h1", "p", "main",
    "table", "thead", "tbody", "tr", "th", "td",
}  # fmt: skip


class _Minter:
    def mint(self, caller: Caller, *, consent: Consent) -> str:
        return "made-up-token"


class _Page(HTMLParser):
    """A page's tags with their attributes, the text of each cell by row, and whether it
    holds a script's text."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.rows: list[list[str]] = []
        self.heads: list[str] = []
        self._cell: list[str] | None = None
        self._head = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))
        if tag == "tr":
            self.rows.append([])
        if tag in ("td", "th"):
            self._cell, self._head = [], tag == "th"

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None:
            text = "".join(self._cell)
            (self.heads if self._head else self.rows[-1]).append(text)
            self._cell = None


def _parsed(html: str) -> _Page:
    page = _Page()
    page.feed(html)
    return page


def _settings(tmp_path: Path) -> Settings:
    app = AppSettings(access_code=SecretStr("made-up-access-code-0123"), tickets_dir=tmp_path)
    return Settings(app=app, voice=VoiceSettings(env="dev"))


@pytest.fixture
def tickets(tmp_path: Path) -> MockTicketSystem:
    return mock(tmp_path / "tickets")


def _client(tickets: MockTicketSystem, tmp_path: Path, peer: tuple[str, int] = HERE) -> TestClient:
    app = build_app(_settings(tmp_path), router=APIRouter(), minter=_Minter(), tickets=tickets)
    return TestClient(app, client=peer)


def test_the_page_lists_every_ticket_newest_first(tmp_path: Path) -> None:
    clock = Clock()
    tickets = mock(tmp_path / "tickets", clock)
    run(tickets.create(new_ticket("req-1")))
    clock.now = MORNING + timedelta(hours=2, minutes=5)
    run(tickets.create(new_ticket("req-2", type="Bug", priority="High", summary=ARABIC)))
    page = _client(tickets, tmp_path).get(PAGE)
    assert page.status_code == 200
    parsed = _parsed(page.text)
    assert parsed.heads == list(COLUMNS)
    assert parsed.rows[1:] == [
        ["2026111082000002", "Bug", "High", "New", ARABIC, "2026-11-10 11:35"],
        ["2026111082000001", "Inquiry", "Medium", "New", SUMMARY, "2026-11-10 09:30"],
    ]
    summaries = [a for tag, a in parsed.tags if tag == "td" and a.get("class") == "summary"]
    assert summaries and all(a.get("dir") == "auto" for a in summaries)


def test_with_no_ticket_the_page_says_so(tickets: MockTicketSystem, tmp_path: Path) -> None:
    page = _client(tickets, tmp_path).get(PAGE)
    assert page.status_code == 200
    assert "No tickets yet." in page.text and "<table" not in page.text
    assert not (tmp_path / "tickets").exists()  # reading it made nothing


def test_every_value_is_escaped(tickets: MockTicketSystem, tmp_path: Path) -> None:
    run(tickets.create(new_ticket(summary=MARKUP)))
    page = _client(tickets, tmp_path).get(PAGE).text
    assert MARKUP not in page and "<script" not in page and "<b>" not in page
    assert "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt; &amp; &quot;quoted&quot;" in page
    parsed = _parsed(page)
    assert parsed.rows[1][4] == MARKUP  # shown as the text it is
    assert {tag for tag, _ in parsed.tags} <= PAGE_TAGS


def test_the_page_has_the_widgets_headers_no_framing_no_cache_and_its_own_style(
    tickets: MockTicketSystem, tmp_path: Path
) -> None:
    client = _client(tickets, tmp_path)
    page = client.get(PAGE)
    assert page.headers["content-type"] == "text/html; charset=utf-8"
    assert page.headers["cache-control"] == "no-store"
    for name, value in page_headers(None).items():
        assert page.headers[name] == value
    assert page.headers["content-security-policy"].endswith("frame-ancestors 'none'")
    parsed = _parsed(page.text)
    links = [a for tag, a in parsed.tags if tag == "link"]
    assert links == [{"rel": "icon", "href": "data:,"}, {"rel": "stylesheet", "href": STYLE}]
    assert ("meta", {"http-equiv": "refresh", "content": str(REFRESH_S)}) in parsed.tags
    style = client.get(f"/{STYLE}")
    assert style.headers["content-type"] == "text/css; charset=utf-8"
    assert style.content == (WEB / STYLE).read_bytes()


def test_the_page_has_no_write_route(tickets: MockTicketSystem, tmp_path: Path) -> None:
    run(tickets.create(new_ticket()))
    before = (tmp_path / "tickets" / FILE_NAME).read_bytes()
    router = tickets_router(tickets, headers={})
    assert [(r.path, r.methods) for r in router.routes if isinstance(r, APIRoute)] == [
        (PAGE, {"GET"})
    ]
    client = _client(tickets, tmp_path)
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        answer = client.request(method, PAGE, json={"summary": "made up"})
        assert answer.status_code == 405, method
        assert client.request(method, f"{PAGE}/1").status_code in (404, 405)
    assert (tmp_path / "tickets" / FILE_NAME).read_bytes() == before


@pytest.mark.parametrize(
    ("peer", "status"),
    [
        ("127.0.0.1", 200),
        ("127.5.6.7", 200),
        ("::1", 200),
        ("::ffff:127.0.0.1", 200),
        ("192.168.1.20", 404),
        ("203.0.113.7", 404),
        ("::ffff:203.0.113.7", 404),
        ("testclient", 404),
    ],
)
def test_the_page_is_only_for_a_client_on_this_machine(
    tickets: MockTicketSystem, tmp_path: Path, peer: str, status: int
) -> None:
    run(tickets.create(new_ticket()))
    answer = _client(tickets, tmp_path, (peer, 50000)).get(PAGE)
    assert answer.status_code == status
    if status == 404:
        assert SUMMARY not in answer.text


def test_the_page_lists_whatever_the_modes(tickets: MockTicketSystem, tmp_path: Path) -> None:
    run(tickets.create(new_ticket()))
    tickets.mode = tickets.read_mode = "refuse"
    assert len(_parsed(_client(tickets, tmp_path).get(PAGE).text).rows) == 2


def test_the_app_serves_no_page_without_a_ticket_system(tmp_path: Path) -> None:
    app = build_app(_settings(tmp_path), router=APIRouter(), minter=_Minter())
    assert TestClient(app, client=HERE).get(PAGE).status_code == 404


def test_render_is_the_pages_text(tickets: MockTicketSystem) -> None:
    assert render(()) == render(tickets.listed())
    assert render(()).startswith("<!doctype html>")
