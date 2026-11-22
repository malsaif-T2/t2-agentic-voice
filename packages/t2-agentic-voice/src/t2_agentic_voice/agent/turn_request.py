"""One model request of a turn (agent/turn.py's "The request"), as `request_of` builds it from
the turn's messages: a first line new on every request (`llm.vary_first_line`), the calls with
their results dropped from the last request, which offers no tools, the line that names the
reply's language after a tool result of the turn, and on every request under
`llm.reply_line_always`, the language alone where no result came before (agent/prompt.py's
docstring), and the `llm` group's model, effort and output bound.
"""

from __future__ import annotations

from collections.abc import Sequence

from t2_agentic_voice.agent.context import without_calls
from t2_agentic_voice.agent.prompt import reply_line, with_first_line
from t2_agentic_voice.core.settings.llm import REASONING_MODELS, LlmSettings
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.ports.chat_model import ChatMessage, ChatRequest, ToolSchema
from t2_agentic_voice.domain.text.arabic_numbers import Register


def request_of(
    llm: LlmSettings,
    messages: Sequence[ChatMessage],
    tools: tuple[ToolSchema, ...],
    *,
    after_tools: bool,
    language: LanguageTag,
    register: Register,
) -> ChatRequest:
    """The request of `messages`, offering `tools`, in a reply in `language` and `register`;
    `after_tools` when a tool result of the turn came before it (the module's docstring)."""
    if llm.vary_first_line:  # so no two requests share a cached prefix (the setting's text)
        messages = [ChatMessage.system(with_first_line(messages[0].content)), *messages[1:]]
    if not tools:
        messages = without_calls(messages)
    if after_tools or llm.reply_line_always:  # the request's own, never kept in the turn's
        line = reply_line(language, register, last=not tools, after_results=after_tools)
        messages = [*messages, ChatMessage.system(line)]
    return ChatRequest(
        messages=tuple(messages),
        tools=tools,
        model=llm.model,
        reasoning_effort=llm.reasoning_effort if llm.model in REASONING_MODELS else None,
        max_output_tokens=llm.max_output_tokens,
    )
