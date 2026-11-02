"""The SDKs under the library's guarantees are the versions they were read at. Plan 002 read them
as text for every variable they read and every header and error they build: groq for
`GROQ_CUSTOM_HEADERS`, `GROQ_LOG`, its request hook and its exception chain (the Groq adapter);
httpx under it; OpenTelemetry's API, SDK and HTTP exporter for every `OTEL_*` variable (TD-005);
and requests under the exporter. The library declares no upper bound, so a later release
installs as soon as the lock moves; the adversarial tests catch only what they try, so this test
fails first, until the new version has been read the same way."""

from __future__ import annotations

from importlib.metadata import version

import pytest

READ = {
    "groq": "1.7.0",
    "httpx": "0.28.1",
    "opentelemetry-api": "1.45.2",
    "opentelemetry-sdk": "1.45.2",
    "opentelemetry-exporter-otlp-proto-http": "1.45.2",
    "requests": "2.34.2",
}


@pytest.mark.parametrize(("package", "read"), sorted(READ.items()))
def test_each_sdk_is_the_version_it_was_read_at(package: str, read: str) -> None:
    installed = version(package)
    assert installed == read, (
        f"{package} {installed} is installed, but the library's guarantees were read on {read}. "
        "FIX: read the new version as text as plan 002's decision log read this one (each "
        "variable it reads, each header and error it builds), mend what changed, then put the "
        "new version in READ here."
    )
