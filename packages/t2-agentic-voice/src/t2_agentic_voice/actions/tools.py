"""Read tools (the design's 4.4 and 6.4; plan 006): what the talker may call inside a turn, each
a team's function over its own systems, which must have no side effect and be safe to cancel or
to have its result discarded (the design's 3.2).

- **`Tool`** holds one: its `name`, which the talker calls it by; its `description`, in English
  (models call English descriptions more reliably: the design's 6.4); `parameters`, the pydantic
  model of the arguments the talker gives, the only schema it sees; the `function`, async or
  sync; its `timeout_s`; its `progress` line's key (`Language.progress`, domain/declaration.py)
  and `progress_after_s`, how long after the caller stopped speaking that line is said if no
  answer has been asked of the voice, whether the tool or the model holds it up (plan 006, Q27);
  what a barge-in does to
  it (`on_interrupt`: `cancel`, the default for a read tool, or `finish`); and `bind`, its
  parameters filled from the session, never shown to the talker (`from_caller`).
- **`@tool`** makes one of an async or a sync function (a sync one runs in a worker thread),
  its parameters read from the signature; a parameter annotated `CallContext` is the call's
  context, found by its type, and optional. **`Tool.from_function`** wraps an existing function
  without rewriting it.
- **`CallContext`** is what a tool sees of the call: the verified `caller`, read-only, which
  nothing said in the call changes (invariant 3); the call's id; the reply language; the call's
  `record` of completed actions as plain values; and `past_actions`, what this caller has had
  done before (the design's 6.4; plan 007's Q4). A tool with `reports_on` may back up a claim
  about those actions (the design's 8.2, rule A).
- **What comes back:** a `ToolResult`, the data the talker reads (framed as data, never as
  instructions: invariant 4), a card for the screen, the evidence the output guard's ID rule
  reads beside the data (domain/guard.py), and whether the call succeeded (`ok`). A function may
  return one itself; the runner makes one of any other return, its value as JSON.
- **Failures** (the design's 6.4): `ToolError(message)` (core/errors.py) is an expected failure
  whose message the talker gets; any other exception, or the timeout, gives the talker a generic
  "the tool failed" (the runner, actions/runner.py): an exception logged at ERROR by its type
  and its frames, a timeout at WARNING as `tool_timed_out` with its `timeout_s`, never an
  argument's value.

A function `from_function` cannot call by its parameters' names (a `*args`, a parameter with no
annotation, a `bind=` for a parameter it lacks), or a field `Tool` refuses, is a
ConfigurationError naming the field, with a FIX line, never the value (actions/signature.py).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Annotated, Any, Final, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    PrivateAttr,
    ValidationError,
    field_validator,
    model_validator,
)

from t2_agentic_voice.actions.signature import arguments_model
from t2_agentic_voice.actions.tool_schema import model_schema
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.events import CallId
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.base import FROZEN, PLAIN
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.ports.chat_model import TOOL_NAME, ToolSchema
from t2_agentic_voice.domain.talker_declaration import ProgressKey

# What a barge-in does to a tool still running: cancel it (a read tool's default), or let it
# finish, its result kept for the talker's next turn (the design's 6.4).
OnInterrupt = Literal["cancel", "finish"]
# The fields of a `Caller` a bound parameter may take: its subject, its name, its locale, or
# one of its attributes, as `attributes.<key>`.
_CALLER_FIELD = r"^(subject|display_name|locale|attributes\.[A-Za-z0-9_.-]{1,64})$"
_ATTRIBUTES = "attributes."
# Seconds after the caller stopped speaking with no answer begun that a tool's progress line is
# said by default: under 3.0 s by the cached line's own leading silence (up to about 0.25 s) and
# the way out, so the caller hears it by then (plan 006, Q27).
PROGRESS_AFTER_S: Final = 2.6
# The seconds a tool's call may take by default before it is a timeout.
TIMEOUT_S: Final = 5.0
# What fixes each field of a tool that `from_function` cannot build.
_FIXES = {
    "name": 'name the tool with letters, digits, underscores and hyphens, as name="lookup_device"',
    "description": "describe, in English, when the talker calls it",
    "timeout_s": "give timeout_s a number of seconds above 0",
    "progress": 'name the progress line by its key, a lowercase word, as progress="searching"',
    "progress_after_s": "give progress_after_s a number of seconds above 0",
    "on_interrupt": 'give on_interrupt "cancel" or "finish"',
    "bind": 'bind each parameter with from_caller("subject") or another field of the caller',
    "reports_on": 'name the actions its results report on, as reports_on=["open_request"]',
}


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class FromCaller(_Frozen):
    """A parameter filled from the call's verified caller (`from_caller`), never from the
    talker: its `field`, as `subject` or `attributes.department`."""

    field: str = Field(pattern=_CALLER_FIELD)

    def value(self, caller: Caller) -> str | None:
        """The value `caller` holds for `field`, None when it holds none."""
        if self.field.startswith(_ATTRIBUTES):
            return caller.attributes.get(self.field.removeprefix(_ATTRIBUTES))
        value: str | None = getattr(caller, self.field)
        return value


def from_caller(field: str) -> FromCaller:
    """Bind a tool's parameter to the caller's `field` (`subject`, `display_name`, `locale` or
    `attributes.<key>`): filled from the session, hidden from the talker's schema."""
    return FromCaller(field=field)


