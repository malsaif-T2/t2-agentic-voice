"""The `session` group: what answers the caller in a call.

`mode` is unset by default, which follows the declaration: an agent that declares instructions
(`VoiceAgent(instructions=...)`) runs the talker, and one that does not runs the echo, as every
agent did before the talker (plan 003, Q3). So no setting changes its meaning: unset still runs
an echo agent's echo, and `echo` still runs the echo, now for any agent, an agent with
instructions included (a team's first audio check). `talker` runs the talker, and is refused for
an agent that declares no instructions (`mode_for`).

`progress_beat_ms` is the silence after a tool's progress line, before the answer, counted from
the end of the line's speech, its take's own silence after it cut. Unset by default: the take as
it is, then the 400 ms beat around every fixed line said next to other speech (D-077), so a call
sounds as it did until a measurement keeps a shorter one (GP-18; plan 010's 1.15 asks for 100).

`early_over_reply` is off by default: a turn held while a reply to an earlier turn is still in
progress starts no talker early (TD-117), as before, until a measurement keeps it (plan 010's 2.2).
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
    progress_beat_ms: int | None = Field(
        default=None,
        ge=0,
        le=2000,
        description=(
            "The silence after a tool's progress line before the answer, in ms, counted from "
            "the end of the line's speech: the take's own silence after it is cut first. "
            "Unset: the take as it is, then 400 ms, the beat around every fixed line said next "
            "to other speech."
        ),
    )

    early_over_reply: bool = Field(
        default=False,
        description=(
            "Whether a turn held while a reply to an earlier turn is still in progress (nothing "
            "of it playing as the turn began) starts the talker early too: that reply is "
            "stopped as the turn's held words come, as the turn's answer would stop it, so the "
            "talker reads it as cut. Off: such a turn starts the talker once it has ended."
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
