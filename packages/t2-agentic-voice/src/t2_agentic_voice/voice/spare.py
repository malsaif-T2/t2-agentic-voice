"""One thing made ahead of its use, off the event loop (TD-089): voice/calls.py keeps a call's
speech detector and turn analyzer made this way, so a call's offer does not wait for their ONNX
sessions to load (85 to 135 ms each on the owner's machine).

`Spare(make)` holds nothing until `fill`, which makes one in a thread. `take` hands over the one
it holds and makes the next in the background, in a thread; when it holds none (none filled yet,
or two offers close together), it makes one for the caller in a thread, as before, so an error
of `make` reaches the caller that needs it. A background make that fails is logged by its type
and leaves the spare empty, so the next `take` makes its own. `aclose` drops the one it holds
and stops waiting for a make in flight (a thread cannot be stopped; what it makes is dropped).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from t2_agentic_voice.core.logging import get_logger

log = get_logger(__name__)


class Spare[T]:
    """One `T` from `make` kept ready (the module's docstring)."""

    def __init__(self, make: Callable[[], T]) -> None:
        self._make = make
        self._held: T | None = None
        self._making: asyncio.Task[None] | None = None
        self._open = True

    async def fill(self) -> None:
        """Make one now, in a thread, unless one is held; an error of `make` is raised."""
        self._open = True
        if self._held is None:
            self._held = await asyncio.to_thread(self._make)

    async def take(self) -> T:
        """The one held, the next made in the background; else one made now, in a thread."""
        held, self._held = self._held, None
        if held is None:
            return await asyncio.to_thread(self._make)
        if self._making is None or self._making.done():
            self._making = asyncio.create_task(self._refilled(), name="t2v-spare")
        return held

    async def aclose(self) -> None:
        """Drop the one held and stop waiting for a make in flight."""
        self._open = False
        self._held = None
        making, self._making = self._making, None
        if making is not None and not making.done():
            making.cancel()
            await asyncio.gather(making, return_exceptions=True)

    async def _refilled(self) -> None:
        try:
            made = await asyncio.to_thread(self._make)
        except Exception as error:  # the next take makes its own, and raises it there
            log.warning("spare_not_made", error=type(error).__name__)
            return
        if self._open and self._held is None:
            self._held = made
