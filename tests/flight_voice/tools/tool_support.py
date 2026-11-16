"""What the flight tools' tests share: the mock airline on the pinned day, a call's context as
the token route mints it (the demo traveler), each tool run through the library's own runner
from the arguments as JSON (so every argument is parsed as the talker's would be), and the ID
rule's check of a card against its result."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from typing import Any, Final

from flight_voice.airline.system import Airline
from flight_voice.said import Tag
from flight_voice.trip import TripBook
from t2_agentic_voice import CallContext, Caller, GuardSettings, Tool, ToolResult
from t2_agentic_voice.actions.runner import ToolRunner
from t2_agentic_voice.core.clock import SYSTEM_CLOCK
from t2_agentic_voice.domain.guard_ids import check_ids
from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest

from tests.flight_voice.scenario_dates import TODAY

CALL_ID: Final = "call-1"
# The demo traveler, as the token route mints every caller.
CALLER: Final = Caller(subject="owner", attributes={"traveler_id": "T-0001"})
TAGS: Final[tuple[Tag, ...]] = ("ar-SA", "ar", "en")
YEAR: Final = TODAY.year


def airline(**modes: Any) -> Airline:
    """The mock airline, today the pinned Monday, its modes as given."""
    return Airline(today=lambda: TODAY, **modes)


def context(tag: Tag = "en", call_id: str = CALL_ID, caller: Caller = CALLER) -> CallContext:
    """A call's context: the demo traveler, in `tag`."""
    return CallContext(caller=caller, call_id=call_id, language=tag)


def run(tool: Tool, tag: Tag = "en", call_id: str = CALL_ID, **arguments: Any) -> ToolResult:
    """`tool` run by the library's runner on `arguments`, sent as JSON, in a call in `tag`."""
    request = ToolCallRequest(id="t-1", name=tool.name, arguments=json.dumps(arguments))
    runner = ToolRunner([tool])
    return asyncio.run(runner.run(request, context(tag, call_id), clock=SYSTEM_CLOCK))


def data(result: ToolResult) -> dict[str, Any]:
    """A result's data, as an object."""
    assert isinstance(result.data, dict), result
    return result.data


def ids_pass(texts: Iterable[str], evidence: Iterable[str]) -> bool:
    """Whether every text passes the ID rule, the default guard settings, against `evidence`."""
    known = tuple(evidence)
    return all(
        check_ids(t, evidence=known, settings=GuardSettings(), year=YEAR).passed for t in texts
    )


def card_passes(result: ToolResult) -> bool:
    """Whether the result's card passes the ID rule against its data alone (every number the
    card shows is in the data), and against the result's whole evidence, as the call reads it."""
    assert result.card is not None
    texts = result.card.texts()
    return ids_pass(texts, (json.dumps(result.data, ensure_ascii=False),)) and ids_pass(
        texts, result.texts()
    )


def book() -> TripBook:
    """A new trip book."""
    return TripBook()
