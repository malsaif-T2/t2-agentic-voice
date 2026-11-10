"""The `limits` group: how long a call may last, brought forward for the owner's guard on the
shared key (plan 003, Q4), and the cap on actions per caller (plan 007), read from the outbox;
the rest of the design's 7.6 row comes with admission control."""

from __future__ import annotations

from pydantic import Field

from t2_agentic_voice.core.settings.base import Group


class LimitSettings(Group):
    """Limits on one call."""

    max_call_s: float = Field(
        default=600.0,
        gt=0,
        allow_inf_nan=False,
        description="The longest a call may last; the library ends it then.",
    )
    idle_s: float = Field(
        default=120.0,
        gt=0,
        allow_inf_nan=False,
        description="The longest a call may go with nothing heard from the caller; then it ends.",
    )
    actions_per_caller_per_day: int = Field(
        default=20,
        ge=1,
        description=(
            "How many of one kind of action one caller may have done in a day, counted from "
            "the outbox whatever became of them. Beyond it the action is refused before its "
            "read-back. The agent's starting value."
        ),
    )
