"""The recorder's refusals (GP-08; plan 002's decision log): it listens on 127.0.0.1 only, answers
only its own `Host` and paths under its token, takes a POST only from its own `Origin`, as JSON,
of a bounded body, takes only 16 kHz mono 16-bit WAV, never replaces a file, and serves only its
allow-list, so no path from a request (an encoded `..`, an absolute path, a link) ever reads the
made-up `.env` files placed where the two real ones sit."""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import quote

import pytest
from ole5_voice.evals import recorder
from ole5_voice.evals.audio import sha256_of, write_wav
from ole5_voice.evals.recorder import RecorderServer
from ole5_voice.evals.recorder_state import MAX_BODY

from tests.ole5_voice.evals.recorder_support import (
    CONSENT,
    KEY,
    LONG,
    SECRET,
    Tree,
    ask,
    get,
    item,
    items,
    link_folder,
    post,
    raw,
    recorder_of,
    serving,
    sidecar,
    take,
    wav,
    write_manifest,
)


def _files(root: Path) -> set[Path]:
    return {p for p in root.rglob("*") if p.is_file()}


def test_the_server_listens_on_127_0_0_1_with_a_new_token_each_run(tree: Tree) -> None:
    checker = recorder_of(tree)
    with serving(checker) as one, serving(checker) as two:
        page, script = get(one, ""), get(one, "recorder.js")
    assert (one.server_address[0], one.host) == ("127.0.0.1", f"127.0.0.1:{one.server_port}")
    assert one.token != two.token and len(one.token) >= 40
    assert one.address == f"http://127.0.0.1:{one.server_port}/{one.token}/"
    assert page.headers["Content-Type"] == "text/html; charset=utf-8"
    assert script.headers["Content-Type"] == "text/javascript; charset=utf-8"
    policy = page.headers["Content-Security-Policy"]
    assert "default-src 'none'" in policy and "script-src 'self';" in policy
    assert page.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert page.headers["Referrer-Policy"] == "no-referrer"
    assert b'src="recorder.js"' in page.body


def test_the_page_loads_nothing_from_elsewhere() -> None:
    """No script, font or stylesheet from another address. (That no reference is in the page or
    the recorder's code is the golden set's rule for every file: `test_no_item_in_source.py`.)"""
    for path in recorder.PAGE.iterdir():
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"https?:|//[\w.-]+\.\w|url\(|@import", text), path.name


@pytest.mark.parametrize(
    "hosts",
    [
        [],
        ["localhost:{port}"],
        ["127.0.0.1"],
        ["127.0.0.1:1"],
        ["evil.example:{port}"],
        ["[::1]:{port}"],
        ["127.0.0.1:{port}", "127.0.0.1:{port}"],
    ],
)
def test_a_wrong_host_is_refused(tree: Tree, hosts: list[str]) -> None:
    """DNS rebinding: a page from another name that resolves to 127.0.0.1 sends its own."""
    with serving(recorder_of(tree)) as server:
        headers = [("Host", h.format(port=server.server_port)) for h in hosts]
        answers = [
            ask(server, "GET", f"/{server.token}/{route}", headers)
            for route in ("", "api/state", "reply/en_ticket")
        ]
    assert {a.status for a in answers} == {403}
    assert all(b"en_ticket" not in a.body and b"RIFF" not in a.body for a in answers)


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/index.html",
        "/{wrong}/",
        "/{cut}/",
        "/{swapped}/",
        "/{token}",
        "/{token}x/",
        "/x/{token}/",
        "/?{token}/",
        "/api/state",
    ],
)
def test_a_missing_or_wrong_token_is_refused(tree: Tree, path: str) -> None:
    with serving(recorder_of(tree)) as server:
        token = server.token
        target = path.format(
            token=token, wrong="a" * len(token), cut=token[:-1], swapped=token.swapcase()
        )
        answer = ask(server, "GET", target, [("Host", server.host)])
    assert answer.status == 403


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "http://localhost:{port}",
        "http://127.0.0.1:1",
        "https://127.0.0.1:{port}",
        "null",
        "http://evil.example",
    ],
)
def test_a_post_from_another_origin_is_refused(tree: Tree, origin: str | None) -> None:
    """A form or a fetch from another page in Chrome, which cannot know the token, carries its
    own `Origin`; one without any is refused too."""
    before = _files(tree.root)
    with serving(recorder_of(tree)) as server:
        sent = None if origin is None else origin.format(port=server.server_port)
        answers = [
            post(server, route, body, origin=sent)
            for route, body in [("api/consent", CONSENT), ("api/take", take())]
        ]
        twice = [("Host", server.host), ("Origin", server.origin), ("Origin", server.origin)]
        doubled = ask(
            server, "POST", f"/{server.token}/api/consent", [*twice, ("Content-Length", "2")], b"{}"
        )
    assert [a.status for a in answers] == [403, 403] and doubled.status == 403
    assert _files(tree.root) == before


