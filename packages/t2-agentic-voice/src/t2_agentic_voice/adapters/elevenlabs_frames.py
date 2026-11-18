"""What ElevenLabs' Text-to-Dialogue socket is sent and sends, as one call's session reads it
(adapters/elevenlabs_stream.py, D-121; ElevenLabs' reference, read 2026-11-18):

- `voices_message`, the socket's first: the voice it registers (`{"voices": [id]}`).
- `clause_message`, one clause, flushed: `{"inputs": [{"text", "voice_id", "new_turn"}],
  "flush": true}`, its text ended with a space so the next clause does not run into it.
- `KEEP_ALIVE`, which resets the server's 20 s idle limit and makes no audio.
- `Frame`, each frame the server sends: base64 audio in `audio`, the clause's end in
  `is_final_audio_for_turn` (or `is_final`, the session's), or an error (`message`, `error`,
  `code`), whose `refusal` keeps its machine name alone, never its message:
  `too_many_concurrent_requests` (the dialogue sessions' own pool is full) is rate-limited, a
  refused key or spent credit, or a policy close, rejected, any other a server error. A frame
  that is not ElevenLabs' is an `AnswerError`.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Final

from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError

from t2_agentic_voice.adapters.provider_http import AnswerError
from t2_agentic_voice.core.errors import ProviderError

PROVIDER: Final = "elevenlabs"
KEEP_ALIVE: Final = json.dumps({"keep_alive": True})
_BUSY: Final = frozenset({"too_many_concurrent_requests", "rate_limit_exceeded"})
_REFUSED: Final = frozenset(
    {"authentication_required", "invalid_api_key", "unauthorized", "quota_exceeded"}
)
_REFUSED_CODES: Final = frozenset({1008, 4001, 4003})
_NAME: Final = re.compile(r"[a-z0-9_]{1,64}")  # a machine name, never a message


def voices_message(voice: str) -> str:
    """The socket's first message, registering `voice`."""
    return json.dumps({"voices": [voice]})


def clause_message(text: str, voice: str, *, new_turn: bool) -> str:
    """The message that says one clause, flushed (the module's docstring)."""
    piece: dict[str, JsonValue] = {"text": text if text[-1:].isspace() else f"{text} "}
    piece["voice_id"] = voice
    if new_turn:
        piece["new_turn"] = True
    return json.dumps({"inputs": [piece], "flush": True})


def details(error: str) -> dict[str, JsonValue]:
    """A failure's details: the provider and the failure's name, no key or text."""
    return {"provider": PROVIDER, "error": error}


class Frame(BaseModel):
    """One frame of ElevenLabs', as far as the session reads it; other fields are ignored."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    audio: str | None = None
    is_final_audio_for_turn: bool | None = None
    is_final: bool | None = None
    error: JsonValue = None
    code: int | None = None

    @property
    def ends(self) -> bool:
        """Whether it is the clause's last."""
        return bool(self.is_final_audio_for_turn or self.is_final)

    @classmethod
    def read(cls, raw: str | bytes) -> Frame:
        try:
            return cls.model_validate_json(raw)
        except ValidationError:
            raise AnswerError("unreadable_frame") from None

    def pcm(self) -> bytes:
        """The frame's audio, decoded; none for a frame with no audio."""
        try:
            return base64.b64decode(self.audio or "", validate=True)
        except (binascii.Error, ValueError):
            raise AnswerError("unreadable_audio") from None

    def refusal(self) -> ProviderError:
        """An error frame's ProviderError, by its machine name alone (the module's docstring)."""
        error = self.error
        name = error if isinstance(error, str) and _NAME.fullmatch(error) else "error_frame"
        if name in _BUSY:
            return ProviderError("rate_limited", True, details=details(name))
        if name in _REFUSED or self.code in _REFUSED_CODES:
            return ProviderError("rejected", False, details=details(name))
        return ProviderError("server_error", False, details=details(name))
