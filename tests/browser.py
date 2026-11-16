"""The browser-side tests' fake browser (tests/browser.mjs), run under Node: a page's module
imported with just enough DOM, media, fetch and WebRTC to start a call and take `t2v/1`'s
messages, with nothing on the network and no audio, so a test reads what the page shows (each
element's text, attributes and children) rather than its script's text alone. Writing markup
throws there, and so fails the test. Skipped where Node is not installed, as the wheel's test is
without uv; test_browser_client.py's text checks (no markup inserted, the protocol's lists) run
everywhere."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Iterator, Mapping
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from tests.isolation import child_shell

HARNESS = Path(__file__).with_name("browser.mjs")
# The elements HTML never closes.
VOID = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}
)
# A step of the fake browser's, and what it shows: JSON as browser.mjs reads and writes it.
type Step = dict[str, Any]
type Shown = dict[str, Any]


class _Elements(HTMLParser):
    """A page's elements in document order, each with its parent's index and its own text."""

    def __init__(self) -> None:
        super().__init__()
        self.elements: list[dict[str, Any]] = []
        self._open: list[int] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        parent = self._open[-1] if self._open else None
        self.elements.append({"tag": tag, "attrs": dict(attrs), "parent": parent, "text": ""})
        if tag not in VOID:
            self._open.append(len(self.elements) - 1)

    def handle_endtag(self, tag: str) -> None:
        while self._open and self.elements[self._open.pop()]["tag"] != tag:
            pass

    def handle_data(self, data: str) -> None:
        if self._open and data.strip():
            self.elements[self._open[-1]]["text"] += data.strip()


def page_elements(page: Path) -> list[dict[str, Any]]:
    """The elements of the HTML file `page`, as browser.mjs builds its document from them."""
    parser = _Elements()
    parser.feed(page.read_text(encoding="utf-8"))
    return parser.elements


def browse(
    folder: Path,
    files: Mapping[str, Path],
    *,
    entry: str,
    location: str,
    steps: list[Step],
    page: Path | None = None,
    answers: Mapping[str, Any] | None = None,
    storage: Mapping[str, str] | None = None,
) -> Shown:
    """Copy `files` (each a path under `folder`, from its source) into `folder` as ES modules,
    open `page` (none: an empty one) at `location` with `entry` imported, and take `steps`,
    the routes answering `answers` too, and the page given `storage` as its localStorage (none:
    no localStorage). What browser.mjs wrote: its snapshots, the started client's events, the
    messages sent, the requests made, the storage left; no listener of the page failed."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not on this machine: the fake browser runs under it")
    for name, source in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(source.read_bytes())
    (folder / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    payload = {
        "module": (folder / entry).as_uri(),
        "location": location,
        "page": [] if page is None else page_elements(page),
        "steps": steps,
        "answers": dict(answers or {}),
        "storage": None if storage is None else dict(storage),
    }
    done = subprocess.run(
        [node, str(HARNESS)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=child_shell(),
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    shown: Shown = json.loads(done.stdout)
    assert shown["errors"] == []
    return shown


def receive(message: Mapping[str, Any]) -> Step:
    """The step that delivers `message` on the call's data channel, as the session's JSON."""
    return {"do": "receive", "data": json.dumps(message, ensure_ascii=False)}


def descendants(node: Shown) -> Iterator[Shown]:
    """Every element under `node`, in document order."""
    for child in node.get("children", []):
        if "tag" in child:
            yield child
            yield from descendants(child)


def text(node: Shown) -> str:
    """The text `node` shows, as `textContent` reads it."""
    if "text" in node:
        return str(node["text"])
    return "".join(text(child) for child in node["children"])
