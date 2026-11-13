"""T2 Agentic Voice: a library for speech-first voice agents.

This module and the facades beside it (`ports`, `groq`, `classifiers`, `identity`, `server`,
`stores`, `events`, `languages`, `evals`, `tracing`) are the library's public API (harness.toml
[package] public): an app imports from them, never from the layers inside, and ARCH-PUBLIC fails
an app that does.
The layers and their rules: ARCHITECTURE.md. Beside `VoiceSettings` sit its groups, so an app
can build one in code (`VoiceSettings(env="dev", server=ServerSettings(...))`), and beside
`get_logger` the logger it returns.

`VoiceRuntime` and `Providers` are imported when first named (`__getattr__`): the runtime's
module imports FastAPI, which costs seconds, so `import t2_agentic_voice` (an eval command, a
child process, `t2v --help`) imports neither, and naming `Providers` (api/providers.py) imports
no FastAPI either.
"""

import importlib
import warnings
from typing import TYPE_CHECKING, Any

from t2_agentic_voice.actions.action import Action, ActionContext, HeardConsent, action
from t2_agentic_voice.actions.knowledge import knowledge_tool
from t2_agentic_voice.actions.tools import (
    CallContext,
    FromCaller,
    RecordedAction,
    Tool,
    ToolResult,
    from_caller,
    tool,
)
from t2_agentic_voice.agent.prompt import render_prompt
from t2_agentic_voice.api.status import Status, status
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import ConversationLine
from t2_agentic_voice.core.errors import (
    ActionNotSent,
    ActionRejected,
    ConfigurationError,
    InvalidRequestError,
    JoinRejected,
    NotFoundError,
    ProviderError,
    T2VoiceError,
    ToolError,
)
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.logging import StructuredLogger, configure_logging, get_logger
from t2_agentic_voice.core.settings.groq import GroqSettings
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.core.settings.interruptions import InterruptionSettings
from t2_agentic_voice.core.settings.join import JoinSettings
from t2_agentic_voice.core.settings.limits import LimitSettings
from t2_agentic_voice.core.settings.llm import LlmSettings
from t2_agentic_voice.core.settings.logs import LoggingSettings
from t2_agentic_voice.core.settings.privacy import PrivacySettings
from t2_agentic_voice.core.settings.server import ServerSettings
from t2_agentic_voice.core.settings.session import SessionSettings
from t2_agentic_voice.core.settings.storage import StorageSettings
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.core.settings.tracing import TracingSettings
from t2_agentic_voice.core.settings.tts import TtsSettings, TtsVoice
from t2_agentic_voice.core.settings.turns import TurnSettings
from t2_agentic_voice.core.settings.words import WordSettings
from t2_agentic_voice.domain.action_declaration import Claims, ReadBack, Say, Spoken
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.talker_declaration import DeclaredTool, Vocabulary
from t2_agentic_voice.domain.words import Phrases, Words

if TYPE_CHECKING:
    from t2_agentic_voice.api.providers import Providers
    from t2_agentic_voice.api.runtime import VoiceRuntime

# The names imported when first named, by the module that defines them.
_LAZY = {
    "Providers": "t2_agentic_voice.api.providers",
    "VoiceRuntime": "t2_agentic_voice.api.runtime",
}

__all__ = [
    "Action",
    "ActionContext",
    "ActionNotSent",
    "ActionRejected",
    "CallContext",
    "Caller",
    "Card",
    "Claims",
    "ConfigurationError",
    "Consent",
    "ConversationLine",
    "DeclaredTool",
    "FromCaller",
    "GroqSettings",
    "GuardSettings",
    "HeardConsent",
    "InterruptionSettings",
    "InvalidRequestError",
    "JoinRejected",
    "JoinSettings",
    "Language",
    "LimitSettings",
    "LlmSettings",
    "LoggingSettings",
    "NotFoundError",
    "Phrases",
    "PrivacySettings",
    "ProviderError",
    "Providers",
    "ReadBack",
    "RecordedAction",
    "Say",
    "ServerSettings",
    "SessionSettings",
    "Spoken",
    "Status",
    "StorageSettings",
    "StructuredLogger",
    "SttSettings",
    "T2VoiceError",
    "Tool",
    "ToolError",
    "ToolResult",
    "TracingSettings",
    "TtsSettings",
    "TtsVoice",
    "TurnSettings",
    "Vocabulary",
    "VoiceAgent",
    "VoiceRuntime",
    "VoiceSettings",
    "WordSettings",
    "Words",
    "action",
    "configure_logging",
    "from_caller",
    "get_logger",
    "knowledge_tool",
    "render_prompt",
    "status",
    "tool",
]


def __getattr__(name: str) -> Any:
    """`VoiceRuntime` and `Providers`, imported when first named; and `AppError`, the base
    error's old name, which still works until the next minor release, with a DeprecationWarning
    (the design's 5.4; D-026)."""
    if name in _LAZY:
        return getattr(importlib.import_module(_LAZY[name]), name)
    if name == "AppError":
        warnings.warn(
            "t2_agentic_voice.AppError is deprecated: use T2VoiceError",
            DeprecationWarning,
            stacklevel=2,
        )
        return T2VoiceError
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
