"""core/settings: the groups of `VoiceSettings` (core/config.py), one module per group, on what
they share (`base.py`), and how the environment's names and texts become the settings' data
(`names.py`). None reads the environment: only core/config.py does (ARCH-ENV).
ARCHITECTURE.md's "Layers" maps the layers; each module's docstring says what it holds.

A field's `description` is its documentation: `uv run poe settings-ref` writes it into
docs/generated/settings.md and .env.example, so the code and the reference cannot drift. A
timing or size setting carries its unit in its name (`_ms`, `_s`), as the design's 7.3 asks,
and a count of words says so (`_words`).
"""
