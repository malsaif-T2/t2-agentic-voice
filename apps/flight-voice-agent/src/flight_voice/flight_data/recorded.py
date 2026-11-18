"""SerpApi's answers recorded and replayed at the wire, so a replay runs through the real
adapter and its parser: tests and the app's recorded mode answer offline.

A fixture is one answer in an envelope, `{"params": {...}, "status": 200, "body": {...}}`, its
params the request's as the adapter sends them, the key left out. `fixture_name(params)` names
it by the airports (commas made "+"), the day, the class and the travelers
(`RUH_JED_2026-11-19_c1_a1.json`); a fare calendar by its range in place of the day
(`RUH_JED_calendar_2026-11-19_2027-01-15_c1_a1.json`).

- `ReplayTransport(folder)` answers a request from the fixture whose params equal the
  request's, the key aside; every `*.json` of the folder is read once, at the start. A request
  no fixture holds gets a 404 marked not recorded, which the adapter reads as `not_recorded`
  (no retry, not lasting), logged as `flight_data_not_recorded`. A missing folder is one WARNING
  at the start, then every search is not recorded.
- `RecordingTransport(folder, inner)` passes each request on and writes each 200 answer as a
  fixture; it refuses to write one whose text holds the key.
- `recorded(folder)` is the adapter over a replay, named "recorded".

`APP_FIXTURES` is the app's recorded mode's folder, found from the package as the server finds
its page, never from the working directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

import httpx
from pydantic import SecretStr
from t2_agentic_voice import get_logger

from flight_voice.flight_data.serpapi import NOT_RECORDED_HEADER, SerpApiFlightData
from flight_voice.flight_data.serpapi_params import CALENDAR_ENGINE

__all__ = [
    "APP_FIXTURES",
    "RecordingTransport",
    "ReplayTransport",
    "envelope",
    "fixture_name",
    "recorded",
]

log = get_logger(__name__)

APP_FIXTURES: Final = Path(__file__).resolve().parents[3] / "evals" / "flight_data"
_KEY: Final = "api_key"
_DROPPED: Final = frozenset({"content-encoding", "content-length", "transfer-encoding"})


def _params(request: httpx.Request) -> dict[str, str]:
    return {k: v for k, v in request.url.params.items() if k != _KEY}


def fixture_name(params: dict[str, str]) -> str:
    """The fixture's file name for these params; a fare calendar's names its range."""
    route = "_".join(params.get(k, "").replace(",", "+") for k in ("departure_id", "arrival_id"))
    day = params.get("outbound_date", "")
    if params.get("engine") == CALENDAR_ENGINE:
        first, last = params.get("date_range_start", ""), params.get("date_range_end", "")
        day = f"calendar_{first}_{last}"
    return f"{route}_{day}_c{params.get('travel_class', '')}_a{params.get('adults', '')}.json"


def envelope(params: dict[str, str], status: int, body: object) -> dict[str, Any]:
    """A fixture's content: the params (the key left out), the status and the body."""
    kept = {k: str(v) for k, v in params.items() if k != _KEY}
    return {"params": kept, "status": status, "body": body}


def _match(params: dict[str, str]) -> frozenset[tuple[str, str]]:
    return frozenset((k, str(v)) for k, v in params.items() if k != _KEY)


class ReplayTransport(httpx.AsyncBaseTransport):
    """Answers from the fixtures in `folder` (the module's docstring)."""

    def __init__(self, folder: Path) -> None:
        self._held: dict[frozenset[tuple[str, str]], tuple[int, bytes]] = {}
        if not folder.is_dir():
            log.warning("flight_data_fixtures_missing", folder=folder.name)
            return
        for file in sorted(folder.glob("*.json")):
            try:
                held = json.loads(file.read_text(encoding="utf-8"))
                key = _match(held["params"])
                answer = (int(held["status"]), json.dumps(held["body"]).encode("utf-8"))
            except (ValueError, KeyError, TypeError, AttributeError):
                log.warning("flight_data_fixture_unreadable", fixture=file.name)
                continue
            self._held[key] = answer

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        params = _params(request)
        held = self._held.get(_match(params)) if request.url.path == "/search" else None
        if held is None:
            log.info("flight_data_not_recorded", fixture=fixture_name(params))
            return httpx.Response(404, headers={NOT_RECORDED_HEADER: "1"}, request=request)
        status, body = held
        headers = {"content-type": "application/json"}
        return httpx.Response(status, headers=headers, content=body, request=request)


class RecordingTransport(httpx.AsyncBaseTransport):
    """Passes each request to `inner` (the network by default) and writes each 200 answer into
    `folder` as a fixture (the module's docstring)."""

    def __init__(self, folder: Path, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self._folder = folder
        self._inner = inner if inner is not None else httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        content = await response.aread()
        if response.status_code == httpx.codes.OK:
            self._write(request, content)
        headers = [(k, v) for k, v in response.headers.items() if k.lower() not in _DROPPED]
        return httpx.Response(
            response.status_code, headers=headers, content=content, request=request
        )

    def _write(self, request: httpx.Request, content: bytes) -> None:
        params = _params(request)
        name = fixture_name(params)
        try:
            body = json.loads(content)
        except ValueError:
            log.warning("flight_data_recording_unreadable", fixture=name)
            return
        text = json.dumps(envelope(params, 200, body), ensure_ascii=False, indent=1)
        key = request.url.params.get(_KEY, "")
        if key and key in text:
            log.error("flight_data_recording_refused", fixture=name)
            return
        self._folder.mkdir(parents=True, exist_ok=True)
        (self._folder / name).write_text(text + "\n", encoding="utf-8", newline="\n")
        log.info("flight_data_recorded", fixture=name)

    async def aclose(self) -> None:
        await self._inner.aclose()


def recorded(folder: Path = APP_FIXTURES, **settings: Any) -> SerpApiFlightData:
    """The SerpApi adapter answering from the fixtures in `folder`, named "recorded";
    `settings` are the adapter's own (`deadline_s`, `span_days`, ...)."""
    return SerpApiFlightData(
        SecretStr("recorded"), transport=ReplayTransport(folder), name="recorded", **settings
    )
