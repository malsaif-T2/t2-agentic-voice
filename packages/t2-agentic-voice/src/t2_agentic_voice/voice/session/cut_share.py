"""How much of a clause the caller heard when a stop or the call's end cut it, for speaker.py's
`Speaker`, which marks the clause cut in the heard history with that share (history.py).

It is the agent's audio the output sent since that clause began playing (its first audio queued,
or the clause before it ended: `AgentAudio` reaches the session in order with each clause's
`ClausePlayed`, voice/transport.py's `OutputTap`), over the clause's length, estimated from this
call's clauses played so far, seconds per caption character (`SECONDS_PER_CHARACTER` before any
played), as a reply's share counts.
"""

from __future__ import annotations

from t2_agentic_voice.voice.session.playback import Clause
from t2_agentic_voice.voice.session.session_events import AgentAudio

# How long a clause's audio lasts per character of its caption until a clause of the call has
# played (the agent's estimate: about 14 characters a second, a calm speaking rate), for the share
# of a clause cut before any other played.
SECONDS_PER_CHARACTER = 0.07


class CutShare:
    """One call's measure of the clause playing (the module's docstring): the agent's audio sent
    since it began, and the seconds per character of the clauses played whole so far."""

    def __init__(self) -> None:
        self._since_s = 0.0  # the agent's audio sent since the clause playing began
        self._played_s, self._played_chars = 0.0, 0  # the clauses played whole so far

    def heard(self, event: AgentAudio) -> None:
        """The output sent a piece of the agent's audio: counted toward the clause playing."""
        if event.sample_rate > 0:
            self._since_s += len(event.pcm16) / 2 / event.sample_rate

    def restart(self) -> None:
        """The agent's audio counts from here: a clause began to play, or one ended or was cut."""
        self._since_s = 0.0

    def played(self, clause: Clause, audio_s: float) -> None:
        """`clause` played whole, with `audio_s` of audio: its length counts toward the rate."""
        if audio_s > 0:
            self._played_s += audio_s
            self._played_chars += len(clause.caption)

    def fraction(self, clause: Clause) -> float:
        """The share of `clause`, the one playing, heard so far."""
        return self._since_s / self._length_s(clause)

    def _length_s(self, clause: Clause) -> float:
        """How long `clause`'s audio lasts, estimated by its caption's characters."""
        rate = self._played_s / self._played_chars if self._played_chars else SECONDS_PER_CHARACTER
        return max(rate * len(clause.caption), 1e-3)
