"""voice/session: one call's session, which imports no Pipecat (the design's 12.2; ARCH-BAN).

Turn order, the echo, Stop and `hangup`, heard words, playback bookkeeping, usage, the call's
report and its recording. It meets voice's Pipecat modules only through its events
(`session_events.py`) and commands (`commands.py`), and the protocols, the clock and the set-up
of `io.py`, so a call fed from text or a file runs the same session code as a call over WebRTC.
The session is `call.py`'s `CallSession`; the echo's replies are `echo.py`'s, the heard words
`heard.py`'s, the replies as they play and the speaker `playback.py`'s, the usage `usage.py`'s,
the turns, public events and report `report.py`'s, and the recorder `recording.py`'s.
"""
