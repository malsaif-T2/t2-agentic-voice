"""What a call reports to a team's observers (the design's 6.6): the frozen events, `Event`, the
base every one extends, which `runtime.on` takes too, and the `CallReport` that `CallEnded`
carries, with the parts it is made of. Provisional (the design's 5.1). A facade: it only
re-exports (ARCH-FACADE)."""

from t2_agentic_voice.core.events import (
    AgentSpeechEnded,
    CallEnded,
    CallReport,
    CallStarted,
    ClientConnection,
    Event,
    Interrupted,
    ModelUsage,
    ProviderFailed,
    TransportFailed,
    TurnMetrics,
    TurnRecord,
    TurnTimes,
    UserTurnEnded,
)

__all__ = [
    "AgentSpeechEnded",
    "CallEnded",
    "CallReport",
    "CallStarted",
    "ClientConnection",
    "Event",
    "Interrupted",
    "ModelUsage",
    "ProviderFailed",
    "TransportFailed",
    "TurnMetrics",
    "TurnRecord",
    "TurnTimes",
    "UserTurnEnded",
]
