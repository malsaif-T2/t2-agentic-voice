"""core: what every layer shares: the settings, structured logging, the error types, and
tracing (the span helpers, the redaction hook, and the private provider with its exporter).

It imports no other layer (harness.toml [layers]), so every layer may import it.
"""
