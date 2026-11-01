"""domain/ports: the protocols every outside service is reached through, and their data types.

One module per port (`speech_to_text.py` today; the chat model, text-to-speech and the
knowledge base later). An adapter in `adapters/` implements a port, the api layer injects it,
and the other layers see only the protocol (GP-22). Apps reach them through the `ports` facade.
"""
