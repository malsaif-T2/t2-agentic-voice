"""The shell's variables the suite drops, in one place: tests/conftest.py drops them, and a test
that starts a child process gives it the same shell. tests/harness/test_isolation.py and
test_import_isolation.py keep lists of their own, as checks of these that do not rest on them."""

from __future__ import annotations

from t2_agentic_voice.core.settings.base import PREFIX, setting_name

# The variable that moves every runtime path, among this project's (`PREFIX`).
VAR_DIR_VARIABLE = setting_name("storage", "var_dir")
# The variables of the providers' SDKs and of the tracing tools, which the library never reads
# (the design's 7.3) but their SDKs would: a real key, an exporter's headers, Phoenix's own.
FOREIGN_PREFIXES = ("GROQ_", "OTEL_", "PHOENIX_")
# Variables of the HTTP clients under the SDKs, which change what a request to 127.0.0.1 trusts:
# requests replaces `verify=True` with either CA bundle (TD-004).
FOREIGN_NAMES = ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")
# Every prefix dropped from the shell: the providers', the tracing tools' and this project's own.
DROPPED_PREFIXES = (*FOREIGN_PREFIXES, PREFIX.upper())


def dropped(name: str) -> bool:
    """Whether the suite drops the variable `name` from the shell, in any case."""
    return name.upper().startswith(DROPPED_PREFIXES) or name.upper() in FOREIGN_NAMES
