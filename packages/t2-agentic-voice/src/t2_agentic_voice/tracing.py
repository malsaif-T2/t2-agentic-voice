"""Tracing: set up from the settings or on a team's own provider, the span helpers, and the
redaction hook (D-023). Provisional (D-021). A facade: it only re-exports (ARCH-FACADE)."""

from t2_agentic_voice.core.redaction import Redactor
from t2_agentic_voice.core.tracing import SpeechToTextSpan, Tracing

__all__ = ["Redactor", "SpeechToTextSpan", "Tracing"]
