"""What the recorder's tests share (`test_recorder.py`, `test_recorder_security.py`): a made-up
tree like the owner's, with made-up `.env` files where the two real ones sit; a recorder over
it; a real server on a free port of 127.0.0.1 in a thread; and a client that sends exactly the
headers a test gives. No test touches a device: every take is a WAV built here."""

from __future__ import annotations

import base64
import http.client
import io
import json
import socket
import struct
import sys
import threading
import wave
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ole5_voice.evals.audio import sha256_of, write_wav
from ole5_voice.evals.models import AudioRef, Item, Manifest, ManifestFile, SplitFile, Variant
from ole5_voice.evals.recorder import RecorderServer
from ole5_voice.evals.recorder_load import load_recorder
from ole5_voice.evals.recorder_state import Recorder
from t2_agentic_voice.evals import GitResult

from tests.ole5_voice.evals.fakes import FakeGoldenSet

WHEN = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)
KEY = "made-up-key-that-is-never-served"
SECRET = f"T2V_GROQ__API_KEY={KEY}\n"
LONG = "n" * 120  # a line whose take names would pass a name's 128 characters
SCRIPT = f"""\
listening_sounds = ["mm-hmm"]

[[lines]]
id = "n01"
kind = "request"
language = "english"
say = ["open a ticket about my mail"]

[[lines]]
id = "n02"
kind = "multi_clause_request"
language = "english"
say = ["my mail is slow", "and the archive is full"]

[[lines]]
id = "n03"
kind = "echo_only"
language = "none"
reply = "en_ticket"

[[lines]]
id = "{LONG}"
kind = "request"
language = "english"
say = ["a line with a long name"]
"""
CONSENT = {"speaker": "the owner", "words": "I agree to these recordings' use.", "agreed": True}
TRACK = {"echo_cancellation": True, "noise_suppression": True, "auto_gain_control": True}


def wav(seconds: float = 0.5, rate: int = 16_000, channels: int = 1, width: int = 2) -> bytes:
    """A made-up WAV file: a ramp at 16 kHz mono 16-bit, or silence in another format."""
    frames = int(rate * seconds)
    if (rate, channels, width) == (16_000, 1, 2):
        return write_wav(b"".join(struct.pack("<h", (i * 37) % 2000 - 1000) for i in range(frames)))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(width)
        writer.setframerate(rate)
        writer.writeframes(b"\x01" * channels * width * frames)
    return buffer.getvalue()


@dataclass
class Tree:
    """The made-up tree: this repository's checkout (its `.env`, and `--out` under its var/),
    the old repository beside it (its `.env`), and the lab's replies and recordings."""

    root: Path
    checkout: Path
    out: Path
    replies: Path
    talkover: Path
    script: Path
    manifests: Path
    segment: bytes


def make_tree(root: Path) -> Tree:
    checkout = root / "t2-agentic-voice"
    out = checkout / "var" / "golden-audio"
    lab = root / "voice-lab"
    replies, talkover = lab / "assets" / "talkover", lab / "recordings" / "talkover"
    manifests = checkout / "apps" / "ole5-voice-agent" / "evals" / "manifests"
    for folder in (out, replies, talkover / "seg", manifests, root / "Ole5-chatbot"):
        folder.mkdir(parents=True)
    served = (out, replies, talkover, talkover / "seg", root / "Ole5-chatbot")
    for folder in {p for f in served for p in (f, *f.parents) if p.is_relative_to(root)}:
        (folder / ".env").write_text(SECRET, encoding="utf-8")
    (replies / "en_ticket.wav").write_bytes(wav(0.3, rate=24_000))
    reply = {"id": "en_ticket", "lang": "en", "topic": "a ticket read-back", "ms": 300}
    replies_json = [{**reply, "file": "en_ticket.wav", "text": "a reply"}]
    (replies / "replies.json").write_text(json.dumps(replies_json), encoding="utf-8")
    segment = wav(0.75)
    (talkover / "seg" / "a.wav").write_bytes(segment)
    write_manifest(manifests / "talkover.json", [("seg/a.wav", sha256_of(segment))])
    script = checkout / "script.toml"
    script.write_text(SCRIPT, encoding="utf-8")
    return Tree(root, checkout, out, replies, talkover, script, manifests, segment)


def write_manifest(path: Path, files: Sequence[tuple[str, str]], root: str = "talkover") -> None:
    named = tuple(
        ManifestFile(
            path=p,
            sha256=sha,
            seconds=0.75,
            sample_rate=16_000,
            device="laptop",
            session="talkover-1",
        )
        for p, sha in files
    )
    path.write_text(Manifest(root=root, files=named).model_dump_json(), encoding="utf-8")


