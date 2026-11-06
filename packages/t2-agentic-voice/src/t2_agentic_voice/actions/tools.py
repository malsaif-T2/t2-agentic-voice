"""Read tools (the design's 4.4 and 6.4; plan 006): what the talker may call inside a turn, each
a team's function over its own systems, which must have no side effect and be safe to cancel or
to have its result discarded (the design's 3.2).

- **`Tool`** holds one: its `name`, which the talker calls it by; its `description`, in English
  (models call English descriptions more reliably: the design's 6.4); `parameters`, the pydantic
  model of the arguments the talker gives, the only schema it sees; the `function`, async or
  sync; its `timeout_s`; its `progress` line's key (`Language.progress`, domain/declaration.py)
  and `progress_after_s`, how long it runs before that line is spoken; what a barge-in does to
  it (`on_interrupt`: `cancel`, the default for a read tool, or `finish`); and `bind`, its
  parameters filled from the session, never shown to the talker (`from_caller`).
- **`@tool`** makes one of an async or a sync function (a sync one runs in a worker thread),
  its parameters read from the signature; a parameter annotated `CallContext` is the call's
  context, found by its type, and optional. **`Tool.from_function`** wraps an existing function
  without rewriting it.
- **`CallContext`** is what a tool sees of the call: the verified `caller`, read-only, which
  nothing said in the call changes (invariant 3); the call's id; and the reply language.
- **What comes back:** a `ToolResult`, the data the talker reads (framed as data, never as
  instructions: invariant 4), a card for the screen, and the evidence the output guard's ID
  rule reads (domain/guard.py). A function may return one itself; the runner makes one of any
  other return.
- **Failures** (the design's 6.4): `ToolError(message)` (core/errors.py) is an expected failure
  whose message the talker gets; any other exception, or the timeout, gives the talker a generic
  "the tool failed", its type and stack logged at ERROR with no argument values.

The decorator, `from_function`, `tool_schema` and `FromCaller.value` are plan 006's Track B,
with the runner (actions/runner.py); this module holds their shapes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

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


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class FromCaller(_Frozen):
    """A parameter filled from the call's verified caller (`from_caller`), never from the
    talker: its `field`, as `subject` or `attributes.department`."""

    field: str = Field(pattern=_CALLER_FIELD)

    def value(self, caller: Caller) -> str | None:
        """The value `caller` holds for `field`, None when it holds none."""
        raise NotImplementedError("bound parameters are plan 006's Track B")


def from_caller(field: str) -> FromCaller:
    """Bind a tool's parameter to the caller's `field` (`subject`, `display_name`, `locale` or
    `attributes.<key>`): filled from the session, hidden from the talker's schema."""
    return FromCaller(field=field)


class CallContext(_Frozen):
    """What a tool sees of its call: the verified `caller`, read-only (invariant 3), the
    call's id and the reply's language."""

    caller: Caller
    call_id: CallId
    language: LanguageTag


class ToolResult(_Frozen):
    """What a tool call gave: `data`, which the talker reads as data, never as instructions;
    a `card` to show the caller, if any; and `evidence`, the texts whose ID-shaped tokens the
    output guard may let the talker say (a passage's text, a record's number)."""

    data: JsonValue = None
    card: Card | None = None
    evidence: tuple[str, ...] = ()


class Tool(_Frozen):
    """One read tool, as the module says. Build one with `@tool` or `Tool.from_function`; the
    agent's `tools` take it (domain/talker_declaration.py's `DeclaredTool` is its shape)."""

    name: str = Field(pattern=TOOL_NAME)
    description: str = Field(min_length=1)
    parameters: type[BaseModel]
    function: Callable[..., Any]
    timeout_s: float = Field(default=5.0, gt=0, allow_inf_nan=False)
    progress: ProgressKey | None = None
    progress_after_s: float = Field(default=1.0, gt=0, allow_inf_nan=False)
    on_interrupt: OnInterrupt = "cancel"
    bind: Annotated[Mapping[str, FromCaller], FROZEN, PLAIN] = Field(
        default_factory=dict, validate_default=True
    )

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
        if self.progress is not None and self.progress_after_s >= self.timeout_s:
            raise ValueError("a progress line is spoken before the tool's timeout")
        return self

    @classmethod
    def from_function(
        cls,
        function: Callable[..., Any],
        *,
        description: str,
        name: str | None = None,
        timeout_s: float = 5.0,
        progress: str | None = None,
        progress_after_s: float = 1.0,
        on_interrupt: OnInterrupt = "cancel",
        bind: Mapping[str, FromCaller] | None = None,
    ) -> Tool:
        """`function`, async or sync, as a tool named `name` (the function's own by default):
        its parameters' model read from its signature, a `CallContext` parameter and those
        `bind` fills left out."""
        raise NotImplementedError("Tool.from_function is plan 006's Track B")

    def tool_schema(self) -> ToolSchema:
        """The tool as the talker is told of it: its name, its description and the JSON schema
        of `parameters`, no bound parameter in it."""
        raise NotImplementedError("a tool's schema is plan 006's Track B")


def tool(
    *,
    description: str,
    name: str | None = None,
    timeout_s: float = 5.0,
    progress: str | None = None,
    progress_after_s: float = 1.0,
    on_interrupt: OnInterrupt = "cancel",
    bind: Mapping[str, FromCaller] | None = None,
) -> Callable[[Callable[..., Any]], Tool]:
    """The decorator that makes an async or a sync function a `Tool` (`Tool.from_function`'s
    arguments): `@tool(description="...", timeout_s=3)`."""
    raise NotImplementedError("@tool is plan 006's Track B")
