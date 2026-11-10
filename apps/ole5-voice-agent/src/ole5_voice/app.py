"""The Ole5 app's composition: what it builds from the library.

It reports the library's status; the call, the talker, the knowledge base and the mock ticket
system are composed by the server (server.py).
"""

from __future__ import annotations

from t2_agentic_voice import Status, VoiceSettings, status


def health(settings: VoiceSettings) -> Status:
    """What the Ole5 app runs with."""
    return status(settings)
