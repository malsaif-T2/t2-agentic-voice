"""domain/ports: the protocols every outside service is reached through, and their data types.

One module per port: `speech_to_text.py`, `text_to_speech.py` and `identity.py` (the identity
source and the used-token store) so far; the chat model and the knowledge base later. An adapter
in `adapters/` implements a port, the api layer injects it, and the other layers see only the
protocol (GP-22). Each port that holds connections closes them with `aclose()`. Apps reach them
through the `ports` facade.
"""
