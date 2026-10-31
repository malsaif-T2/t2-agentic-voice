"""adapters: the outside services, each behind a port from domain.

Speech-to-text, the chat model and text-to-speech (Groq today), the knowledge base, and the
ticket system. Each adapter implements one domain port and is chosen by a setting, so a provider
is swapped by configuration, never by editing the layers that use it (D-004; the mechanism is
D-003). It is the only layer that may import the service clients (harness.toml [[owners]]).
"""
