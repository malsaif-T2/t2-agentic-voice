"""api: the outermost layer, the backend's HTTP surface and composition root.

It serves the web widget, starts a call (checks the join token and hands the WebRTC offer to
voice, which answers it), reports health, builds the adapters from the settings and injects them
into the layers below, and maps every error to one shape for its transport (GP-19). It may
import every other layer.
"""
