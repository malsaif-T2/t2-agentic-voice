"""Serving a runtime on its own, the sidecar (the design's 4.5): `serve`, and `combine_lifespans`
for an app that mounts the router's app as a sub-application; and for an app that serves its
own demo page, the access-code token route (`access_code_router`, its `AccessCodeGuard` and the
`TokenMinter` it mints with) and the page's headers (`page_headers`); and what that page may
choose for a call under `server.call_choices` (`CallOptions` of `SttOffer`, `ModelOffer` and
`VoiceOffer`, passed as `VoiceRuntime(call_options=...)`; one call's `CallChoice`). Stable (the
design's 5.1). A facade: it only re-exports (ARCH-FACADE)."""

from t2_agentic_voice.api.access_code import AccessCodeGuard, TokenMinter, access_code_router
from t2_agentic_voice.api.call_options import (
    CallChoice,
    CallOptions,
    ModelOffer,
    SttOffer,
    VoiceOffer,
)
from t2_agentic_voice.api.page_headers import page_headers
from t2_agentic_voice.api.server import combine_lifespans, serve

__all__ = [
    "AccessCodeGuard",
    "CallChoice",
    "CallOptions",
    "ModelOffer",
    "SttOffer",
    "TokenMinter",
    "VoiceOffer",
    "access_code_router",
    "combine_lifespans",
    "page_headers",
    "serve",
]
