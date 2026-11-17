"""The longer wait while an action's read-back awaits its answer (plan 010's 1.11, the owner's Q9),
held by call_life.py's `CallLife` and brought up to date by call.py after each step: with
`turns.read_back_silence_ms` set, the session tells the Pipecat side (`ReadBackWait`) each time
the call starts or ends confirming (read_back.py's `Confirming.active`), so a turn said
meanwhile ends at that silence, not at `turns.max_silence_ms` (voice/turn_hold.py), and "yes,
[pause] but change ..." is not cut after the yes when the fallback is short. Unset, nothing is
told, and every turn waits `max_silence_ms`, as before.
"""

from __future__ import annotations

from t2_agentic_voice.voice.session.commands import ReadBackWait
from t2_agentic_voice.voice.session.io import CallSetup, Commands


class ReadBackWaits:
    """What one call (`setup`) has told the Pipecat side through `commands` of a read-back
    awaiting its answer (the module's docstring)."""

    def __init__(self, setup: CallSetup, commands: Commands) -> None:
        self._commands = commands
        self._on = setup.settings.turns.read_back_silence_ms is not None
        self._told = False

    async def tell(self, confirming: bool) -> bool:
        """Tell the Pipecat side whether a read-back awaits its answer (`confirming`) when that
        changed since it was last told and the setting is set; `confirming`, for the caller's
        own use."""
        if self._on and confirming != self._told:
            self._told = confirming
            await self._commands.run(ReadBackWait(waiting=confirming))
        return confirming
