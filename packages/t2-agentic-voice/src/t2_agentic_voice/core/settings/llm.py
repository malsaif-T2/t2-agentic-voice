"""The `llm` group: the talker's chat model (the design's 7.6; plan 006), on Groq by default
(D-004), or on OpenAI's own API behind `provider` (D-112). Its defaults move only on a
registered measurement (GP-18): run K moved `reasoning_effort` to medium (D-074).

A model is reached through one provider (`PROVIDER_OF`), and the settings refuse a model the
chosen provider does not serve, and an effort its model does not take (`EFFORTS`), each with the
setting to change, so a wrong pair fails as the settings load, never at a call's first request.
"""

from __future__ import annotations

from typing import Final, Literal

from pydantic import Field, ValidationInfo, field_validator

from t2_agentic_voice.core.settings.base import Group

LlmProvider = Literal["groq", "openai"]
# Groq's production chat models, read on 2026-11-06 from its model list (plan 006's progress
# log): the arms the plan's runs compare. A preview model may change or go without notice. Then
# OpenAI's on its own API, read on 2026-11-17 from its model list (D-112): the candidates
# measured beside gpt-oss-120b.
LlmModel = Literal[
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gpt-6-luna",
    "gpt-5.6-luna",
    "gpt-5.4-mini",
    "gpt-6.1-terra",
]
# How hard a reasoning model thinks before it answers, as the providers' APIs name the levels:
# Groq's gpt-oss take low to high; OpenAI's `none` is no reasoning at all.
ReasoningEffort = Literal["none", "low", "medium", "high"]
# Which provider serves each model the settings name.
PROVIDER_OF: Final[dict[str, LlmProvider]] = {
    "openai/gpt-oss-120b": "groq",
    "openai/gpt-oss-20b": "groq",
    "llama-3.3-70b-versatile": "groq",
    "llama-3.1-8b-instant": "groq",
    "gpt-6-luna": "openai",
    "gpt-5.6-luna": "openai",
    "gpt-5.4-mini": "openai",
    "gpt-6.1-terra": "openai",
}
_GPT_OSS: Final[frozenset[ReasoningEffort]] = frozenset({"low", "medium", "high"})
_NONE: Final[frozenset[ReasoningEffort]] = frozenset({"none"})
# The efforts each reasoning model takes with the talker's tools: groq 1.7.0's reference for
# gpt-oss ("support 'low', 'medium', or 'high'"); OpenAI's Chat Completions, probed 2026-11-17,
# refuse function tools with any effort but `none` for gpt-5.4 and later ("To use function
# tools, use /v1/responses or set reasoning_effort to 'none'"), so its models take `none` alone.
EFFORTS: Final[dict[str, frozenset[ReasoningEffort]]] = {
    "openai/gpt-oss-120b": _GPT_OSS,
    "openai/gpt-oss-20b": _GPT_OSS,
    "gpt-6-luna": _NONE,
    "gpt-5.6-luna": _NONE,
    "gpt-5.4-mini": _NONE,
    "gpt-6.1-terra": _NONE,
}
# The models that take `reasoning_effort`; the others the settings name (the Llama models)
# refuse the field, so they are sent none.
REASONING_MODELS: Final[frozenset[str]] = frozenset(EFFORTS)


class LlmSettings(Group):
    """The chat model the talker writes its replies with: the adapter, the model, how much it
    reasons, the most it may write, how long a request may take, whether each request opens
    with a line of its own, and the most requests a turn."""

    provider: LlmProvider = Field(
        default="groq",
        description=(
            "Which adapter reaches the talker's chat model: groq (D-004), or openai, OpenAI's "
            "own API with the openai group's key (D-112), off by default. Under openai the yes "
            "rule's check and the uncertain overlap's request stay on Groq's gpt-oss-120b, "
            "so the Groq key is needed too."
        ),
    )
    model: LlmModel = Field(
        default="openai/gpt-oss-120b",
        validate_default=True,
        description=(
            "The chat model: on groq openai/gpt-oss-120b, openai/gpt-oss-20b, "
            "llama-3.3-70b-versatile or llama-3.1-8b-instant; on openai gpt-6-luna, "
            "gpt-5.6-luna, gpt-5.4-mini or gpt-6.1-terra. The default changes only on a "
            "registered measurement (GP-18)."
        ),
    )
    reasoning_effort: ReasoningEffort = Field(
        default="medium",
        validate_default=True,
        description=(
            "How much a reasoning model thinks before it answers: none, low, medium or high, "
            "as its model takes them (the gpt-oss models low to high; OpenAI's only none, the "
            "one its Chat Completions take with tools). Sent only to a model that takes it. "
            "Medium, as the owner ruled on run K's dev pass (plan 006, Q26): gpt-oss-120b "
            "invented 6 answers of 136 against 18 at low, for about 0.33 s more to the first "
            "clause."
        ),
    )
    max_output_tokens: int = Field(
        default=1024,
        ge=16,
        le=65_536,
        description=(
            "The most tokens one model request may write, its reasoning included: a spoken "
            "reply is one to three short sentences, or every step of a procedure."
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
            "on openai/gpt-oss-120b with one app's system prompt, 3 of the 8 requests it served "
            "from its cache took 1.03, 1.25 and 5.71 s to the first token, while 12 requests with "
            "a first line of their own all took 0.15 to 0.30 s (2026-11-07, D-072)."
        ),
    )
    max_requests_per_turn: int = Field(
        default=3,
        ge=2,
        le=5,
        description=(
            "The most model requests one turn makes: each but the last offers the agent's "
            "tools, the last none, so the turn ends in words."
        ),
    )

    @staticmethod
    def provider_of(model: str) -> LlmProvider:
        """The provider that serves `model`, one the settings name; groq for any other."""
        return PROVIDER_OF.get(model, "groq")

    @field_validator("model")
    @classmethod
    def _served(cls, model: LlmModel, info: ValidationInfo) -> LlmModel:
        """The model is the chosen provider's (the module's docstring)."""
        provider = info.data.get("provider")
        serves = PROVIDER_OF[model]
        if provider is not None and serves != provider:
            theirs = ", ".join(m for m, p in PROVIDER_OF.items() if p == provider)
            raise ValueError(
                f"{model} is served by {serves}, not {provider}. FIX: set llm.model to one of "
                f"{provider}'s ({theirs}), or llm.provider to {serves}"
            )
        return model

    @field_validator("reasoning_effort")
    @classmethod
    def _taken(cls, effort: ReasoningEffort, info: ValidationInfo) -> ReasoningEffort:
        """The effort is one its model takes (the module's docstring)."""
        takes = EFFORTS.get(info.data.get("model", ""))
        if takes is not None and effort not in takes:
            raise ValueError(
                f"{info.data['model']} takes {', '.join(sorted(takes))}, not {effort}. FIX: "
                "set llm.reasoning_effort to one of those"
            )
        return effort
