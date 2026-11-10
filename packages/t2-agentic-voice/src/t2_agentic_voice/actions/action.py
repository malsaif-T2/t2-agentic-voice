"""Confirmed actions (the design's 4.4 and 6.4): one side effect, run only after the caller's yes,
as a job outside the turn.

- **`Action`** holds one: its `name`, which the talker calls it by; its `description`, in
  English; `draft`, the pydantic model of what the talker gives, the only schema it sees;
  `result`, the model the function returns; the `execute` function; the words (`read_back`,
  `done`, `claims`, and `sending`, `failed`, `unknown`, `declined`, the library's own unless
  given; `sending` is said while the write runs, a fixed line that never says it is done); an
  optional `validate`; `max_per_call` and `timeout_s`. Build one with **`@action`**.
- **`@action`** reads the draft and the result from the function's signature: a `draft`
  parameter, a return annotation, each a pydantic model, and optionally a parameter annotated
  `ActionContext`. `@my_action.lookup` registers how to find a write whose reply was lost.
- **`ActionContext`** is `CallContext` plus the `request_id`, which the team should pass to its
  backend as an idempotency key; `consent`, the heard words that confirmed the action, for
  audit; and `conversation`, what each side said in the call. A backend is reached by a
  closure, as `knowledge_tool` reaches its knowledge base.

An action's schema is its draft's, with no field beyond it. Parsing refuses a key the draft
does not hold, so a field the talker invents is told back to it (invariant 4), and consent is
never something the talker can claim (invariant 1). Every check is actions/action_checks.py's.

What the runtime does with an action is the job of `actions/action_runner.py` (plan 007's
Track B).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Final, final

from pydantic import BaseModel, ConfigDict, Field

from t2_agentic_voice.actions.action_checks import (
    check_draft,
    check_read_back,
    check_templates,
    draft_and_result,
)
from t2_agentic_voice.actions.tools import CallContext, untitled_schema
from t2_agentic_voice.core.conversation import ConversationLine
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.yes_inputs import HeardSource
from t2_agentic_voice.domain.action_declaration import Claims, ReadBack, Say, refused
from t2_agentic_voice.domain.ports.chat_model import TOOL_NAME, ToolSchema

# The seconds an action's write may take before the runtime looks it up or says it is unknown,
# and how many times one may be done in a call (the design's 6.4).
TIMEOUT_S: Final = 20.0
MAX_PER_CALL: Final = 1
_NAME = re.compile(TOOL_NAME)


class HeardConsent(BaseModel):
    """The words that confirmed an action, read-only, for the team's audit: what was heard, in
    which `source`, and when the caller began saying it on the call's clock."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    words: str = Field(repr=False)
    source: HeardSource
    speech_at: float | None


class ActionContext(CallContext):
    """What an action sees of its call (the module's docstring)."""

    request_id: str = Field(min_length=1)
    consent: HeardConsent
    conversation: tuple[ConversationLine, ...] = ()


def _strict(draft: type[BaseModel]) -> type[BaseModel]:
    """`draft` with an unknown key an error: the model the talker's arguments are parsed into."""
    config = ConfigDict(extra="forbid", hide_input_in_errors=True, protected_namespaces=())
    attributes = {"__module__": draft.__module__, "model_config": config}
    metaclass: Any = type(draft)
    made: type[BaseModel] = metaclass(draft.__name__, (draft,), attributes)
    return made


