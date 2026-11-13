"""agent: the talker, the model that speaks, asks, and calls tools: one turn from the caller's
words to a reply and tool calls, in the reply's language, every clause checked by the output
guard before it is said. It never words an outcome itself: actions do.

It imports core, domain and actions, never adapters or voice. ARCHITECTURE.md's "Layers" maps
the layers and what each owns; each module's docstring says what it holds.
"""
