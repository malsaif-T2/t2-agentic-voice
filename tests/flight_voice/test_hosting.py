"""The settings handed to a host (flight_voice/hosting.py): every setting given here written as
an env line, defaults left out, each secret (a key, the join keys, the access code) blank under
its note, a path marked as this machine's, and no secret's text anywhere in the file."""

from __future__ import annotations

from pathlib import Path

import pytest
from flight_voice.hosting import PATH_NOTE, SECRET_NOTE, env_lines, main

from tests.flight_voice.server_support import CODE, KEY

GROQ = "gsk-a-made-up-groq-key-0123456789"


def test_the_host_gets_every_setting_given_and_no_secret(
    environment: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment.setenv("T2V_GROQ__API_KEY", GROQ)
    environment.setenv("T2V_LLM__MODEL", "openai/gpt-oss-120b")
    environment.setenv("T2V_SERVER__ALLOWED_ORIGINS", '["https://voice.example.com"]')
    environment.setenv("FLIGHT_VOICE_AGENT", "lean")
    environment.setenv("FLIGHT_VOICE_FLIGHT_DATA", "mock")
    lines = env_lines(None)
    text = "\n".join(lines)
    assert "T2V_ENV=dev" in lines and "FLIGHT_VOICE_AGENT=lean" in lines
    assert "T2V_LLM__MODEL=openai/gpt-oss-120b" in lines
    assert 'T2V_SERVER__ALLOWED_ORIGINS=["https://voice.example.com"]' in lines
    for secret in ("T2V_GROQ__API_KEY=", "T2V_JOIN__KEYS=", "FLIGHT_VOICE_ACCESS_CODE="):
        assert secret in lines and lines[lines.index(secret) - 1] == SECRET_NOTE, secret
    assert GROQ not in text and KEY not in text and CODE not in text and "***" not in text
    assert "T2V_JOIN__CURRENT_KID=k1" in lines  # a key's name, not a secret
    assert "T2V_TTS__PROVIDER" not in text  # a default is left out


def test_a_path_is_marked_as_this_machines_and_the_file_is_written(
    environment: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment.setenv("T2V_STORAGE__VAR_DIR", str(tmp_path / "var"))
    out = tmp_path / "alpha.env"
    assert main(["--out", str(out)]) == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    (at,) = [i for i, line in enumerate(lines) if line.startswith("T2V_STORAGE__VAR_DIR=")]
    assert lines[at - 1] == PATH_NOTE
