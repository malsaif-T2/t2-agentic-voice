"""The chat model port, as the design's 6.1 gives it: a request in (the messages, the tools the
model may call, the model's settings), a stream of events out (`TextDelta`, `ToolCallRequest`,
`Usage`, `Done`), each a pydantic model checked at the boundary (invariant 4).

Every chat model adapter implements `ChatModel`, and keeps to the rules of every port:

- **Cancellation.** The talker cancels a request by cancelling the task that iterates its
  stream (the reply's cancel scope, D-060). The adapter stops within 50 ms and leaves no task
  or connection behind: the response is closed. Over HTTP/1.1 a half-read answer closes its
  connection too, since the connection carries no other request until its answer is read whole,
  so the request after a cancel mid-answer opens a new one (its TCP and TLS set-up paid again);
  only an answer read to its end leaves its connection for the next request.
- **Failures** are raised as `ProviderError` (its kind, `retryable` and `retry_after_s`), from
  the stream, never as the SDK's own error, which may hold the request.
- **Tool calls** come whole: a `ToolCallRequest` holds the call's id, the tool's name and the
  raw text of its arguments as the model wrote them. Parsing that text into the tool's typed
  parameters is the tool runner's (actions/), so an invalid argument goes back to the talker
  with its field named (invariant 4), never as a provider's failure.
- **The end.** A stream that is not cancelled and does not fail ends with one `Done`, after any
  `Usage`; nothing follows it.

`aclose()` closes what the adapter holds open, as every port's does. Public through the `ports`
facade; the design's 5.1 calls it stable.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Annotated, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from t2_agentic_voice.core.settings.llm import ReasoningEffort
from t2_agentic_voice.domain.ports.speech_to_text import DataFlow

# A tool's name as the model calls it: what chat APIs take for a function's name.
TOOL_NAME = r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$"
# Who wrote a message: the instructions, the caller, the model, or a tool's result.
Role = Literal["system", "user", "assistant", "tool"]
# Why a stream ended: the model finished its text, it asked for tools, it reached
# `max_output_tokens`, or the provider filtered its content.
FinishReason = Literal["stop", "tool_calls", "length", "content_filter"]
_Count = Annotated[int, Field(ge=0)]


class _Port(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class ToolCallRequest(_Port):
    """The model asks for a tool: the call's `id`, which its result names; the tool's `name`;
    and `arguments`, the raw text the model wrote for them (JSON, unparsed and unchecked: the
    tool runner parses it)."""

    id: str = Field(min_length=1, max_length=256)
    name: str = Field(pattern=TOOL_NAME)
    arguments: str = ""


class ChatMessage(_Port):
    """One message of a request: the instructions (`system`), the caller's words (`user`), the
    model's own reply (`assistant`, with the tool calls it asked for, if any), or a tool's
    result (`tool`, naming the call it answers). Build one with `system`, `user`, `assistant`
    or `tool_result`."""

    role: Role
    content: str = ""
    tool_calls: tuple[ToolCallRequest, ...] = ()
    tool_call_id: str | None = Field(default=None, min_length=1, max_length=256)

    @model_validator(mode="after")
    def _of_its_role(self) -> Self:
        if self.tool_calls and self.role != "assistant":
            raise ValueError("only the model's own message asks for tools")
        if (self.tool_call_id is not None) != (self.role == "tool"):
            raise ValueError("a tool's result names the call it answers, and no other does")
        if self.role != "assistant" and not self.content:
            raise ValueError("a message says something, but the model's own may only call tools")
        return self

    @classmethod
    def system(cls, content: str) -> Self:
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> Self:
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str = "", *, tool_calls: tuple[ToolCallRequest, ...] = ()) -> Self:
        return cls(role="assistant", content=content, tool_calls=tool_calls)

    @classmethod
    def tool_result(cls, call_id: str, content: str) -> Self:
        return cls(role="tool", content=content, tool_call_id=call_id)


class ToolSchema(_Port):
    """A tool as the model is told of it: its `name`, its `description` (in English, which
    models call more reliably: the design's 6.4), and its `parameters`, a JSON schema of an
    object, with no bound parameter in it."""

    name: str = Field(pattern=TOOL_NAME)
    description: str = Field(min_length=1)
    parameters: Mapping[str, JsonValue] = Field(default_factory=lambda: {"type": "object"})

    @model_validator(mode="after")
    def _an_object(self) -> Self:
        if self.parameters.get("type") != "object":
            raise ValueError("a tool's parameters are the JSON schema of an object")
        return self


class ChatRequest(_Port):
    """One request to the model: its `messages`, the `tools` it may call (each name once), the
    `model`, how much it reasons (`reasoning_effort`, None for a model that takes none), the
    most tokens it may write, and its `temperature` (None: the provider's default)."""

    messages: tuple[ChatMessage, ...] = Field(min_length=1)
    tools: tuple[ToolSchema, ...] = ()
    model: str = Field(min_length=1)
    reasoning_effort: ReasoningEffort | None = None
    max_output_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)

    @model_validator(mode="after")
    def _each_tool_once(self) -> Self:
        names = [tool.name for tool in self.tools]
        if len(set(names)) != len(names):
            raise ValueError("each tool is offered once, by its own name")
        return self


class TextDelta(_Port):
    """The next piece of the model's text, as it streams."""

    text: str = Field(min_length=1)


class Usage(_Port):
    """What the request used, as the provider reports it: the tokens read (`input_tokens`, the
    cached ones among them counted again in `cached_tokens`) and written (`output_tokens`, its
    reasoning included)."""

    input_tokens: _Count
    output_tokens: _Count
    cached_tokens: _Count = 0

    @model_validator(mode="after")
    def _cached_among_read(self) -> Self:
        if self.cached_tokens > self.input_tokens:
            raise ValueError("the cached tokens are among the tokens read")
        return self


class Done(_Port):
    """The stream ended, and why (`FinishReason`)."""

    finish_reason: FinishReason


type ChatEvent = TextDelta | ToolCallRequest | Usage | Done


class ChatModel(Protocol):
    """A chat model behind the port. `name` identifies it in logs and traces; `data_flow` says
    where the messages go."""

    name: str
    data_flow: DataFlow

    def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        """The model's answer to `request`, event by event as the provider streams it: text,
        whole tool calls, then its usage and one `Done`. Raises `ProviderError` on the
        provider's failure; a cancel stops it within 50 ms and closes its response."""

    async def aclose(self) -> None:
        """Close what the adapter holds open, its connections; an adapter that holds none
        returns at once. Called once, when its owner (the runtime, a run) is done with it."""
