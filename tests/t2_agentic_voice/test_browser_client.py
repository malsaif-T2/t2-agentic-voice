"""The browser side of `t2v/1` (plan 003): the reference client
`api/static/t2v-client.js` and the dev page `api/static/dev.html`, read as text, since the suite
runs no browser (the agent's browser pane and the owner's Chrome and Edge check the rest: plan
003, step 16 and 18). The client speaks the protocol the fixture lists, every message of the
session's included (plan 006's `card` among them; test_browser_cards.py runs the client in a
fake browser); every page and script, the Ole5 widget's included, inserts text only as text; the
dev page holds no script or style of its own; and the built wheel ships both files."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import zipfile
from html.parser import HTMLParser
from pathlib import Path

import pytest
from t2_agentic_voice.api import protocol
from t2_agentic_voice.voice.protocol import ClientHello, parse_client_message

from tests.isolation import child_shell

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "packages" / "t2-agentic-voice"
STATIC = LIBRARY / "src" / "t2_agentic_voice" / "api" / "static"
CLIENT = STATIC / "t2v-client.js"
DEV_PAGE = STATIC / "dev.html"
# The committed t2v/1 message list (test_protocol_list.py holds the models to it).
FIXTURE = Path(__file__).parent / "fixtures" / "t2v_protocol.json"
# What inserts markup rather than text (the browser criteria of plan 003).
MARKUP = re.compile(r"\b(innerHTML|outerHTML|insertAdjacentHTML)\b|document\s*\.\s*write")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _array(source: str, name: str) -> list[str]:
    """The strings of a JavaScript `const <name> = [...]`."""
    found = re.search(rf"const {name} = \[([^\]]*)\]", source)
    assert found, name
    return re.findall(r'"([^"]*)"', found.group(1))


def _constant(source: str, name: str) -> str:
    found = re.search(rf"const {name} = ([^;]+);", source)
    assert found, name
    return found.group(1).strip()


def browser_files(root: Path = ROOT) -> list[Path]:
    """Every page and script a browser runs: the library's static files and each app's
    widget."""
    library = root / "packages" / "t2-agentic-voice" / "src" / "t2_agentic_voice" / "api" / "static"
    found = [*library.glob("*.js"), *library.glob("*.html")]
    for web in sorted((root / "apps").glob("*/web")):
        found += [*web.glob("*.js"), *web.glob("*.html")]
    return sorted(found)


def test_no_page_or_script_inserts_markup() -> None:
    files = browser_files()
    names = {path.relative_to(ROOT).as_posix() for path in files}
    assert {
        "packages/t2-agentic-voice/src/t2_agentic_voice/api/static/t2v-client.js",
        "packages/t2-agentic-voice/src/t2_agentic_voice/api/static/dev.html",
        "apps/ole5-voice-agent/web/widget.js",
        "apps/ole5-voice-agent/web/index.html",
    } <= names
    assert [path.name for path in files if MARKUP.search(_text(path))] == []
    assert "textContent" in _text(CLIENT)


def test_the_search_finds_each_way_to_insert_markup(tmp_path: Path) -> None:
    web = tmp_path / "apps" / "a" / "web"
    web.mkdir(parents=True)
    library = tmp_path / "packages" / "t2-agentic-voice" / "src" / "t2_agentic_voice" / "api"
    (library / "static").mkdir(parents=True)
    for each, line in enumerate(
        [
            "a.innerHTML = t",
            "a.outerHTML = t",
            "a.insertAdjacentHTML('beforeend', t)",
            "document.write(t)",
            "document . write(t)",
        ]
    ):
        (web / f"w{each}.js").write_text(line, encoding="utf-8")
    (library / "static" / "c.html").write_text("<p>a.textContent = t</p>", encoding="utf-8")
    flagged = [p.name for p in browser_files(tmp_path) if MARKUP.search(_text(p))]
    assert flagged == ["w0.js", "w1.js", "w2.js", "w3.js", "w4.js"]


def test_the_client_speaks_the_protocol_the_fixture_lists() -> None:
    source = _text(CLIENT)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    channel = fixture["data_channel"]
    assert _array(source, "CLIENT_MESSAGES") == list(channel["client_to_session"])
    # Every message of the session's (test_browser_cards.py sends each through the client).
    assert _array(source, "SESSION_MESSAGES") == list(channel["session_to_client"])
    states = channel["session_to_client"]["state"]["state"].split(" | ")
    assert _array(source, "STATES") == states == ["listening", "thinking", "speaking", "confirming"]
    assert [_constant(source, "RESERVED").strip('"')] == fixture["reserved"]["types"]
    assert _constant(source, "PROTOCOL") == str(fixture["protocol"]) == "1"
    patch = protocol.BODIES["PATCH /offer"]
    assert _array(source, "QUIET") == list(patch.errors[409])
    assert int(_constant(source, "MAX_CANDIDATES").split()[0]) == protocol.MAX_CANDIDATES
    assert _constant(source, "JSON_TYPE") == f'"{protocol.JSON_TYPE}"'
    name = _constant(source, "CLIENT").strip('"')
    assert parse_client_message({"v": 1, "type": "hello", "client": name}) == ClientHello(
        v=1, type="hello", client=name
    )


def test_the_client_sends_only_json_objects_and_bodies() -> None:
    """Every data-channel message is one JSON object built with its version (no raw text, so
    never SmallWebRTC's `ping`), every HTTP body is JSON sent as such, and the offer secret
    rides in the body, never in a URL."""
    source = _text(CLIENT)
    assert source.count(".send(") == 1
    assert "this.#channel.send(JSON.stringify({ v: PROTOCOL, type, ...fields }));" in source
    assert source.count("fetch(") == 1
    assert 'headers: { "content-type": JSON_TYPE }' in source
    assert "body: JSON.stringify(body)" in source
    assert "offer_secret: this.#secret" in source
    assert "fetch(new URL(path, this.#base), {" in source  # a route's path alone: no query


def test_the_client_sends_candidates_only_once_answered() -> None:
    source = _text(CLIENT)
    drain = source[source.index("  #drain() {") : source.index("  async #patch(")]
    assert "if (!this.#answered || this.#draining) return;" in drain
    begin = source[source.index("  async #begin() {") : source.index("  async #request(")]
    assert begin.index('await this.#request("POST", "offer"') < begin.index(
        "this.#answered = true;"
    )
    assert begin.index("addTransceiver") < begin.index("createDataChannel")  # audio is mid 0
    assert begin.index("openMicrophone()") < begin.index("getToken()")  # no token spent first
    assert 'candidate: "", sdp_mid: this.#mid(), sdp_mline_index: 0' in source


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.inline: list[str] = []
        self._in: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))
        self._in = tag

    def handle_data(self, data: str) -> None:
        if self._in in ("script", "style") and data.strip():
            self.inline.append(data)

    def handle_endtag(self, tag: str) -> None:
        self._in = None


def test_the_dev_page_holds_no_script_or_style_of_its_own() -> None:
    """So whatever Content-Security-Policy the router sends `/dev` keeps it working: the client
    builds the page, found by the root element's `data-t2v-page`."""
    page = _Page()
    page.feed(_text(DEV_PAGE))
    assert page.inline == []
    assert [a for t, a in page.tags if t == "script"] == [
        {"type": "module", "src": "client/1/t2v-client.js"}
    ]
    assert ("html", {"lang": "en", "data-t2v-page": "dev"}) in page.tags
    assert all(t != "style" and "style" not in a for t, a in page.tags)
    assert all(not name.startswith("on") for _, a in page.tags for name in a)
    source = _text(CLIENT)
    dev = source[source.index("function devPage(page) {") :]
    read = set(re.findall(r'\$\("([a-z-]+)"\)', dev))
    ids = {a["id"] for _, a in page.tags if a.get("id")}
    assert read and read == ids
    assert 'documentElement?.dataset?.t2vPage === "dev"' in source


def test_the_library_names_no_app() -> None:
    for path in (CLIENT, DEV_PAGE):
        assert "ole5" not in _text(path).lower()


def _uv() -> str:
    found = os.environ.get("UV") or shutil.which("uv")
    if found is None:
        pytest.skip("uv is not on this machine: the wheel is built with it")
    return found


def test_the_built_wheel_ships_the_client_and_the_dev_page(tmp_path: Path) -> None:
    built = subprocess.run(
        [_uv(), "build", "--offline", "--wheel", "--out-dir", str(tmp_path), str(LIBRARY)],
        env=child_shell(),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    [wheel] = tmp_path.glob("t2_agentic_voice-*.whl")
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        shipped = archive.read("t2_agentic_voice/api/static/t2v-client.js")
    assert "t2_agentic_voice/api/static/dev.html" in names
    assert shipped == CLIENT.read_bytes()
