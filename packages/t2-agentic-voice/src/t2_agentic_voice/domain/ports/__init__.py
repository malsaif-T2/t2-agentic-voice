"""domain/ports: the protocols every outside service is reached through, one module per port,
with their data types.

An adapter in `adapters/` implements a port, the api layer injects it, and the other layers see
only the protocol (GP-22); apps reach them through the `ports` facade. Each port that holds
connections closes them with `aclose()`, but the knowledge base, which is the team's own (the
design's 6.3). ARCHITECTURE.md's "Layers" maps the layers; each module's docstring says what it
holds.
"""
