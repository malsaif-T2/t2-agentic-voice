"""Serving a runtime on its own, the sidecar (the design's 4.5): `serve`, and `combine_lifespans`
for an app that mounts the router's app as a sub-application. Stable (the design's 5.1). A
facade: it only re-exports (ARCH-FACADE)."""

from t2_agentic_voice.api.server import combine_lifespans, serve

__all__ = ["combine_lifespans", "serve"]
