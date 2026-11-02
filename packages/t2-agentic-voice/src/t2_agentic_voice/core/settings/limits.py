"""The `limits` group: how long a call may last. Only these two keys so far, brought forward
for the owner's guard on the shared key (plan 003, Q4); the rest of the design's 7.6 row
comes with admission control."""

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
