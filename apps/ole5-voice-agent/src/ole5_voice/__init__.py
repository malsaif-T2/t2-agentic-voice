"""Ole5 Voice Agent: a voice-first support assistant for Ole5, built on T2 Agentic Voice.

It uses only the library's public API, as a teammate's app would (ARCH-PUBLIC). Today it holds
the composition stub (`app.py`, which reports the library's status) and `evals/`, the golden
set's commands, which measure the library's speech-to-text on Ole5's own speech. What it will
add is Ole5's own: the talker's prompt, its tools, the knowledge base and the ticket system.
"""

# The app's loggers, which each command sends to its output with the library's
# (`configure_logging(loggers=LOGGERS)`): its package's, which each module's
# `get_logger(__name__)` sits under, and a command's own, `__main__` when it runs as
# `python -m`, as its poe task runs it.
LOGGERS = (__name__, "__main__")
