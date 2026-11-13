"""voice/session: one call's session, which imports no Pipecat (ARCH-BAN): turn order, the
interruptions, the talker in the call, an action's read-back and the caller's answer to it, and
the call's books (its usage, report, recording and heard history). It meets voice's Pipecat
modules only through io.py's protocols, its events and its commands, so a call fed from text or a
file runs the same session code as a call over WebRTC.

ARCHITECTURE.md's "Layers" maps the layers and what each owns; each module's docstring says what
it holds.
"""
