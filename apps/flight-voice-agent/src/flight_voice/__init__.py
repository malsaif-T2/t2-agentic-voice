"""The flight-booking voice agent: a mock airline's booking line, built on T2 Agentic Voice
(D-101), the main agent shown and worked on, with the Ole5 app as the check that a change to
the library is general.

It uses only the library's public API, as a teammate's app would (ARCH-PUBLIC), and imports no
other app. It holds the mock airline (`airline/`: its airports, schedule, fares, dates, the
demo traveler, the bookings store and the facade the tools call), exact and deterministic, so
every fact a call says can be checked in code.
"""

# The app's loggers, which each command sends to its output with the library's
# (`configure_logging(loggers=LOGGERS)`): its package's, which each module's
# `get_logger(__name__)` sits under, and a command's own, `__main__` when it runs as
# `python -m`.
LOGGERS = (__name__, "__main__")
