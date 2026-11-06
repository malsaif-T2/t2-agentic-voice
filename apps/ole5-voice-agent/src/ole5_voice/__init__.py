"""Ole5 Voice Agent: a voice-first support assistant for Ole5, built on T2 Agentic Voice.

It uses only the library's public API, as a teammate's app would (ARCH-PUBLIC). It holds its
server (`server.py`, with the token route and the widget's files), its settings, Ole5's agents
(`agent.py`: the talker, with Ole5's instructions and its search of the knowledge base, and the
echo), its knowledge base adapter (`knowledge_base.py`, `passages.py`) and `evals/`, the
commands that measure the library on Ole5's own speech and questions. The ticket system is
still to come.
"""

# The app's loggers, which each command sends to its output with the library's
# (`configure_logging(loggers=LOGGERS)`): its package's, which each module's
# `get_logger(__name__)` sits under, and a command's own, `__main__` when it runs as
# `python -m`, as its poe task runs it.
LOGGERS = (__name__, "__main__")
