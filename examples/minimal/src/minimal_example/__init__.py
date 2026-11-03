"""The smallest app on T2 Agentic Voice: an echo agent, the guide's quickstart.

It is a test of the library too: it uses only the public API and no Ole5 code, so a library
change that quietly depends on Ole5 breaks it. `app.py` declares the agent and makes its runtime
(`make_runtime`); `__main__.py` starts it, `python -m minimal_example`, or `t2v dev
minimal_example.app:make_runtime` serves it with its dev page. It grows with the library,
staying the shortest working example.
"""

# The example's loggers, which it sends to its output with the library's
# (`configure_logging(loggers=LOGGERS)`): its package's, which each module's
# `get_logger(__name__)` sits under, and `__main__`, its own when it runs as `python -m`.
LOGGERS = (__name__, "__main__")
