"""The smallest app on T2 Agentic Voice.

It is the guide's quickstart and a test of the library: it uses only the public API and no Ole5
code, so a library change that quietly depends on Ole5 breaks it. It grows with the library,
staying the shortest working example (one tool, a short prompt).
"""

from __future__ import annotations

from t2_agentic_voice import Status, VoiceSettings, status


def run(settings: VoiceSettings) -> Status:
    """Start the example with `settings`; for now, report what it runs with."""
    return status(settings)
