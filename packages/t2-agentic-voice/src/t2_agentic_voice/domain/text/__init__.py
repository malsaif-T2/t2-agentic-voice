"""domain/text: the rules for a speech text, with no IO: how a text is normalized and its words
matched, how its numbers, IDs and terms are said, and how it is cut into clauses. Apps reach them
through the `languages` facade (D-021). The library's tables of Arabic characters are written
with `\\u` escapes, each character named in a comment.

ARCHITECTURE.md's "Layers" maps the layers; each module's docstring says what it holds.
"""
