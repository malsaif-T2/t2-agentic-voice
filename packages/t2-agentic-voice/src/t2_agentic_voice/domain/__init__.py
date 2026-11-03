"""domain: the rules of a support call, with no IO.

What counts as a clear yes, the ticket flow's states, what an interruption is (spoken commands
that cut the agent off, listening sounds, the agent's own words), Arabic text normalization,
how numbers and ticket IDs are spoken, the evaluation scorers' pure parts (term recall, ID
recall, text from silence, the sign test), and the ports (protocols) every outside service is
reached through. Built so far: the text rules (`text/`), the scorers' pure parts, the
declaration of a use case (`declaration.py`), and the speech-to-text, text-to-speech and identity
ports. It imports only core (harness.toml [layers]), so its rules are easy to test and
impossible to bypass with IO.
"""
