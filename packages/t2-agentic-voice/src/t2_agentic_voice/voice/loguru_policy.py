"""Pipecat's own log lines, which go through loguru, a logger for the whole process (plan 003,
Q2; D-031): `voice` owns loguru, and switches Pipecat's namespace off before it first imports
any Pipecat module, transitive ones included, so the banner Pipecat logs at its import never
prints, and none of its lines with call content (the text it speaks, a remote candidate's
address, a data-channel message) reaches a sink (docs/SECURITY.md, invariant 8). The package's
`__init__` calls `switch_pipecat_off` before any module under it is imported, and voice's entry
point calls it again at the runtime's start (`VoiceCalls.start`), as Q2 settled it.

`logging.pipecat = "off"` is the only value (Q19 is the owner's): loguru's switch for one
namespace, `logger.disable`, with no sink added or removed. A disabled name returns before any
sink sees the record (loguru 0.7.3's `_logger.py`, line 1995), so nothing of Pipecat's prints,
loguru's default sink included. Pipecat's failures stay visible as the library's own log lines
and events (`voice/pipecat_events.py`).
"""

from __future__ import annotations

from loguru import logger

# The namespace loguru matches: `pipecat` and every module under it (`pipecat.*`).
PIPECAT = "pipecat"


def switch_pipecat_off() -> None:
    """Switch Pipecat's loguru namespace off: no record of `pipecat` or a module under it
    reaches any sink from now on. Idempotent, and cheap enough to call again at start."""
    logger.disable(PIPECAT)
