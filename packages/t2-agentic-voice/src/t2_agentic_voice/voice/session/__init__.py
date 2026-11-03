"""voice/session: one call's session, which imports no Pipecat (the design's 12.2; ARCH-BAN).

Turn order, the echo, Stop and `hangup`, heard words, playback bookkeeping, usage, the call's
report and its recording. It meets voice's Pipecat modules only through its events
(`session_events.py`) and commands (`commands.py`), and the protocols, the clock and the set-up
of `io.py`, so a call fed from text or a file runs the same session code as a call over WebRTC.
Built so far: those three modules, and the session's signature (`call.py`).
"""
