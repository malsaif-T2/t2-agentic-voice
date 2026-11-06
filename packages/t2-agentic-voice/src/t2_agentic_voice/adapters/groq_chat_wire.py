"""What goes over the wire to and from Groq's chat completions, for `GroqChat`
(adapters/groq_chat.py, whose docstring says what each part does): a request's messages and
tools as the SDK takes them, and its stream read chunk by chunk into the chat model port's
events, each chunk parsed into this module's models first (invariant 4).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from t2_agentic_voice.adapters.groq_client import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
    Omit,
    omit,
)
from t2_agentic_voice.domain.ports.chat_model import (
    ChatEvent,
    ChatMessage,
    Done,
    FinishReason,
    TextDelta,
    ToolCallRequest,
    ToolSchema,
    Usage,
)

# What an error code sent inside the stream must look like to be kept in the details: a plain
# name (`tool_use_failed`), never a text that could hold the request.
_CODE = r"^[a-z][a-z0-9_]{0,63}$"


def given[T](value: T | None) -> T | Omit:
    """`value`, or the SDK's `omit` for none, so the field is left out and Groq's default holds."""
    return omit if value is None else value


def message_param(message: ChatMessage) -> ChatCompletionMessageParam:
    """One message as Groq's chat completions take it."""
    match message.role:
        case "system":
            return {"role": "system", "content": message.content}
        case "user":
            return {"role": "user", "content": message.content}
        case "tool":
            return {
                "role": "tool",
                "content": message.content,
                "tool_call_id": message.tool_call_id or "",
            }
    said: ChatCompletionAssistantMessageParam = {"role": "assistant"}
    if message.content or not message.tool_calls:
        said["content"] = message.content
    if message.tool_calls:
        said["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in message.tool_calls
        ]
    return said


def tool_param(tool: ToolSchema) -> ChatCompletionToolParam:
    """One tool as a function Groq's chat completions offer the model."""
    parameters: dict[str, object] = dict(tool.parameters)
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": parameters,
        },
    }


class UnfinishedError(Exception):
    """A stream that ended with no finish reason: an answer cut short."""


class _Wire(BaseModel):
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)


class _StreamError(_Wire):
    """An error Groq sent inside the stream, as far as the adapter reads it: its code."""

    code: str | None = Field(default=None, pattern=_CODE)

    @classmethod
    def code_of(cls, body: object) -> str | None:
        """The error's code, or None for no code, one that is not a plain name, or a body of
        another shape."""
        try:
            return cls.model_validate(body).code
        except ValidationError:
            return None


class _Function(_Wire):
    name: str | None = None
    arguments: str | None = None


class _CallPiece(_Wire):
    """A piece of a tool call, as a chunk's delta gives it."""

    index: int = Field(default=0, ge=0)
    id: str | None = None
    function: _Function | None = None


class _Delta(_Wire):
    content: str | None = None
    tool_calls: list[_CallPiece] | None = None


class _Choice(_Wire):
    index: int = 0
    delta: _Delta = Field(default_factory=_Delta)
    finish_reason: FinishReason | Literal["function_call"] | None = None


class _Cached(_Wire):
    cached_tokens: int | None = Field(default=None, ge=0)


class _Usage(_Wire):
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    prompt_tokens_details: _Cached | None = None

    def usage(self) -> Usage:
        details = self.prompt_tokens_details
        cached = details.cached_tokens if details and details.cached_tokens else 0
        return Usage(
            input_tokens=self.prompt_tokens,
            output_tokens=self.completion_tokens,
            cached_tokens=cached,
        )


class _Groq(_Wire):
    usage: _Usage | None = None


class _Chunk(_Wire):
    """One chunk of the stream, as far as the adapter reads it; other fields are ignored."""

    choices: list[_Choice] = Field(default_factory=list)
    usage: _Usage | None = None
    x_groq: _Groq | None = None


class _Call:
    """A tool call as its pieces come (adapters/groq_chat.py's docstring)."""

    def __init__(self) -> None:
        self.id: str | None = None
        self.name: str | None = None
        self.arguments = ""

    def add(self, piece: _CallPiece) -> None:
        self.id = self.id or piece.id
        if piece.function is not None:
            self.name = self.name or piece.function.name
            self.arguments += piece.function.arguments or ""

    def whole(self) -> ToolCallRequest:
        return ToolCallRequest.model_validate(
            {"id": self.id, "name": self.name, "arguments": self.arguments}
        )


class StreamReply:
    """What one stream has said so far, chunk by chunk: the events each chunk gives, then those
    that end it (adapters/groq_chat.py's docstring)."""

    def __init__(self) -> None:
        self._calls: dict[int, _Call] = {}
        self._usage: _Usage | None = None
        self._finish: FinishReason | None = None

    def read(self, data: Mapping[str, object]) -> list[ChatEvent]:
        chunk = _Chunk.model_validate(data)
        usage = chunk.usage or (chunk.x_groq.usage if chunk.x_groq else None)
        self._usage = usage or self._usage
        events: list[ChatEvent] = []
        for choice in (each for each in chunk.choices if each.index == 0):
            if choice.delta.content:
                events.append(TextDelta(text=choice.delta.content))
            for piece in choice.delta.tool_calls or ():
                self._calls.setdefault(piece.index, _Call()).add(piece)
            if choice.finish_reason is not None:
                reason = choice.finish_reason
                self._finish = "tool_calls" if reason == "function_call" else reason
                events += [self._calls[index].whole() for index in sorted(self._calls)]
                self._calls.clear()
        return events

    def end(self) -> list[ChatEvent]:
        if self._finish is None:
            raise UnfinishedError
        usage: list[ChatEvent] = [self._usage.usage()] if self._usage else []
        return [*usage, Done(finish_reason=self._finish)]


def stream_error_code(body: object) -> str | None:
    """The code of an error Groq sent inside the stream (its body, as the SDK gives it), or None
    for no code, one that is not a plain name, or a body of another shape."""
    return _StreamError.code_of(body)
