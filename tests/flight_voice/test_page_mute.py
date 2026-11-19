"""The flight page's mute button (apps/flight-voice-agent/web/microphone.js), run in the fake
browser (tests/browser.py) on its own markup, the library's client reading each step's microphone
track: hidden and disabled with no call; muting through the client's own switch (push to talk on,
never held), so the track sends nothing while the call goes on, the state line saying so; unmuting
back to the push-to-talk box's value; and a new call starting unmuted."""

from __future__ import annotations

from pathlib import Path

from t2_agentic_voice.voice.protocol import Ended, State, wire

from tests.browser import Step, receive, text
from tests.flight_voice.page_support import call, look, page

MUTE = {"do": "click", "id": "mute"}
HEARD = {"do": "microphone"}
LISTENING = receive(wire(State(state="listening")))
PUSH_TO_TALK: list[Step] = [
    {"do": "check", "id": "push-to-talk", "value": True},
    {"do": "change", "id": "push-to-talk"},
]


def test_the_mute_button_is_hidden_and_disabled_with_no_call(tmp_path: Path) -> None:
    shown = page(tmp_path, [look("mute"), MUTE, look("mute")])
    before, clicked = shown["snapshots"]
    assert "disabled" in before["attrs"] and "hidden" in before["attrs"]
    assert before["attrs"]["aria-label"] == "كتم" and before["attrs"]["aria-pressed"] == "false"
    assert clicked["attrs"]["aria-pressed"] == "false"


def test_mute_silences_the_microphone_and_unmute_brings_it_back(tmp_path: Path) -> None:
    shown = page(
        tmp_path,
        call(
            LISTENING,
            look("mute"),
            HEARD,
            MUTE,
            HEARD,
            look("mute"),
            look("state"),
            look("talk"),
            MUTE,
            HEARD,
            look("mute"),
            look("state"),
        ),
    )
    live, muted, state, talk, unmuted, back = shown["snapshots"]
    assert "disabled" not in live["attrs"] and "hidden" not in live["attrs"]
    assert shown["microphone"] == [[True], [False], [True]]
    assert (
        muted["attrs"]["aria-pressed"] == "true" and muted["attrs"]["aria-label"] == "إلغاء الكتم"
    )
    assert text(state) == "يسمعك · مكتوم"
    assert "disabled" in talk["attrs"]
    assert unmuted["attrs"]["aria-pressed"] == "false" and unmuted["attrs"]["aria-label"] == "كتم"
    assert text(back) == "يسمعك"
    assert not [m for m in shown["sent"] if m.get("type") == "hangup"]  # the call went on


def test_unmute_gives_push_to_talk_back_as_the_box_says(tmp_path: Path) -> None:
    shown = page(
        tmp_path,
        call(
            *PUSH_TO_TALK, HEARD, look("talk"), MUTE, look("talk"), HEARD, MUTE, HEARD, look("talk")
        ),
    )
    held_off, muted, unmuted = shown["snapshots"]
    assert shown["microphone"] == [[False], [False], [False]]  # push to talk, never held
    assert "disabled" not in held_off["attrs"]
    assert "disabled" in muted["attrs"]
    assert "disabled" not in unmuted["attrs"] and unmuted["attrs"]["aria-pressed"] == "false"


def test_a_new_call_starts_unmuted(tmp_path: Path) -> None:
    shown = page(
        tmp_path,
        [
            *call(MUTE, receive(wire(Ended(reason="hangup"))), look("mute")),
            *call(look("mute"), HEARD),
        ],
    )
    over, again = shown["snapshots"]
    assert "hidden" in over["attrs"] and "disabled" in over["attrs"]
    assert over["attrs"]["aria-pressed"] == "false"
    assert "disabled" not in again["attrs"] and again["attrs"]["aria-pressed"] == "false"
    assert shown["microphone"][-1][-1] is True  # the new call's microphone is heard
