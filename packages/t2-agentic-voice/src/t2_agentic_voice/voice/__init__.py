"""voice: one call's real-time pipeline.

Audio in and out over WebRTC, speech detection, end of turn, the two-step interruption, and the
cancel scope of every turn, wiring speech-to-text and text-to-speech (through domain's ports) to
the talker. It is the only layer that may import the voice framework (harness.toml [[owners]]).
"""
