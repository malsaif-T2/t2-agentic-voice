"""The numbers that name a call's parts, which every layer shares: a call's ID, a turn's, a
reply's and a clause's, with the bounds a client's message keeps. The call's events and its
report are built on them (core/events.py, core/call_report.py), and core/events.py re-exports
each, where every layer reads them.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

# A call's ID: URL-safe characters, as the router mints it. It names the call in traces
# (`session.id`), events, logs and the `hello` message, so it is never a credential (the
# design's 5.5).
CALL_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
# The largest turn number or index a message may carry: a 32-bit signed integer's, which every
# client language holds exactly.
MAX_INDEX = 2**31 - 1
# The longest duration a client reports, in milliseconds: a day (the agent's bound, far over
# any call).
MAX_MS = 86_400_000.0

CallId = Annotated[str, Field(pattern=CALL_ID_PATTERN)]
# A turn's number in its call, from 0, as the speech-to-text bridge stamps it.
TurnId = Annotated[int, Field(ge=0, le=MAX_INDEX)]
# A reply's number in its call, from 0, as the session counts them: the greeting is reply 0.
ReplyId = Annotated[int, Field(ge=0, le=MAX_INDEX)]
# A clause's index in its reply, from 0.
ClauseIndex = Annotated[int, Field(ge=0, le=MAX_INDEX)]
