"""The test console's feed (api/dev_console.py; D-083): `DevFeed`, one observer of every event
the runtime emits (core/events.py), which the console's page reads (`GET /dev/feed`).

- **In memory**, the records of the last `FEED_CALLS` calls, at most `FEED_RECORDS` in all,
  each numbered in order (`seq`).
- **On disk**, every call's events, kept since they are development calls (the owner,
  2026-11-10): one JSON line per event, appended off the event loop, in `<call ID>.jsonl` under
  `storage.var_dir`'s `dev-console/` (`CONSOLE_FOLDER`), which nothing deletes. A start's feed
  reads the newest `FEED_CALLS` files back, oldest first, before it keeps its first event or
  answers its first page, each line parsed as the event its `type` names, a line that is not
  one skipped.
- Nothing of it is logged: the events hold call content (docs/SECURITY.md, invariant 8); a file
  that cannot be written or read is logged by the failure's kind alone. A restart starts a new
  feed, named apart (`name`), so the page knows to start over.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from collections import deque
from contextlib import suppress
from pathlib import Path
from typing import Final

from pydantic import JsonValue

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import EVENTS, CallEnded, Event
from t2_agentic_voice.core.logging import get_logger

# The calls whose records the feed keeps, and the most records in all.
FEED_CALLS: Final = 20
FEED_RECORDS: Final = 20_000
# The folder under `storage.var_dir` that holds each call's events, one file a call.
CONSOLE_FOLDER: Final = "dev-console"
# Each event's class by the name a saved line gives as its `type`.
_EVENT_TYPES: Final[dict[str, type[Event]]] = {kind.__name__: kind for kind in EVENTS}

_log = get_logger(__name__)


class DevFeed:
    """The records of the runtime's events, newest last, each call's saved in `folder` when
    given (the module's docstring)."""

    def __init__(
        self, *, folder: Path | None = None, calls: int = FEED_CALLS, records: int = FEED_RECORDS
    ) -> None:
        self.name = secrets.token_hex(4)
        self._folder, self._calls, self._most = folder, calls, records
        self._records: deque[dict[str, JsonValue]] = deque()
        self._order: list[str] = []  # the calls kept, oldest first
        self._seq = 0
        self._new = asyncio.Event()
        self._loading = asyncio.Lock()
        self._loaded = folder is None

    @classmethod
    def of(cls, settings: VoiceSettings) -> DevFeed:
        """The feed of a runtime run with `settings`, its calls saved under `storage.var_dir`."""
        return cls(folder=settings.storage.var_dir / CONSOLE_FOLDER)

    @property
    def last(self) -> int:
        """The number of the newest record, 0 before the first."""
        return self._seq

    async def observe(self, event: Event) -> None:
        """The runtime's observer of every event: kept, then saved in its call's file."""
        await self.ready()
        record = self.add(event)
        if self._folder is not None:
            line = json.dumps(
                {"type": record["type"], "event": record["event"]}, ensure_ascii=False
            )
            await asyncio.to_thread(_save, self._folder, event.call_id, line)

    async def ready(self) -> None:
        """Read the saved calls back, once, before the first event is kept or page answered."""
        if self._loaded or self._folder is None:
            return
        async with self._loading:
            if not self._loaded:
                for event in await asyncio.to_thread(self._saved, self._folder):
                    self.add(event)
                self._loaded = True

    def _saved(self, folder: Path) -> list[Event]:
        """The events of the newest FEED_CALLS calls saved in `folder`, the oldest call's first,
        each call's in order."""
        try:
            files = sorted(folder.glob("*.jsonl"), key=lambda path: path.stat().st_mtime)
        except OSError as error:
            _log.warning("dev_console_not_read", failure=type(error).__name__)
            return []
        events: list[Event] = []
        skipped = 0
        for path in files[-self._calls :]:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError) as error:
                _log.warning("dev_console_not_read", failure=type(error).__name__)
                continue
            for line in lines:
                event = _event_of(line)
                skipped += event is None
                if event is not None:
                    events.append(event)
        _log.info("dev_console_read", calls=min(len(files), self._calls), skipped=skipped)
        return events

    def add(self, event: Event) -> dict[str, JsonValue]:
        """Keep `event` as the newest record, returned; the oldest call's records go once more
        calls than FEED_CALLS are kept, and the oldest records once more than FEED_RECORDS."""
        if event.call_id not in self._order:
            self._order.append(event.call_id)
            while len(self._order) > self._calls:
                gone = self._order.pop(0)
                kept = [each for each in self._records if each["call_id"] != gone]
                self._records = deque(kept)
        self._seq += 1
        record: dict[str, JsonValue] = {
            "seq": self._seq,
            "type": type(event).__name__,
            "call_id": event.call_id,
            "ended": isinstance(event, CallEnded),
            "event": event.model_dump(mode="json"),
        }
        self._records.append(record)
        while len(self._records) > self._most:
            self._records.popleft()
        self._new.set()
        self._new = asyncio.Event()
        return record

    def after(self, seq: int) -> list[dict[str, JsonValue]]:
        """The records after `seq`; every record when `seq` is past the newest (an earlier
        feed's number)."""
        start = 0 if seq > self._seq else seq
        return [each for each in self._records if _seq(each) > start]

    async def wait_after(self, seq: int, *, wait_s: float) -> list[dict[str, JsonValue]]:
        """The records after `seq`, at once when there are any, else once one comes or `wait_s`
        has passed (then none)."""
        await self.ready()
        found = self.after(seq)
        if found or wait_s <= 0:
            return found
        new = self._new
        with suppress(TimeoutError):
            async with asyncio.timeout(wait_s):
                await new.wait()
        return self.after(seq)


def _save(folder: Path, call_id: str, line: str) -> None:
    """Append `line` to the call's file in `folder`; `call_id` is a `CallId`, so no path is in
    it. A failure is logged by its kind alone."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / f"{call_id}.jsonl").open("a", encoding="utf-8", newline="\n") as file:
            file.write(line + "\n")
    except OSError as error:
        _log.warning("dev_console_not_saved", call_id=call_id, failure=type(error).__name__)


def _event_of(line: str) -> Event | None:
    """The event a saved line holds, parsed as the class its `type` names; None for a line that
    is not one (blank, not JSON, an unknown type, or fields its class refuses)."""
    try:
        saved = json.loads(line)
        return _EVENT_TYPES[saved["type"]].model_validate(saved["event"])
    except (ValueError, KeyError, TypeError):
        return None


def _seq(record: dict[str, JsonValue]) -> int:
    value = record["seq"]
    return value if isinstance(value, int) else 0
