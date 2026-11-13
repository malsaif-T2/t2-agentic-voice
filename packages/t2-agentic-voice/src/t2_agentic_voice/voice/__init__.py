"""voice: one call's real-time pipeline: audio in and out over WebRTC, speech detection, end of
turn, the two-step interruption and each reply's cancel scope, wiring speech-to-text and
text-to-speech (through domain's ports) to the talker, and the call's session (voice/session/).

It imports core, domain and agent, never actions or adapters, and is the only layer that may
import the voice framework, Pipecat (harness.toml [[owners]]). ARCHITECTURE.md's "Layers" maps
the layers and what each owns; each module's docstring says what it holds. Pipecat's loguru
namespace is switched off here, before any module under this package is imported, so it is off
before voice first imports Pipecat (`loguru_policy.py`).
"""

from t2_agentic_voice.voice.loguru_policy import switch_pipecat_off

switch_pipecat_off()