class RecordedAction(_Frozen):
    """An action done for this caller, as plain values a tool or an action reads: its name,
    its `request_id`, and its real result. Proves nothing: only the record's own entries do."""

    action: str
    request_id: str
    result: JsonValue = None


# How a context reads the actions a caller had done, given the verified caller's subject and the
# action's name: the action runner's `past`, over its outbox.
PastReader = Callable[[str, str], Awaitable[tuple[RecordedAction, ...]]]


class CallContext(_Frozen):
    """What a tool sees of its call: the verified `caller`, read-only (invariant 3), the
    call's id and the reply's language, and the actions done in this call (`record`)."""

    caller: Caller
    call_id: CallId
    language: LanguageTag
    record: tuple[RecordedAction, ...] = ()
    _past: PastReader | None = PrivateAttr(default=None)

    def reading_past(self, reader: PastReader) -> Self:
        """A copy of this context whose `past_actions` reads through `reader` (the talker
        gives the runner's, over its outbox)."""
        made = self.model_copy()
        made._past = reader
        return made

    async def past_actions(self, action: str) -> tuple[RecordedAction, ...]:
        """The actions named `action` this caller had done, in this call or before it, newest
        last, read from the outbox and scoped to the verified caller: the subject is the
        context's own, never an argument. A context given no reader (one a test builds) reads
        this call's `record` alone."""
        if self._past is None:
            return tuple(done for done in self.record if done.action == action)
        return await self._past(self.caller.subject, action)


class ToolResult(_Frozen):
    """What a tool call gave: `data`, which the talker reads as data, never as instructions;
    a `card` to show the caller, if any; `evidence`, the texts beside `data` whose ID-shaped
    tokens the output guard may let the talker say (a passage's whole text, a record's number);
    and `ok`, False when the call failed (a `ToolError`, any other failure, the timeout, an
    argument the talker got wrong), its `data` then saying why, and `failure` naming what failed
    for the call's trace (D-078): a word or two the runner sets, never a value."""

    data: JsonValue = None
    card: Card | None = None
    evidence: tuple[str, ...] = ()
    ok: bool = True
    failure: str | None = None

    def texts(self) -> tuple[str, ...]:
        """The texts the output guard reads as this result's evidence: its data as JSON, then
        its evidence texts."""
        return (json.dumps(self.data, ensure_ascii=False), *self.evidence)


