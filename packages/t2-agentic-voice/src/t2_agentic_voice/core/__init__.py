"""core: what every layer shares, below them all: the settings, structured logging, the error
types, tracing, the call's clock, and the types the layers hand each other (a caller's identity,
a call's events and report, the yes rule's inputs).

It imports no other layer, so every layer may import it. ARCHITECTURE.md's "Layers" maps the
layers and what each owns; each module's docstring says what it holds.
"""
