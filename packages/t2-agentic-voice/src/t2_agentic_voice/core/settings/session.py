"""The `session` group: what answers the caller in a call.

`mode` is unset by default, which follows the declaration: an agent that declares instructions
(`VoiceAgent(instructions=...)`) runs the talker, and one that does not runs the echo, as every
agent did before the talker (plan 003, Q3). So no setting changes its meaning: unset still runs
an echo agent's echo, and `echo` still runs the echo, now for any agent, an agent with
instructions included (a team's first audio check). `talker` runs the talker, and is refused for
an agent that declares no instructions (`mode_for`).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.base import PREFIX, Group, setting_name

# What answers each turn: the echo, which says back what it heard (plan 003, Q3), or the talker,
# which answers with the chat model and the agent's tools (plan 006).
SessionMode = Literal["echo", "talker"]


class SessionSettings(Group):
    """The voice session: what answers the caller."""

    mode: SessionMode | None = Field(
        default=None,
        description=(
            "What answers each turn: echo, which says back what it heard, or talker, which "
            "answers with the chat model and the agent's tools. Unset: the declaration's, "
            "talker for an agent that declares instructions and echo for one that does not."
        ),
    )

    def mode_for(self, *, instructed: bool, prefix: str = PREFIX) -> SessionMode:
        """The mode a call of an agent runs in: `mode` when set, else talker for an agent that
        declares instructions (`instructed`) and echo for one that does not. ConfigurationError
        naming the setting under `prefix` for `talker` set for an agent with no instructions,
        which the talker cannot run."""
        if self.mode is None:
            return "talker" if instructed else "echo"
        if self.mode == "talker" and not instructed:
            name = setting_name("session", "mode", prefix=prefix)
            raise ConfigurationError(
                f"{name} is talker, but the agent declares no instructions for the talker. FIX: "
                "give the agent its instructions (VoiceAgent(instructions=...)), or leave "
                f"{name} unset.",
                details={"setting": name},
            )
        return self.mode
