"""The browser side of the dev console's choice of speech-to-text (api/static/dev-console.js,
t2v-client.js; api/dev_stt.py): the console fills its pickers from `GET dev/stt`, the one
remembered in this browser when the menu still holds it, else the settings' own; its Start
sends the call's choice to `POST dev/stt` after the join and before the offer; a change is
remembered; with no localStorage, or no menu, the pickers fall back and a call sends no
choice. Each turn's line names who heard it and the request's time. Run in the fake browser
(tests/browser.py)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.browser import Shown, browse, descendants, text

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "packages" / "t2-agentic-voice" / "src" / "t2_agentic_voice" / "api" / "static"
LOCATION = "http://127.0.0.1:7860/voice/dev/console"
KEY = "t2v.dev-console.stt"
MENU = {
    "providers": [
        {"provider": "groq", "models": ["whisper-large-v3", "whisper-large-v3-turbo"]},
        {"provider": "elevenlabs", "models": ["scribe_v3"]},
    ],
    "live_languages": ["session", "auto"],
    "default": {"provider": "groq", "model": "whisper-large-v3", "live_language": "session"},
}
SCRIBE = {"provider": "elevenlabs", "model": "scribe_v3", "live_language": "auto"}


def _console(
    folder: Path,
    steps: list[dict[str, Any]],
    *,
    menu: object = MENU,
    storage: dict[str, str] | None = None,
    feed: list[dict[str, Any]] | None = None,
) -> Shown:
    answers: dict[str, Any] = {
        "GET stt": [200, menu] if menu is not None else [404, {}],
        "POST stt": [204, None],
    }
    if feed is not None:  # one answer, then none: the console waits before it asks again
        first = {"feed": "f-1", "last": len(feed), "records": feed}
        answers["GET feed"] = {"sequence": [[200, first], [404, {}]]}
    return browse(
        folder,
        {
            "voice/dev/console.js": STATIC / "dev-console.js",
            "voice/client/1/t2v-client.js": STATIC / "t2v-client.js",
        },
        entry="voice/dev/console.js",
        location=LOCATION,
        page=STATIC / "dev-console.html",
        steps=steps,
        answers=answers,
        storage=storage,
    )


def _calls(shown: Shown) -> list[tuple[str, str]]:
    return [(r["method"], r["path"]) for r in shown["requests"] if r["path"] != "/voice/dev/feed"]


def _snap(name: str) -> dict[str, str]:
    return {"do": "snapshot", "id": name}


def test_the_remembered_choice_is_picked_and_sent_before_the_offer(tmp_path: Path) -> None:
    shown = _console(
        tmp_path,
        [_snap("stt-provider"), _snap("stt-model"), {"do": "click", "id": "start"}],
        storage={KEY: json.dumps(SCRIBE)},
    )
    provider, model = shown["snapshots"]
    assert [text(option) for option in provider["children"]] == ["groq", "elevenlabs"]
    assert [text(option) for option in model["children"]] == ["scribe_v3"]
    calls = _calls(shown)
    join, choose, offer = (
        calls.index(("POST", "/voice/join")),
        calls.index(("POST", "/voice/dev/stt")),
        calls.index(("POST", "/voice/offer")),
    )
    assert join < choose < offer
    (sent,) = [
        r["body"]
        for r in shown["requests"]
        if r["method"] == "POST" and r["path"] == "/voice/dev/stt"
    ]
    assert sent == {"call_id": "c-1", "offer_secret": "made-up-secret", **SCRIBE}


def test_a_change_is_remembered_and_a_stale_one_falls_back_to_the_settings_own(
    tmp_path: Path,
) -> None:
    stale = {"provider": "soniox", "model": "stt-async-v6", "live_language": "detected"}
    shown = _console(
        tmp_path,
        [
            {"do": "set", "id": "stt-model", "value": "whisper-large-v3-turbo"},
            {"do": "change", "id": "stt-model"},
            {"do": "click", "id": "start"},
        ],
        storage={KEY: json.dumps(stale)},
    )
    turbo = {"provider": "groq", "model": "whisper-large-v3-turbo", "live_language": "session"}
    assert json.loads(shown["storage"][KEY]) == turbo
    (sent,) = [
        r["body"]
        for r in shown["requests"]
        if r["method"] == "POST" and r["path"] == "/voice/dev/stt"
    ]
    assert {key: sent[key] for key in turbo} == turbo


def test_with_no_storage_and_no_menu_a_call_sends_no_choice(tmp_path: Path) -> None:
    shown = _console(tmp_path, [_snap("stt-note"), {"do": "click", "id": "start"}], menu=None)
    assert "unavailable" in text(shown["snapshots"][0])
    calls = _calls(shown)
    assert ("POST", "/voice/offer") in calls and ("POST", "/voice/dev/stt") not in calls
    with_menu = _console(tmp_path / "menu", [{"do": "click", "id": "start"}])
    (sent,) = [
        r["body"]
        for r in with_menu["requests"]
        if r["method"] == "POST" and r["path"] == "/voice/dev/stt"
    ]
    assert sent["provider"] == "groq" and sent["model"] == "whisper-large-v3"


def test_each_turns_line_names_who_heard_it_and_the_requests_time(tmp_path: Path) -> None:
    at = "2026-11-16T12:00:00+00:00"
    scribe = {"provider": "elevenlabs", "model": "scribe_v3"}

    def record(seq: int, kind: str, event: dict[str, Any], **extra: Any) -> dict[str, Any]:
        body = {"call_id": "c-9", "at": at, **event}
        return {"seq": seq, "type": kind, "call_id": "c-9", "ended": False, "event": body, **extra}

    feed = [
        record(1, "CallStarted", {"turn_id": None}),
        record(2, "UserTurnEnded", {"turn_id": 0, "heard": "hello"}, heard_by=scribe),
        record(3, "TurnMetrics", {"turn_id": 0, "stt_ms": 640.4, "usage": []}, heard_by=scribe),
    ]
    shown = _console(tmp_path, [_snap("turns")], feed=feed)
    lines = [text(node) for node in descendants(shown["snapshots"][0])]
    assert "Heard by elevenlabs · scribe_v3 · request 640 ms" in lines
