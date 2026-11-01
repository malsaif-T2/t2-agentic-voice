"""domain: the rules of a support call, with no IO.

What counts as a clear yes, the ticket flow's states, what an interruption is (spoken commands
that cut the agent off, listening sounds, the agent's own words), Arabic text normalization,
how numbers and ticket IDs are spoken, and the ports (protocols) every outside service is
reached through. It imports only core (harness.toml [layers]), so its rules are easy to test and
impossible to bypass with IO.
"""
