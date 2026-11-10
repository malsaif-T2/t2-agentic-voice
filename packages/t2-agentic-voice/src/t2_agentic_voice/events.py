"""What a call reports to a team's observers (the design's 6.6): the frozen events, the talker's
among them (a tool call begun and ended, a clause the output guard blocked), an action's (a
read-back requested and answered, a write completed or unconfirmed), `Event`, the base
every one extends, which `runtime.on` takes too, and the `CallReport` that `CallEnded` carries,
with the parts it is made of. Provisional (the design's 5.1). A facade: it only re-exports
(ARCH-FACADE)."""

from t2_agentic_voice.core.events import (
    ActionCompleted,
    ActionUnconfirmed,
    AgentSpeechEnded,
    CallEnded,
    CallReport,
    CallStarted,
    ClientConnection,
    ConfirmationAnswered,
    ConfirmationRequested,
    Event,
    GuardBlocked,
    Interrupted,
    ModelUsage,
    ProviderFailed,
    ToolFinished,
    ToolStarted,
    TransportFailed,
    TurnMetrics,
    TurnRecord,
    TurnTimes,
    UserTurnEnded,
)

__all__ = [
    "ActionCompleted",
    "ActionUnconfirmed",
    "AgentSpeechEnded",
    "CallEnded",
    "CallReport",
    "CallStarted",
    "ClientConnection",
    "ConfirmationAnswered",
    "ConfirmationRequested",
    "Event",
    "GuardBlocked",
    "Interrupted",
    "ModelUsage",
    "ProviderFailed",
    "ToolFinished",
    "ToolStarted",
    "TransportFailed",
    "TurnMetrics",
    "TurnRecord",
    "TurnTimes",
    "UserTurnEnded",
]