@pytest.mark.parametrize(
    "kind", ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data"]
)
def test_a_post_that_is_not_json_is_refused(tree: Tree, kind: str) -> None:
    with serving(recorder_of(tree)) as server:
        assert post(server, "api/consent", CONSENT, kind=kind).status == 415
        assert (
            ask(
                server,
                "POST",
                f"/{server.token}/api/consent",
                [
                    ("Host", server.host),
                    ("Origin", server.origin),
                    ("Content-Type", "application/json"),
                    ("Content-Length", "1"),
                ],
                b"{",
            ).status
            == 400
        )
        assert post(server, "api/nothing", CONSENT).status == 404
    assert not (tree.out / "laptop-1").exists()


def test_a_body_too_large_or_of_no_given_length_is_refused(tree: Tree) -> None:
    with serving(recorder_of(tree)) as server:
        base = [
            ("Host", server.host),
            ("Origin", server.origin),
            ("Content-Type", "application/json"),
        ]
        target = f"/{server.token}/api/take"
        too_large = ask(server, "POST", target, [*base, ("Content-Length", str(MAX_BODY + 1))])
        lengths = [
            [],
            [("Content-Length", "-1")],
            [("Content-Length", "2"), ("Content-Length", "2")],
        ]
        unsized = [ask(server, "POST", target, [*base, *given]).status for given in lengths]
        head = f"POST {target} HTTP/1.1\r\nHost: {server.host}\r\nOrigin: {server.origin}\r\n"
        short = raw(
            server,
            f"{head}Content-Type: application/json\r\nContent-Length: 10\r\n\r\n{{}}".encode(),
        )
    assert too_large.status == 413
    assert unsized == [411, 411, 411]
    assert short.startswith(b"HTTP/1.0 400 ")


@pytest.mark.parametrize(
    "clip",
    [
        wav(rate=44_100),
        wav(rate=8_000),
        wav(channels=2),
        wav(width=1),
        b"RIFF but no wave",
        b"",
        write_wav(b""),
    ],
    ids=["44.1 kHz", "8 kHz", "stereo", "8-bit", "not a wave", "empty", "no samples"],
)
def test_a_take_that_is_not_16k_mono_16bit_wav_is_refused(tree: Tree, clip: bytes) -> None:
    with serving(recorder_of(tree)) as server:
        post(server, "api/consent", CONSENT)
        answer = post(server, "api/take", take(clip=clip))
        not_base64 = post(server, "api/take", take() | {"audio": "not base64!"})
    assert answer.status == 400 and answer.json()["error"].startswith("the take is refused: ")
    assert not_base64.status == 400
    assert sorted(p.name for p in (tree.out / "laptop-1").iterdir()) == ["session.json"]


def test_no_field_of_a_post_names_a_path(tree: Tree) -> None:
    before = _files(tree.root)
    with serving(recorder_of(tree)) as server:
        post(server, "api/consent", CONSENT)
        statuses = [
            post(server, "api/take", take("../../.env")).status,
            post(server, "api/take", take("n99")).status,  # no such line
            post(server, "api/take", take(file="../../.env")).status,  # no such field
            post(server, "api/take", take(LONG)).status,  # its take names would be too long
            post(
                server, "api/review", {"id": "../talkover-1/t01-1", "verdict": "confirmed"}
            ).status,
            post(server, "api/review", {"id": "nothing-like-it", "verdict": "confirmed"}).status,
        ]
    assert statuses == [400, 404, 400, 400, 400, 404]
    assert _files(tree.root) - before == {tree.out / "laptop-1" / "session.json"}


@pytest.mark.parametrize(
    "route",
    [
        "reply/nope",
        "reply",
        "reply/en_ticket/x",
        "take/nope",
        "take/",
        "variant/nope/0",
        "variant/t01-1/1",
        "variant/t01-1/x",
        "variant/t01-1/-1",
        "variant/t01-1/0/x",
        "variant/t01-2/0",
        "index.html",
        "recorder_page/index.html",
        "api/state/x",
        "api/nothing",
        "replies.json",
    ],
)
def test_a_get_off_the_allow_list_is_refused(tree: Tree, route: str) -> None:
    with serving(recorder_of(tree)) as server:
        assert get(server, route).status == 404


def test_a_reply_whose_file_is_gone_is_not_found(tree: Tree) -> None:
    (tree.replies / "en_ticket.wav").unlink()
    with serving(recorder_of(tree)) as server:
        assert get(server, "reply/en_ticket").status == 404
    no_reply = '[[lines]]\nid = "n01"\nkind = "request"\nlanguage = "english"\n'
    tree.script.write_text(no_reply, encoding="utf-8")
    with serving(recorder_of(tree, replies=None)) as server:
        assert get(server, "reply/en_ticket").status == 404  # no --replies: no reply at all


