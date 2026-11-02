"""api: the outermost layer, the backend's HTTP surface and composition root.

It serves the web widget, starts a call (checks the join token and hands the WebRTC offer to
voice, which answers it), reports health, builds the adapters from the settings and injects them
into the layers below, and maps every error to one shape for its transport (GP-19). It may
import every other layer. Built so far: the health report (`status.py`) and the `t2v/1` HTTP
bodies, their caps and their one error body (`protocol.py`); the runtime (`runtime.py`) and
serving (`server.py`) are signatures.
"""
