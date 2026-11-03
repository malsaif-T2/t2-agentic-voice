"""The Ole5 app's composition: what it builds from the library.

For now it reports the library's status; the call, the talker, the knowledge base and the
ticket system are composed here as the library gains them.
"""

from __future__ import annotations

from t2_agentic_voice import Status, VoiceSettings, status


def health(settings: VoiceSettings) -> Status:
    """What the Ole5 app runs with."""
    return status(settings)