def _traversals(tree: Tree, server: RecorderServer) -> list[str]:
    """Every way a path could climb out of a served folder: encoded and plain `..`, absolute
    paths, a backslash, each from each route, and as the request's target itself."""
    token = server.token
    env = tree.checkout / ".env"
    climbs = [
        "..%2f..%2f.env",
        "%2e%2e/%2e%2e/.env",
        "../../.env",
        ".env",
        "..%5c..%5c.env",
        "%2e%2e%5c.env",
        quote(str(env), safe=""),
        quote(env.as_posix()),
        env.as_posix().lstrip("/"),
    ]
    routes = ["reply/", "take/", "variant/", "variant/t01-1/", "", "api/", "recorder.js/"]
    targets = [f"/{token}/{route}{climb}" for route in routes for climb in climbs]
    return [
        *targets,
        f"/{token}/../.env",
        "/../.env",
        f"/{token}/..%2f.env",
        str(env).replace(" ", "%20"),
        quote(env.as_posix()),
        f"http://{server.host}/{token}/../../.env",
        f"/{token}/%2e%2e/%2e%2e/%2e%2e/%2e%2e/Ole5-chatbot/.env",
    ]


def test_no_path_from_a_request_reads_a_dotenv(tree: Tree) -> None:
    """Only while the made-up `.env` files are in place does this prove anything: in this
    repository's checkout above `--out` (`../../.env` from `var/golden-audio`), in the old
    repository's, and in each served folder."""
    for folder in (
        tree.checkout,
        tree.root / "Ole5-chatbot",
        tree.out,
        tree.replies,
        tree.talkover,
    ):
        assert (folder / ".env").read_text(encoding="utf-8") == SECRET
    with serving(recorder_of(tree)) as server:
        answers = [
            ask(server, "GET", target, [("Host", server.host)])
            for target in _traversals(tree, server)
        ]
    assert answers and {a.status for a in answers} <= {403, 404}
    assert not [a for a in answers if KEY.encode() in a.body]


@pytest.mark.parametrize("link", ["a folder link", "a file link", "a hard link"])
def test_no_link_leads_the_server_to_a_dotenv(tree: Tree, link: str) -> None:
    """A link below a served folder, to the `.env` above it: the file is reached through no
    link, or it is refused for not being WAV of the SHA-256 recorded, which a link cannot fake."""
    env = tree.checkout / ".env"
    sha = sha256_of(env.read_bytes())
    folder = tree.out / "laptop-1"
    folder.mkdir()
    (folder / "n01-laptop-1-1.json").write_text(
        sidecar("n01-laptop-1-1", "n01", sha), encoding="utf-8"
    )
    (tree.replies / "en_ticket.wav").unlink()
    places = [
        tree.replies / "en_ticket.wav",
        folder / "n01-laptop-1-1.wav",
        tree.talkover / "env.wav",
    ]
    if link == "a folder link":
        link_folder(tree.talkover / "via", tree.checkout)
        segment = "via/.env"
    else:
        segment = "env.wav"
        for place in places:
            try:
                if link == "a hard link":
                    os.link(env, place)
                else:
                    place.symlink_to(env)
            except OSError:
                pytest.skip(
                    "this account may not make symbolic links (Windows without the privilege)"
                )
    write_manifest(tree.manifests / "linked.json", [(segment, sha)])
    golden = (*items(tree), item("t02", ("talkover", segment, sha)))
    with serving(recorder_of(tree, golden=golden)) as server:
        answers = [
            get(server, route)
            for route in ("reply/en_ticket", "take/n01-laptop-1-1", "variant/t02-1/0")
        ]
    assert {a.status for a in answers} <= {404, 409}
    assert not [a for a in answers if KEY.encode() in a.body]


def test_the_recorder_never_writes_through_a_link(tree: Tree) -> None:
    elsewhere = tree.root / "elsewhere"
    elsewhere.mkdir()
    link_folder(tree.out / "laptop-1", elsewhere)
    with serving(recorder_of(tree)) as server:
        answer = post(server, "api/consent", CONSENT)
    assert answer.status == 409 and "link" in answer.json()["error"]
    assert list(elsewhere.iterdir()) == []


def test_what_http_server_refuses_itself_echoes_nothing(tree: Tree) -> None:
    with serving(recorder_of(tree)) as server:
        method = ask(server, "PUT", f"/{server.token}/", [("Host", server.host)])
        line = raw(server, b"GET /made-up-path HTTP/9.9 made-up-words\r\n\r\n")
    assert method.status == 501 and b"PUT" not in method.body
    assert b"400" in line and b"made-up" not in line  # sent as HTTP/0.9: a body, no status line
