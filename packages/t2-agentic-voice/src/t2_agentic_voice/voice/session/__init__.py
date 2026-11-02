"""voice/session: one call's session, which imports no Pipecat (the design's 12.2; ARCH-BAN).

Turn order, the echo, Stop and `hangup`, heard words, playback bookkeeping, usage, the call's
report and its recording. It meets voice's Pipecat modules only through `io.py`'s commands and
events, so a call fed from text or a file runs the same session code as a call over WebRTC.
Built so far: the commands and events (`io.py`), and the session's signature (`call.py`).
"""
