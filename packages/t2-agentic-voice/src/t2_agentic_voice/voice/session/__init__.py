"""voice/session: one call's session, which imports no Pipecat (the design's 12.2; ARCH-BAN).

Turn order, the echo, Stop and `hangup`, heard words, playback bookkeeping, usage, the call's
report and its recording. It meets voice's Pipecat modules only through its events
(`session_events.py`) and commands (`commands.py`), and the protocols, the clock and the set-up
of `io.py`, so a call fed from text or a file runs the same session code as a call over WebRTC.
The session is `call.py`'s `CallSession`; the echo's replies are `echo.py`'s, the heard words
`heard.py`'s, the replies as they play `playback.py`'s, the speaker `speaker.py`'s, the turns as
the session keeps them `turn_book.py`'s, its limit timers `limits.py`'s, the usage `usage.py`'s,
the turn records, public events and report `report.py`'s, and the recorder `recording.py`'s.
Plan 005 adds, as signatures so far, each reply's cancel scope (`scope.py`), the heard history
(`history.py`) and the overlaps (`overlap.py`).
"""