@final
@dataclass(frozen=True, eq=False, kw_only=True)
class Action:
    """One action, as the module says. Build one with `@action`. It has the shape the agent's
    `tools` take (`DeclaredAction`). Frozen but for `lookup`, registered once."""

    name: str
    description: str
    draft: type[BaseModel]
    result: type[BaseModel]
    execute: Callable[..., Any]
    read_back: ReadBack
    done: Say
    claims: Claims
    sending: Say | None = None
    failed: Say | None = None
    unknown: Say | None = None
    declined: Say | None = None
    validate: Callable[..., Any] | None = None
    max_per_call: int = MAX_PER_CALL
    timeout_s: float = TIMEOUT_S
    finder: Callable[..., Any] | None = field(default=None, init=False)
    parameters: type[BaseModel] = field(init=False)
    progress: None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if not _NAME.fullmatch(self.name):
            raise refused("name", "it is not a tool name", 'name it as "open_request"')
        if not self.description.strip():
            raise refused("description", "it says nothing", "tell the talker when to call it")
        bad_cap = type(self.max_per_call) is not int or self.max_per_call < 1
        bad_time = not isinstance(self.timeout_s, int | float) or isinstance(self.timeout_s, bool)
        if bad_cap or bad_time or not 0 < self.timeout_s < math.inf:
            raise refused("max_per_call", "it is below 1, or timeout_s not above 0", _LIMITS_FIX)
        check_draft(self.draft)
        check_read_back(self.read_back, self.draft)
        check_templates(
            self.done,
            self.result,
            self.draft,
            (
                ("sending", self.sending),
                ("failed", self.failed),
                ("unknown", self.unknown),
                ("declined", self.declined),
                ("asked_again", self.read_back.asked_again),
            ),
        )
        object.__setattr__(self, "parameters", _strict(self.draft))

    def lookup(self, function: Callable[..., Any]) -> Callable[..., Any]:
        """Register, once, how to find a write whose reply was lost, by its `request_id`."""
        if self.finder is not None:
            raise ConfigurationError(
                "An action takes one lookup. FIX: decorate only one function with @name.lookup.",
                details={"field": "lookup"},
            )
        object.__setattr__(self, "finder", function)
        return function

    def replaced(
        self,
        *,
        execute: Callable[..., Any] | None = None,
        lookup: Callable[..., Any] | None = None,
    ) -> Action:
        """This action with `execute` and its lookup replaced, for a test's faults."""
        made = replace(self, execute=execute or self.execute)
        object.__setattr__(made, "finder", lookup or self.finder)
        return made

    def tool_schema(self) -> ToolSchema:
        """The action as the talker is told of it: its name, its description and the draft's
        schema, and nothing more."""
        schema = untitled_schema(self.parameters.model_json_schema())
        return ToolSchema(name=self.name, description=self.description, parameters=schema)

    @property
    def texts(self) -> Mapping[str, Say | ReadBack | Claims]:
        """Each of its texts the agent's languages must cover, by the field that holds it."""
        kept: dict[str, Say | ReadBack | Claims] = {
            "read_back": self.read_back,
            "done": self.done,
            "claims": self.claims,
        }
        for name in ("sending", "failed", "unknown", "declined"):
            text: Say | None = getattr(self, name)
            if text is not None:
                kept[name] = text
        if self.read_back.asked_again is not None:
            kept["asked_again"] = self.read_back.asked_again
        return kept


def action(
    *,
    description: str,
    read_back: ReadBack,
    done: Say,
    claims: Claims,
    name: str | None = None,
    sending: Say | None = None,
    failed: Say | None = None,
    unknown: Say | None = None,
    declined: Say | None = None,
    validate: Callable[..., Any] | None = None,
    max_per_call: int = MAX_PER_CALL,
    timeout_s: float = TIMEOUT_S,
) -> Callable[[Callable[..., Any]], Action]:
    """The decorator that makes an async or a sync function an `Action` (the module's
    docstring): `@action(description="...", read_back=ReadBack(...), done=Say(...),
    claims=Claims(...))`. ConfigurationError, naming the field, for anything it cannot run."""

    def made(function: Callable[..., Any]) -> Action:
        draft, result = draft_and_result(function, context=ActionContext)
        return Action(
            name=name if name is not None else getattr(function, "__name__", ""),
            description=description,
            draft=draft,
            result=result,
            execute=function,
            read_back=read_back,
            done=done,
            claims=claims,
            sending=sending,
            failed=failed,
            unknown=unknown,
            declined=declined,
            validate=validate,
            max_per_call=max_per_call,
            timeout_s=timeout_s,
        )

    return made


_LIMITS_FIX = "give max_per_call a whole number of 1 or more and timeout_s a number above 0"
