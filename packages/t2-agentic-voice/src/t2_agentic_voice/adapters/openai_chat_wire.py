"""What goes over the wire to and from OpenAI's Chat Completions, for `OpenAIChat`
(adapters/openai_chat.py, whose docstring says what each part does): a request's body, built
from Groq's wire (adapters/groq_chat_wire.py), each line of the stream read into the chunk it
carries, every failure as a `ProviderError`, and the adapter's key held to the settings' rules.
"""

from __future__ import annotations

import json
from typing import Final

from pydantic import JsonValue, SecretStr, ValidationError

from t2_agentic_voice.adapters.groq_chat_wire import (
    UnfinishedError,
    message_param,
    stream_error_code,
    tool_param,
)
from t2_agentic_voice.adapters.provider_http import AnswerError, http_failure
from t2_agentic_voice.core.errors import ConfigurationError, ProviderError
from t2_agentic_voice.core.settings.base import setting_name
from t2_agentic_voice.core.settings.llm import REASONING_MODELS
from t2_agentic_voice.core.settings.provider_keys import OpenAISettings
from t2_agentic_voice.domain.ports.chat_model import ChatRequest
from t2_agentic_voice.domain.ports.speech_to_text import DataFlow

_DATA: Final = "data:"
_DONE: Final = "[DONE]"
VENDOR: Final = "OpenAI"
# OpenAI's API data terms (its "Your data" page for the API, read 2026-11-17).
DATA_FLOW: Final = DataFlow(
    provider="OpenAI",
    processed_in="the US by default; other regions only under a data-residency project",
    stored_in="OpenAI's abuse-monitoring logs, for data OpenAI retains",
    retention=(
        "API inputs and outputs kept up to 30 days for abuse monitoring and never used for "
        "training by default; zero data retention only by OpenAI's approval"
    ),
)


class StreamErrorError(Exception):
    """An error OpenAI sent inside the stream, named by its code when it is a plain name."""

    def __init__(self, code: str | None) -> None:
        super().__init__("stream_error")
        self.code = code


def body_of(request: ChatRequest) -> dict[str, object]:
    """The JSON body of the streamed request for `request` (adapters/openai_chat.py's
    docstring): a value the request leaves out is not sent."""
    body: dict[str, object] = {
        "model": request.model,
        "messages": [message_param(message) for message in request.messages],
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if request.tools:
        body["tools"] = [tool_param(tool) for tool in request.tools]
        body["parallel_tool_calls"] = True
    if request.max_output_tokens is not None:
        body["max_completion_tokens"] = request.max_output_tokens
    if request.temperature is not None:
        body["temperature"] = request.temperature
    if request.reasoning_effort is not None and request.model in REASONING_MODELS:
        body["reasoning_effort"] = request.reasoning_effort
    return body


def chunk_of(line: str) -> dict[str, object] | None:
    """The chunk one line of the stream carries; None for a line that carries none (a blank,
    a comment, another field, `[DONE]`). StreamErrorError for an error sent in the stream,
    AnswerError for data that is not a JSON object."""
    if not line.startswith(_DATA):
        return None
    data = line.removeprefix(_DATA).strip()
    if data == _DONE:
        return None
    try:
        parsed = json.loads(data)
    except ValueError:
        raise AnswerError("unreadable_chunk") from None
    if not isinstance(parsed, dict):
        raise AnswerError("unreadable_chunk")
    if "error" in parsed:
        raise StreamErrorError(stream_error_code(parsed["error"]))
    return parsed


def failure(error: Exception) -> ProviderError:
    """The ProviderError for a failure of a chat request (the module's docstring)."""
    if isinstance(error, UnfinishedError):
        return ProviderError("server_error", False, details={"error": "no_finish"})
    if isinstance(error, StreamErrorError):
        details: dict[str, JsonValue] = {"provider": VENDOR, "error": "stream_error"}
        if error.code:
            details["code"] = error.code
        return ProviderError("rejected", False, details=details)
    return http_failure(VENDOR, error)


def checked(api_key: SecretStr, base_url: str) -> SecretStr:
    """The key, once the `openai` group's own model takes it and the base URL, by the rules the
    settings load by (GP-20): a ConfigurationError naming the setting, never the value, raised
    outside the handler, so no exception chain leads to it."""
    try:
        group = OpenAISettings(api_key=api_key, base_url=base_url)
    except ValidationError as error:
        problem = error.errors(include_input=False, include_url=False)[0]
    else:
        key = group.resolved_api_key()
        if key is None:
            raise no_key(setting_name("openai", "api_key"))
        return key
    setting = setting_name("openai", *problem["loc"])
    raise ConfigurationError(
        f"The OpenAI chat adapter refuses its {setting} ({problem['msg']}). FIX: give it a "
        "value the settings take.",
        details={"setting": setting},
    )


def no_key(setting: str) -> ConfigurationError:
    """The error for the openai chat provider chosen with no key: which variable to set."""
    return ConfigurationError(
        f"No OpenAI API key is set, so its chat adapter is unavailable. FIX: set {setting}, or "
        f"{setting}_FILE to a file that holds the key, or set llm.provider to groq.",
        details={"setting": setting},
    )
