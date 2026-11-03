"""What the tests of the measurements on the file-fed pipeline share (test_turns.py,
test_echo_timing.py): a fake `VoiceCalls` and a fake `feed_file`, so no model loads and no time
passes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from t2_agentic_voice.domain.ports.speech_to_text import AudioClip
from t2_agentic_voice.voice.file_transport import FedCall


@dataclass
class FakeVoiceCalls:
    """Stands in for `VoiceCalls`: keeps what it was built with, and whether it was started and
    closed."""

    built: dict[str, Any]
    started: int = 0
    closed: int = 0

    async def start(self) -> None:
        self.started += 1

    async def aclose(self) -> None:
        self.closed += 1


@dataclass
class FakeFeed:
    """Stands in for `feed_file`: each call returns the next of `calls`, keeping what it was
    asked."""

    calls: list[FedCall]
    asked: list[dict[str, Any]] = field(default_factory=list)
    built: list[FakeVoiceCalls] = field(default_factory=list)

    def voice_calls(self, **built: Any) -> FakeVoiceCalls:
        made = FakeVoiceCalls(built)
        self.built.append(made)
        return made

    async def __call__(self, calls: FakeVoiceCalls, clip: AudioClip, **asked: Any) -> FedCall:
        assert calls.started == 1 and not calls.closed
        self.asked.append({"clip": clip, **asked})
        return self.calls.pop(0)
