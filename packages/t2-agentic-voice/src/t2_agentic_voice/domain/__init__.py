"""domain: the rules of a support call, with no IO, and the ports (protocols) every outside
service is reached through.

It imports only core, so each rule is a plain function with plain tests that no IO can go
around. ARCHITECTURE.md's "Layers" maps the layers and what each owns; each module's docstring
says what it holds.
"""