def item(item_id: str, *segments: tuple[str, str, str]) -> Item:
    """A talk-over item, one variant for each (root, path, SHA-256) given."""
    variants = tuple(
        Variant(
            id=f"{item_id}-{n}",
            segments=(AudioRef(root=root, path=path, sha256=sha),),
            device="laptop",
            session="talkover-1",
            reference="افتح تذكرة",
            reference_source="script",
        )
        for n, (root, path, sha) in enumerate(segments, start=1)
    )
    return Item(
        id=item_id,
        source="talkover",
        kind="sentence",
        language="saudi",
        text="افتح تذكرة",
        variants=variants,
    )


def items(tree: Tree) -> tuple[Item, ...]:
    """t01-1 is on its manifest; t01-2's file is on none; t01-3 is below a root not given."""
    sha = sha256_of(tree.segment)
    return (
        item(
            "t01",
            ("talkover", "seg/a.wav", sha),
            ("talkover", "seg/b.wav", sha),
            ("owner", "laptop/x.wav", sha),
        ),
    )


def recorder_of(tree: Tree, *, golden: Sequence[Item] | None = None, **given: Any) -> Recorder:
    split = SplitFile(salt="made-up", items={"t01": "dev"})
    found = FakeGoldenSet(items(tree) if golden is None else golden, split)
    settings: dict[str, Any] = {
        "out": tree.out,
        "script": tree.script,
        "session": "laptop-1",
        "device": "laptop",
        "replies": tree.replies,
        "audio": {"talkover": tree.talkover},
        "manifests": tree.manifests,
        "load_items": found.load_items,
        "clock": lambda: WHEN,
        "git": _no_git,
    }
    return load_recorder(**(settings | given))


def _no_git(args: Sequence[str], cwd: Path) -> GitResult:
    """A `git` that names no worktree, so the recorder knows only its own checkout, and no
    test of it runs git (`test_worktree.py` and the library's `test_run_checkout.py` run the
    real one)."""
    return GitResult(128, "")


@contextmanager
def serving(recorder: Recorder) -> Iterator[RecorderServer]:
    server = RecorderServer(recorder)
    # A short poll, so `shutdown` returns at once rather than after the default half second.
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


@dataclass
class Answer:
    status: int
    body: bytes
    headers: dict[str, str]

    def json(self) -> Any:
        return json.loads(self.body)


def ask(
    server: RecorderServer,
    method: str,
    path: str,
    headers: Sequence[tuple[str, str]],
    body: bytes = b"",
) -> Answer:
    """One request with exactly these headers (no `Host` unless given) and this target, sent as
    written: never normalized, never encoded."""
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for name, value in headers:
            connection.putheader(name, value)
        connection.endheaders(body or None)
        response = connection.getresponse()
        return Answer(response.status, response.read(), dict(response.getheaders()))
    finally:
        connection.close()


def raw(server: RecorderServer, request: bytes) -> bytes:
    """The answer to bytes sent as they are, the sending side then closed."""
    with socket.create_connection(("127.0.0.1", server.server_port), timeout=10) as connection:
        connection.sendall(request)
        connection.shutdown(socket.SHUT_WR)
        return b"".join(iter(lambda: connection.recv(65536), b""))


def get(server: RecorderServer, route: str) -> Answer:
    return ask(server, "GET", f"/{server.token}/{route}", [("Host", server.host)])


def post(
    server: RecorderServer, route: str, payload: Any, *, origin: str | None = "", kind: str = ""
) -> Answer:
    """A POST from the page: the right `Origin` unless another is given (None: none at all)."""
    body = json.dumps(payload).encode()
    headers = [("Host", server.host), ("Content-Type", kind or "application/json")]
    headers += [("Content-Length", str(len(body)))]
    if origin is not None:
        headers.append(("Origin", origin or server.origin))
    return ask(server, "POST", f"/{server.token}/{route}", headers, body)


def take(line: str = "n01", clip: bytes | None = None, **fields: Any) -> dict[str, Any]:
    """A take as the page sends it."""
    audio = base64.b64encode(wav() if clip is None else clip).decode()
    sent = {
        "line": line,
        "microphone": "Microphone Array (made up)",
        "output": "Speakers (made up)",
    }
    return sent | {"track": TRACK, "status": "kept", "audio": audio} | fields


def sidecar(take_id: str, line: str, sha: str, session: str = "laptop-1") -> str:
    """A take's sidecar as the recorder writes it."""
    fields: dict[str, Any] = {"take": take_id, "line": line, "session": session}
    fields |= {"device": "laptop"}
    fields |= {"microphone": "m", "track": TRACK, "recorded_at": WHEN.isoformat()}
    fields |= {"file": f"{take_id}.wav", "sha256": sha, "seconds": 0.5, "status": "kept"}
    return json.dumps(fields)


def link_folder(link: Path, target: Path) -> None:
    """A folder link: a junction on Windows, where it needs no privilege, else a symbolic link."""
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)
