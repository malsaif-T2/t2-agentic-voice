"""core: what every layer shares: the settings, structured logging, the error types, tracing
(the span helpers, the redaction hook, and the private provider with its exporter), the caller's
identity and consent (`identity.py`), and a call's events and report (`events.py`).

It imports no other layer (harness.toml [layers]), so every layer may import it.
"""
