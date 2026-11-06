"""core: what every layer shares: the settings, structured logging, the error types, tracing
(the span helpers, the redaction hook, and the private provider with its exporter), the caller's
identity and consent (`identity.py`), a call's events and report (`events.py`), and its clock
(`clock.py`).

It imports no other layer (harness.toml [layers]), so every layer may import it.
"""
