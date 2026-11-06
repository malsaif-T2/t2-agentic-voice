"""domain/ports: the protocols every outside service is reached through, and their data types.

One module per port: `speech_to_text.py`, `chat_model.py`, `text_to_speech.py`, `identity.py`
(the identity source and the used-token store) and `knowledge.py` (a team's knowledge base).
An adapter in `adapters/` implements a port, the api layer injects it, and the other layers see
only the protocol (GP-22). Each port that holds connections closes them with `aclose()`, but the
knowledge base, which is the team's own (the design's 6.3). Apps reach them through the `ports`
facade.
"""
