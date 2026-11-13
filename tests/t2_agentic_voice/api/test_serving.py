"""A real server (api/server.py): `serve()` in a child process, on this machine's loopback, on the
fakes. It answers `/health`, `/ready` and a join; voice's entry point starts on a selector event
loop, which uvicorn takes from `asyncio.run` (D-029); and with
a global tracer, meter and logger provider and `FASTAPI_OTEL_AUTO_CONFIGURE=true`, FastAPI's
telemetry records nothing (D-023). The child is serving_child.py."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from tests.isolation import child_shell
from tests.t2_agentic_voice.api.runtime_support import PREFIX, TOKEN
from tests.t2_agentic_voice.api.serving_child import RESULT, STOP

ROOT = Path(__file__).resolve().parents[3]
START_S = 90.0  # importing the library and FastAPI in a new process, on a busy machine


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


def _up(http: httpx.Client, child: subprocess.Popen[bytes]) -> httpx.Response:
    deadline = time.monotonic() + START_S
    while time.monotonic() < deadline:
        assert child.poll() is None, "the server's process ended before it served"
        try:
            return http.get(PREFIX + "/health")
        except httpx.TransportError:
            time.sleep(0.2)
    raise AssertionError("the server did not answer in time")


def test_serve_answers_on_a_selector_loop_with_fastapis_telemetry_off(tmp_path: Path) -> None:
    port = _free_port()
    env = child_shell() | {"FASTAPI_OTEL_AUTO_CONFIGURE": "true"}
    child = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tests.t2_agentic_voice.api.serving_child",
            str(port),
            str(tmp_path),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as http:
            health = _up(http, child)
            ready = http.get(PREFIX + "/ready")
            join = http.post(PREFIX + "/join", json={"token": TOKEN, "protocol": 1})
        (tmp_path / STOP).write_text("", encoding="utf-8")
        _, errors = child.communicate(timeout=60)
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate()
    assert child.returncode == 0, errors.decode("utf-8", "replace")
    assert health.json() == {"env": "dev", "calls": 0}
    assert ready.json() == {"ready": True}
    assert join.status_code == 200 and "server" not in join.headers
    found = json.loads((tmp_path / RESULT).read_text(encoding="utf-8"))
    assert found == {"selector": True, "closed": 1, "spans": 0, "metrics": 0, "logs": 0}
