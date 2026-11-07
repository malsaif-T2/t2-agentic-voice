"""The `llm` group: the talker's chat model (the design's 7.6; plan 006), on Groq, the only
provider for now (D-004). Its defaults are the agent's starting values: `model` and
`reasoning_effort` move only on the plan's registered run K (GP-18)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from t2_agentic_voice.core.settings.base import Group

LlmProvider = Literal["groq"]
# Groq's production chat models, read on 2026-11-06 from its model list (plan 006's progress
# log): the arms the plan's runs compare. A preview model may change or go without notice.
LlmModel = Literal[
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]
# How hard a reasoning model thinks before it answers, as Groq's API names the levels.
ReasoningEffort = Literal["low", "medium", "high"]


class LlmSettings(Group):
    """The chat model the talker writes its replies with: the adapter, the model, how much it
    reasons, the most it may write, how long a request may take, and whether each request opens
    with a line of its own."""

    provider: LlmProvider = Field(
        default="groq",
        description="Which adapter reaches the chat model; only Groq's exists for now (D-004).",
    )
    model: LlmModel = Field(
        default="openai/gpt-oss-120b",
        description=(
            "The chat model: openai/gpt-oss-120b, openai/gpt-oss-20b, llama-3.3-70b-versatile "
            "or llama-3.1-8b-instant. The default changes only on a registered measurement "
            "(GP-18)."
        ),
    )
    reasoning_effort: ReasoningEffort = Field(
        default="low",
        description=(
            "How much a reasoning model thinks before it answers: low, medium or high. Sent "
            "only to a model that takes it (the gpt-oss models); low keeps the first clause "
            "soon."
        ),
    )
    max_output_tokens: int = Field(
        default=1024,
        ge=16,
        le=65_536,
        description=(
            "The most tokens one model request may write, its reasoning included: a spoken "
            "reply is one to three short sentences, and the steps go to the screen."
        ),
    )
    timeout_s: float = Field(
        default=8.0,
        gt=0,
        allow_inf_nan=False,
        description="The longest one model request may take before it is a timeout.",
    )
    vary_first_line: bool = Field(
        default=True,
        description=(
            "Whether each request's system message opens with a line new on every request, so "
            "no two requests share a prefix the provider has cached. Groq's cache can be slow: "
            "on openai/gpt-oss-120b with one 3,617-character prompt, 3 of the 8 requests it "
            "served from its cache took 1.03, 1.25 and 5.71 s to the first token, while 12 "
            "requests with a first line of their own all took 0.15 to 0.30 s (2026-11-07)."
        ),
    )
