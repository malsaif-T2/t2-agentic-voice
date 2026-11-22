"""The flight page's call choices under Options (apps/flight-voice-agent/web/choices.js), run in
the fake browser (tests/browser.py) on its own markup: the three menus filled from the server's
(`GET voice/choices`) in Arabic and in English, the server's own selected and marked, a pick
kept across the language switch; hidden, and no choice ever sent, when the server answers
anything but its menu; fixed while a call runs; a changed pick sent between the join and the
offer by ids alone, nothing when nothing changed; an empty group's menu hidden, a group with no
default starting on "Server's own"; an id shown as text, never markup; nothing kept in storage;
and a refused choice failing the start with the page's own words."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from t2_agentic_voice.voice.protocol import Ended, wire

from tests.browser import Shown, receive, text
from tests.flight_voice.page_support import ANSWERS, ENGLISH, call, look, page

MENU: dict[str, Any] = {
    "stt": [
        {"id": "whisper", "provider": "groq", "model": "whisper-large-v3"},
        {"id": "scribe", "provider": "elevenlabs", "model": "scribe_v3"},
    ],
    "models": [
        {
            "id": "gpt-oss-120b",
            "provider": "groq",
            "model": "openai/gpt-oss-120b",
            "reasoning_effort": "medium",
        },
        {"id": "gpt-5.5", "provider": "openai", "model": "gpt-5.5", "reasoning_effort": "none"},
    ],
    "voices": [
        {"id": "orpheus", "provider": "groq", "models": ["canopylabs/orpheus-arabic-saudi"]},
        {"id": "telnyx-bayan", "provider": "telnyx", "models": ["Telnyx.Bayan"]},
    ],
    "default": {"stt": "scribe", "model": "gpt-oss-120b", "voice": "orpheus"},
}
CHOOSING = ANSWERS | {"GET choices": [200, MENU], "POST choices": [204, None]}


def _choose(id_: str, value: str) -> dict[str, Any]:
    return {"do": "set", "id": id_, "value": value}


def _labels(select: Shown) -> list[str]:
    return [text(option) for option in select["children"]]


def _posted(shown: Shown) -> list[Shown]:
    return [r for r in shown["requests"] if r["method"] == "POST" and r["path"] == "/voice/choices"]


def _paths(shown: Shown) -> list[str]:
    return [r["path"] for r in shown["requests"] if r["method"] == "POST"]


def test_the_menus_are_filled_in_both_languages_the_default_marked_and_a_pick_kept(
    tmp_path: Path,
) -> None:
    steps = [
        look("choices"),
        look("choice-stt"),
        look("choice-model"),
        look("choice-voice"),
        _choose("choice-model", "gpt-5.5"),
        ENGLISH,
        look("choice-stt"),
        look("choice-model"),
    ]
    shown = page(tmp_path, steps, CHOOSING)
    box, stt, model, voice, english_stt, english_model = shown["snapshots"]
    assert "hidden" not in box["attrs"]
    assert _labels(stt) == ["Whisper (Groq)", "ElevenLabs Scribe (الافتراضي)"]
    assert stt["value"] == "scribe" and model["value"] == "gpt-oss-120b"
    assert _labels(model) == ["gpt-oss-120b (Groq) (الافتراضي)", "GPT-5.5 (OpenAI)"]
    assert _labels(voice) == ["Canopy Labs Orpheus (Groq) (الافتراضي)", "Telnyx Bayan (Jasem)"]
    assert _labels(english_stt) == ["Whisper (Groq)", "ElevenLabs Scribe (default)"]
    assert english_model["value"] == "gpt-5.5"  # kept across the switch
    assert _labels(english_model) == ["gpt-oss-120b (Groq) (default)", "GPT-5.5 (OpenAI)"]


def test_a_changed_pick_is_sent_by_ids_alone_between_the_join_and_the_offer(
    tmp_path: Path,
) -> None:
    steps = [_choose("choice-model", "gpt-5.5"), _choose("choice-voice", "telnyx-bayan"), *call()]
    shown = page(tmp_path, steps, CHOOSING)
    paths = _paths(shown)
    join, chose, offer = (paths.index(p) for p in ("/voice/join", "/voice/choices", "/voice/offer"))
    assert join < chose < offer
    (sent,) = _posted(shown)
    assert sent["type"] == "application/json"
    assert sent["body"] == {
        "call_id": "c-1",
        "offer_secret": "made-up-secret",
        "model": "gpt-5.5",
        "voice": "telnyx-bayan",
    }


def test_nothing_changed_sends_no_choice(tmp_path: Path) -> None:
    shown = page(tmp_path, call(look("end")), CHOOSING)
    assert "/voice/choices" not in _paths(shown)
    assert "/voice/offer" in _paths(shown)
    assert "hidden" not in shown["snapshots"][0]["attrs"]  # the call started


def test_a_server_that_offers_no_choice_leaves_the_menus_hidden_and_sends_none(
    tmp_path: Path,
) -> None:
    for at, answers in enumerate(
        (
            ANSWERS,  # the route's 404: server.call_choices off
            ANSWERS | {"GET choices": [503, {"code": "not_started"}]},
            ANSWERS | {"GET choices": [200, ["not", "a", "menu"]]},
            ANSWERS | {"GET choices": [200, {"stt": [], "models": [{"id": 5}], "voices": "x"}]},
        )
    ):
        folder = tmp_path / str(at)
        folder.mkdir()
        shown = page(folder, [look("choices"), _choose("choice-stt", "whisper"), *call()], answers)
        assert "hidden" in shown["snapshots"][0]["attrs"]
        assert "/voice/choices" not in _paths(shown) and "/voice/offer" in _paths(shown)


def test_the_menus_are_fixed_while_a_call_runs(tmp_path: Path) -> None:
    steps = call(look("choice-stt"), receive(wire(Ended(reason="hangup"))), look("choice-stt"))
    during, after = page(tmp_path, steps, CHOOSING)["snapshots"]
    assert "disabled" in during["attrs"] and "disabled" not in after["attrs"]


def test_an_empty_group_is_hidden_and_one_with_no_default_starts_on_the_servers_own(
    tmp_path: Path,
) -> None:
    menu = MENU | {"voices": [], "default": {"stt": None, "model": "gpt-oss-120b", "voice": None}}
    answers = CHOOSING | {"GET choices": [200, menu]}
    steps = [look("choice-voice-field"), look("choice-stt-field"), look("choice-stt"), *call()]
    shown = page(tmp_path, steps, answers)
    voice_field, stt_field, stt = shown["snapshots"]
    assert "hidden" in voice_field["attrs"] and "hidden" not in stt_field["attrs"]
    assert _labels(stt) == ["إعداد الخادم", "Whisper (Groq)", "ElevenLabs Scribe"]
    assert stt["value"] == ""
    assert "/voice/choices" not in _paths(shown)


def test_an_unknown_id_is_shown_as_text_and_sent_as_given(tmp_path: Path) -> None:
    markup = "<b>x</b>"
    menu = MENU | {"stt": [*MENU["stt"], {"id": markup, "provider": "groq", "model": "m"}]}
    answers = CHOOSING | {"GET choices": [200, menu]}
    shown = page(tmp_path, [look("choice-stt"), _choose("choice-stt", markup), *call()], answers)
    assert _labels(shown["snapshots"][0])[-1] == markup  # textContent: markup would throw
    (sent,) = _posted(shown)
    assert sent["body"]["stt"] == markup


def test_a_pick_the_menu_never_offered_is_not_sent(tmp_path: Path) -> None:
    shown = page(tmp_path, [_choose("choice-voice", "klingon"), *call()], CHOOSING)
    assert "/voice/choices" not in _paths(shown)


def test_the_choice_is_kept_in_no_storage(tmp_path: Path) -> None:
    steps = [_choose("choice-stt", "whisper"), ENGLISH, *call()]
    shown = page(tmp_path, steps, CHOOSING, storage={})
    assert shown["storage"] == {}
    assert "/voice/choices" in _paths(shown)


def test_a_refused_choice_fails_the_start_with_the_pages_words(tmp_path: Path) -> None:
    refused = [400, {"code": "invalid_request", "message": "This server offers no such choice."}]
    answers = CHOOSING | {"POST choices": refused}
    steps = [
        _choose("choice-stt", "whisper"),
        {"do": "set", "id": "code", "value": "made-up-code"},
        {"do": "click", "id": "start"},
        look("message"),
        look("start"),
    ]
    shown = page(tmp_path, steps, answers)
    said, start = shown["snapshots"]
    assert text(said) == "تعذّر بدء المكالمة بهذه الخيارات. أعد تحميل الصفحة أو اختر غيرها."
    assert "hidden" not in start["attrs"] and "/voice/offer" not in _paths(shown)
