"""The opt-in live smoke run (flight_data/smoke.py), offline: refused in the main checkout and
without the key, sending nothing; on a made-up network it searches one day and one span of
three days and logs counts, statuses and wall seconds alone, never the key."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import httpx
import pytest
from flight_voice.flight_data.smoke import main
from t2_agentic_voice.evals import GitResult

from tests.flight_voice.flight_data.serpapi_support import KEY, body, content
from tests.leaks import holding, shown


class FakeGit:
    """git as a clean checkout at `top` describes it, `main` the main checkout."""

    def __init__(self, top: Path, main: Path) -> None:
        self.top, self.main = top, main

    def __call__(self, args: Sequence[str], cwd: Path) -> GitResult:
        if "--show-toplevel" in args:
            return GitResult(0, f"{self.top}\n")
        if args[:2] == ["worktree", "list"]:
            return GitResult(0, f"worktree {self.main}\0HEAD x\0\0worktree {self.top}\0HEAD x\0\0")
        if "HEAD" in args:
            return GitResult(0, "a" * 40 + "\n")
        return GitResult(0, "")  # status: clean


class Network:
    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.requests: list[httpx.Request] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, content=content(body()))


def _env(tmp_path: Path, key: str = KEY) -> Path:
    file = tmp_path / "smoke.env"
    file.write_bytes(f"FLIGHT_VOICE_SERPAPI_KEY={key}\n".encode())
    return file


def test_the_main_checkout_is_refused_and_nothing_sent(tmp_path: Path) -> None:
    network = Network()
    code = main(
        ["--env-file", str(_env(tmp_path))],
        folder=tmp_path,
        git=FakeGit(tmp_path, tmp_path),
        transport=httpx.MockTransport(network),
    )
    assert code == 2 and network.requests == []


def test_no_key_is_refused_and_nothing_sent(tmp_path: Path) -> None:
    network = Network()
    code = main(
        ["--env-file", str(_env(tmp_path, key=""))],
        folder=tmp_path,
        git=FakeGit(tmp_path / "tree", tmp_path / "main"),
        transport=httpx.MockTransport(network),
    )
    assert code == 2 and network.requests == []


@pytest.mark.parametrize(("status", "code"), [(200, 0), (503, 1)])
def test_a_day_and_a_span_are_searched_and_only_counts_logged(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    status: int,
    code: int,
) -> None:
    caplog.set_level("DEBUG")
    network = Network(status)
    assert (
        main(
            ["--env-file", str(_env(tmp_path))],
            folder=tmp_path,
            git=FakeGit(tmp_path / "tree", tmp_path / "main"),
            transport=httpx.MockTransport(network),
        )
        == code
    )
    engines = [r.url.params["engine"] for r in network.requests]
    assert "google_flights_calendar" in engines  # the span asks the calendar first
    days = {
        r.url.params["outbound_date"] for r in network.requests if "outbound_date" in r.url.params
    }
    # the day, and the span of three from it day by day (the calendar priced none), or the day
    # alone when the calendar failed
    assert len(days) == (3 if status == 200 else 1)
    assert holding(KEY, shown(caplog=caplog, capsys=capsys)) == []
    if status == 200:
        messages = [r.getMessage() for r in caplog.records]
        assert "smoke_day" in messages and "smoke_span" in messages
