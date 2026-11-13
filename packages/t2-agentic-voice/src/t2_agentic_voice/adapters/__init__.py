"""adapters: what the library reaches outside the process through, each behind a port from domain:
the providers (Groq's speech-to-text, chat model and text-to-speech; the spoken-language
classifiers), the identity sources (signed join tokens, the dev caller), and what is kept on
disk (the used-token stores, the outbox, the phrase and clause caches). A setting picks a
built-in adapter and a team passes any other in code, so a provider is swapped by configuration,
never by editing the layers that use it (D-003, D-004).

It imports core and domain only, and is the only layer that may import the service clients and
`sqlite3` (harness.toml [[owners]]). ARCHITECTURE.md's "Layers" maps the layers and what each
owns; each module's docstring says what it holds.
"""
