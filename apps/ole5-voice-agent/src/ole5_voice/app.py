"""The Ole5 app's composition: what it builds from the library.

It reports the library's status; the call, the talker and the knowledge base are composed by
the server (server.py), and the ticket system will be.
"""

from __future__ import annotations

from t2_agentic_voice import Status, VoiceSettings, status


def health(settings: VoiceSettings) -> Status:
    """What the Ole5 app runs with."""
    return status(settings)
