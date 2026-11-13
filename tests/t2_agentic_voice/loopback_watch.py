"""How plan 005's loopback check (test_loopback_interruptions.py) watches the server side of a
call: what the session gave, where Pipecat's interruptions came from, and when the agent's audio
left. Each watch wraps the real method and calls it, with no change to what it does; every time
is `time.perf_counter`'s, the session's clock (io.py).

What the server sent is read where Pipecat's SmallWebRTC hands aiortc each 10 ms of the agent's
audio (its `RawAudioTrack`), after which aiortc only encodes and sends it.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, cast

import pytest
from t2_agentic_voice.voice.session.commands import Command, HearOverlap, Send, StopSpeaking
from t2_agentic_voice.voice.session_bridge import SessionCommands

from tests.t2_agentic_voice.fakes import quiet_pipecat
from tests.t2_agentic_voice.loopback_audio import Frame, pitch

quiet_pipecat()

from pipecat.frames.frames import InterruptionFrame  # noqa: E402 - after quiet_pipecat()
from pipecat.processors.frame_processor import FrameProcessor  # noqa: E402 - after quiet_pipecat()
from pipecat.transports.base_output import BaseOutputTransport  # noqa: E402 - after quiet_pipecat()
from pipecat.transports.smallwebrtc.transport import (  # noqa: E402 - after quiet_pipecat()
    RawAudioTrack,
)

_Sender = BaseOutputTransport.MediaSender


@dataclass
class Watched:
    """What the server side of a call did, each with when: each command the session gave
    (`given`); each processor that broadcast Pipecat's interruption (`broadcasts`); when each
    `InterruptionFrame` was made, wherever (`interruptions`); when the output transport handled
    each (`reached`); and each 10 ms of the agent's audio its WebRTC track gave aiortc, and
    whether it was loud (`sent`)."""

    given: list[tuple[float, Command]] = field(default_factory=list)
    broadcasts: list[str] = field(default_factory=list)
    interruptions: list[float] = field(default_factory=list)
    reached: list[float] = field(default_factory=list)
    sent: list[tuple[float, bool]] = field(default_factory=list)

    def stops(self) -> list[float]:
        """When the session gave each `StopSpeaking`."""
        return [at for at, command in self.given if isinstance(command, StopSpeaking)]

    def named(self) -> list[str]:
        """The overlaps' commands, in order: each `duck` and `unduck` by its message's type,
        each `HearOverlap` and `StopSpeaking` by its own name."""
        names: list[str] = []
        for _, command in self.given:
            if isinstance(command, Send) and command.message.type in ("duck", "unduck"):
                names.append(command.message.type)
            elif isinstance(command, HearOverlap | StopSpeaking):
                names.append(type(command).__name__)
        return names

    def loud_after(self, at: float) -> list[float]:
        """When each loud 10 ms of the agent's audio left the track after `at`."""
        return [sent for sent, loud in self.sent if loud and sent > at]


def watch(monkeypatch: pytest.MonkeyPatch) -> Watched:
    """Watch the server side of the calls this test makes, as `Watched` says."""
    watched = Watched()
    # The real methods, typed as they are called here (Pipecat leaves three unannotated).
    run = SessionCommands.run
    broadcast = cast(
        Callable[[FrameProcessor], Awaitable[None]], FrameProcessor.broadcast_interruption
    )
    made = cast(Callable[[InterruptionFrame], None], InterruptionFrame.__post_init__)
    handle = cast(Callable[[Any, InterruptionFrame], Awaitable[None]], _Sender.handle_interruptions)
    recv = cast(Callable[[RawAudioTrack], Awaitable[Any]], RawAudioTrack.recv)

    async def running(self: SessionCommands, command: Command) -> None:
        watched.given.append((time.perf_counter(), command))
        await run(self, command)

    async def broadcasting(self: FrameProcessor) -> None:
        watched.broadcasts.append(self.name)
        await broadcast(self)

    def making(self: InterruptionFrame) -> None:
        made(self)
        watched.interruptions.append(time.perf_counter())

    async def handling(self: Any, frame: InterruptionFrame) -> None:
        watched.reached.append(time.perf_counter())
        await handle(self, frame)

    async def sending(self: RawAudioTrack) -> Any:  # a PyAV frame
        frame = await recv(self)
        watched.sent.append((time.perf_counter(), pitch(cast(Frame, frame)) is not None))
        return frame

    monkeypatch.setattr(SessionCommands, "run", running)
    monkeypatch.setattr(FrameProcessor, "broadcast_interruption", broadcasting)
    monkeypatch.setattr(InterruptionFrame, "__post_init__", making)
    monkeypatch.setattr(_Sender, "handle_interruptions", handling)
    monkeypatch.setattr(RawAudioTrack, "recv", sending)
    return watched
