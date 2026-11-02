"""Serving a runtime (api/server.py). Plan 003's Track F builds it and replaces this file's stub
test with its own (FastAPI's telemetry off, the proxy headers, the event loop on Windows)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from t2_agentic_voice.api.runtime import VoiceRuntime
from t2_agentic_voice.api.server import combine_lifespans, serve


@asynccontextmanager
async def _lifespan(app: object) -> AsyncIterator[None]:
    yield


def test_serving_is_a_stub_until_track_f() -> None:
    with pytest.raises(NotImplementedError, match="Track F"):
        serve(lambda: VoiceRuntime.__new__(VoiceRuntime))
    with pytest.raises(NotImplementedError, match="Track F"):
        combine_lifespans(_lifespan, _lifespan)
