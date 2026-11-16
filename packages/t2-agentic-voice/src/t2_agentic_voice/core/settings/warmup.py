"""The `warmup` group: what the server readies before a caller waits for it (TD-089).

Each key changes how soon a call connects, which the warm-up's measurement reads (the evaluation
design's rule for a change to a measured outcome, GP-18): off by default, so a server runs as it
did until that measurement keeps it.
"""

from __future__ import annotations

from pydantic import Field

from t2_agentic_voice.core.settings.base import Group


class WarmupSettings(Group):
    """The warm-up: what the server's start readies for the calls to come."""

    at_start: bool = Field(
        default=False,
        description=(
            "Whether the server's start imports the modules a call's offer needs (Pipecat's "
            "pipeline, aiortc's peer) in a thread, and keeps one call's speech detector and turn "
            "analyzer made ahead, the next made in the background as each call takes one. Off: "
            "the first offer imports them on the event loop, and each call makes its own."
        ),
    )
