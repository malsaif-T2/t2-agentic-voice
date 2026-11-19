"""What a call ran on (`call_setup`), kept in each call's row of the call log: the agent's name
and version, the flight data's source, the talker's model, the speech-to-text, the voice, the
register held, and the release (the git commit the server runs, when it runs from a checkout).
No key, no access code, no URL: only names a setting chooses."""

from __future__ import annotations

import subprocess
from pathlib import Path

from pydantic import JsonValue
from t2_agentic_voice import VoiceAgent, VoiceSettings

from flight_voice.flight_data.settings import FlightDataFields

__all__ = ["call_setup", "release"]


def release(folder: Path | None = None) -> str | None:
    """The git commit the code runs from (`folder` the app's package), or None when it is not a
    git checkout or git cannot say within two seconds."""
    here = folder or Path(__file__).resolve().parent
    try:
        done = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],  # noqa: S607 (git on the PATH)
            cwd=here,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = done.stdout.strip()
    return commit if done.returncode == 0 and commit else None


def call_setup(
    agent: VoiceAgent, voice: VoiceSettings, app: FlightDataFields, commit: str | None
) -> dict[str, JsonValue]:
    """The setup each call of `agent` runs on, from the settings (the module's docstring)."""
    return {
        "agent": agent.name,
        "agent_version": agent.version,
        "flight_data": app.flight_data,
        "llm": {
            "provider": voice.llm.provider,
            "model": voice.llm.model,
            "reasoning_effort": voice.llm.reasoning_effort,
        },
        "stt": {
            "provider": voice.stt.provider,
            "model": voice.stt.model if voice.stt.provider == "groq" else None,  # Whisper's alone
            "live_language": voice.stt.live_language,
            "streaming": voice.stt.streaming,
        },
        "tts": {
            "provider": voice.tts.provider,
            "voices": {tag: v.model_dump() for tag, v in voice.tts.languages.items()},
        },
        "register": voice.words.fixed_register,
        "record_audio": voice.privacy.record_audio,
        "release": commit,
    }
