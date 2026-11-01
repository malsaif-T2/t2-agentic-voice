"""testing: what a team uses to test and measure its voice agent.

The evaluation scorers today (word and character error rates, on jiwer), and later the testing
kit: the fakes of every port, text-mode calls, the adversarial suite and simulated callers. It
sits beside api, above voice: it may import voice and every layer below it, but never adapters
(it reaches a provider only through a port a test passes in) and never api, so a team's tests
need no HTTP stack (harness.toml [layers], D-019). It is the only layer that may import jiwer.
"""