class Tool(_Frozen):
    """One read tool, as the module says. Build one with `@tool` or `Tool.from_function`; the
    agent's `tools` take it (domain/talker_declaration.py's `DeclaredTool` is its shape)."""

    name: str = Field(pattern=TOOL_NAME)
    description: str = Field(min_length=1)
    parameters: type[BaseModel]
    function: Callable[..., Any]
    timeout_s: float = Field(default=TIMEOUT_S, gt=0, allow_inf_nan=False)
    progress: ProgressKey | None = None
    progress_after_s: float = Field(default=PROGRESS_AFTER_S, gt=0, allow_inf_nan=False)
    on_interrupt: OnInterrupt = "cancel"
    bind: Annotated[Mapping[str, FromCaller], FROZEN, PLAIN] = Field(
        default_factory=dict, validate_default=True
    )
    reports_on: tuple[Annotated[str, Field(pattern=TOOL_NAME)], ...] = ()

    @field_validator("description")
    @classmethod
    def _says_something(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("a tool's description tells the talker when to call it")
        return value

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if set(self.bind) & set(self.parameters.model_fields):
            raise ValueError("a bound parameter is filled from the session, never by the talker")
        return self

    @classmethod
    def from_function(
        cls,
        function: Callable[..., Any],
        *,
        description: str,
        name: str | None = None,
        timeout_s: float = TIMEOUT_S,
        progress: str | None = None,
        progress_after_s: float = PROGRESS_AFTER_S,
        on_interrupt: OnInterrupt = "cancel",
        bind: Mapping[str, FromCaller] | None = None,
        reports_on: Sequence[str] = (),
    ) -> Tool:
        """`function`, async or sync, as a tool named `name` (the function's own by default):
        its parameters' model read from its signature, a `CallContext` parameter and those
        `bind` fills left out. ConfigurationError, naming the field, for a function it cannot
        call by its parameters' names or a value `Tool` refuses."""
        bound = dict(bind or {})
        parameters = arguments_model(function, bound=bound, context=CallContext)
        values = {
            "name": name if name is not None else getattr(function, "__name__", ""),
            "description": description,
            "parameters": parameters,
            "function": function,
            "timeout_s": timeout_s,
            "progress": progress,
            "progress_after_s": progress_after_s,
            "on_interrupt": on_interrupt,
            "bind": bound,
            "reports_on": reports_on,
        }
        try:
            return cls.model_validate(values)
        except ValidationError as error:
            first = error.errors(include_input=False, include_url=False)[0]
        # The check of the whole tool names no field: it is its `bind`.
        field = str(first["loc"][0]) if first["loc"] else "bind"
        raise ConfigurationError(
            f"A tool cannot take its `{field}`: {first['msg']}. "
            f"FIX: {_FIXES.get(field, _FIXES['bind'])}.",
            details={"field": field},
        )

    def tool_schema(self) -> ToolSchema:
        """The tool as the talker is told of it: its name, its description and the JSON schema
        of `parameters`, no bound parameter in it (`from_function` leaves them out, and a
        `parameters` model given whole may not hold one), the schema's titles left out, which
        the model reads at every request and needs none of."""
        schema = model_schema(self.parameters.model_json_schema())
        return ToolSchema(name=self.name, description=self.description, parameters=schema)


def tool(
    *,
    description: str,
    name: str | None = None,
    timeout_s: float = TIMEOUT_S,
    progress: str | None = None,
    progress_after_s: float = PROGRESS_AFTER_S,
    on_interrupt: OnInterrupt = "cancel",
    bind: Mapping[str, FromCaller] | None = None,
    reports_on: Sequence[str] = (),
) -> Callable[[Callable[..., Any]], Tool]:
    """The decorator that makes an async or a sync function a `Tool` (`Tool.from_function`'s
    arguments): `@tool(description="...", timeout_s=3)`."""

    def made(function: Callable[..., Any]) -> Tool:
        return Tool.from_function(
            function,
            description=description,
            name=name,
            timeout_s=timeout_s,
            progress=progress,
            progress_after_s=progress_after_s,
            on_interrupt=on_interrupt,
            bind=bind,
            reports_on=reports_on,
        )

    return made
