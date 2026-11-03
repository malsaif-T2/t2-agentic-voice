"""The `session` group: what answers the caller in a call."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from t2_agentic_voice.core.settings.base import Group

# What answers each turn: for now only the echo, which says back what it heard (plan 003, Q3);
# a talker comes later as another value.
SessionMode = Literal["echo"]


class SessionSettings(Group):
    """The voice session: what answers the caller."""

    mode: SessionMode = Field(
        default="echo",
        description="What answers each turn: echo, which says back what it heard, the only one.",
    )
