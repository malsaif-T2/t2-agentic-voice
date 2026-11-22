"""What one call's session keeps as it goes (voice/session/call.py), handed to each of its parts
(the speaker, the turns, the overlaps) as one: each model's usage (usage.py), the call's traces
(core/tracing_tts.py), its recorder (recording.py), its public events (report.py) and what the
caller heard (history.py).
"""

from __future__ import annotations

from dataclasses import dataclass

from t2_agentic_voice.core.tracing_tts import CallTrace, resource_attributes
from t2_agentic_voice.voice.session.history import HeardHistory
from t2_agentic_voice.voice.session.io import CallSetup
from t2_agentic_voice.voice.session.recording import CallRecorder
from t2_agentic_voice.voice.session.report import CallEvents
from t2_agentic_voice.voice.session.usage import Usage


@dataclass(frozen=True, kw_only=True)
class CallBooks:
    """One call's books: its usage, traces, recorder, public events and heard history."""

    usage: Usage
    trace: CallTrace
    recorder: CallRecorder
    events: CallEvents
    history: HeardHistory

    @classmethod
    def of(cls, setup: CallSetup) -> CallBooks:
        """A call's books, empty, built cheaply and with no IO: its traces carry the settings,
        the agent, the models it speaks with and the consent version as their resource."""
        settings, tag = setup.settings, setup.language.tag
        usage = Usage(settings, tag, setup.stt_model)
        models = (usage.stt_model, usage.model(tag))
        resource = resource_attributes(
            settings, agent=setup.agent.name, models=models, consent_version=setup.consent.version
        )
        return cls(
            usage=usage,
            trace=CallTrace(setup.tracing, call_id=setup.call_id, resource=resource),
            recorder=CallRecorder(setup),
            events=CallEvents(setup),
            history=HeardHistory(),
        )
