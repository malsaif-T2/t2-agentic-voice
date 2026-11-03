"""voice: one call's real-time pipeline.

Audio in and out over WebRTC, speech detection, end of turn, the two-step interruption, and the
cancel scope of every turn, wiring speech-to-text and text-to-speech (through domain's ports) to
the talker. It is the only layer that may import the voice framework (harness.toml [[owners]]).
Built so far: the `t2v/1` messages on a call's data channel (`protocol.py`); the events and
commands between the session and the Pipecat modules and the protocols they meet through
(`session/session_events.py`, `session/commands.py`, `session/io.py`) and the session itself
(`session/`: `CallSession` in `session/call.py`, built by plan 003's Track D); voice's entry
point for api (`calls.py`), one Pipecat pipeline per call (`pipeline.py`), its WebRTC transport
and taps (`transport.py`), its turn detection (`turns.py`), its speech bridges (`stt_bridge.py`,
`tts_bridge.py`), its session bridge (`session_bridge.py`), Pipecat's failures as the library's
(`pipecat_events.py`) and the file-fed transport (`file_transport.py`), built by plan 003's
Track E.

Pipecat's loguru namespace is switched off here, before any module under this package is
imported, so it is off before voice first imports Pipecat (plan 003, Q2; `loguru_policy.py`).
"""

from t2_agentic_voice.voice.loguru_policy import switch_pipecat_off

switch_pipecat_off()
