"""voice/session: one call's session, which imports no Pipecat (the design's 12.2; ARCH-BAN).

Turn order, the echo, Stop and `hangup`, heard words, playback bookkeeping, usage, the call's
report and its recording. It meets voice's Pipecat modules only through its events
(`session_events.py`) and commands (`commands.py`), and the protocols, the clock and the set-up
of `io.py`, so a call fed from text or a file runs the same session code as a call over WebRTC.
The session is `call.py`'s `CallSession`; the echo's replies are `echo.py`'s, the heard words
`heard.py`'s, the replies as they play `playback.py`'s, the speaker `speaker.py`'s, the turns as
the session keeps them `turn_book.py`'s, its limit timers `limits.py`'s, the usage `usage.py`'s,
the turn records, public events and report `report.py`'s, and the recorder `recording.py`'s.
Plan 005 adds each reply's cancel scope (`scope.py`), the heard history (`history.py`), the
overlaps under `interruptions.mode = "two_step"` (`overlap.py`, carried out by
`interrupter.py`), and the call's books that its parts share (`books.py`). Plan 006 adds the
talker in the call (`talking.py`, each of its events played by `talker_play.py`), its replies
spoken while they are written (`open_reply.py`), the early start in Smart Turn's hold, and the
reply kept behind the caller's newer turn while it is open. Plan 007 adds an action's read-back,
the confirming state and its receipt (`read_back.py`), the caller's answer to it routed to the
yes rule (`yes_turns.py`), a confirmed action's job and its outcome (`action_job.py`), and splits
the no-talker overlap follow-ups from `interrupter.py` (`overlap_follow.py`) and the timed
progress line from `talking.py` (`talker_progress.py`).
"""
