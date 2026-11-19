"""The flight page's access code by the profile's `access` (apps/flight-voice-agent/web/app.js),
run in the fake browser (tests/browser.py) on its own markup: on an open line ("open") the code's
field is hidden, no code is asked, and the token request carries the consent alone; on a line
that asks one ("code", or no `access` at all, test_page.py) the field shows and a call needs it."""

from __future__ import annotations

from pathlib import Path

from tests.browser import text
from tests.flight_voice.page_support import ANSWERS, PROFILE, call, look, page

START = [{"do": "click", "id": "start"}, {"do": "open"}]


def test_an_open_line_asks_no_code_and_sends_none(tmp_path: Path) -> None:
    opened = ANSWERS | {"GET profile": [200, PROFILE | {"access": "open"}]}
    shown = page(tmp_path, [look("code-field"), *START, look("message"), look("end")], opened)
    field, said, end = shown["snapshots"]
    assert "hidden" in field["attrs"]
    assert text(said) == "" and "hidden" not in end["attrs"]  # the call started, no code asked
    (minted,) = [r for r in shown["requests"] if r["path"] == "/token"]
    assert minted["body"] == {"consent": {"version": "m2-owner-test-1", "record_audio": True}}
    assert [r["path"] for r in shown["requests"]].count("/voice/join") == 1


def test_a_line_that_asks_a_code_keeps_asking_it(tmp_path: Path) -> None:
    coded = ANSWERS | {"GET profile": [200, PROFILE | {"access": "code"}]}
    shown = page(
        tmp_path,
        [look("code-field"), {"do": "click", "id": "start"}, look("message"), *call()],
        coded,
    )
    field, said = shown["snapshots"]
    assert "hidden" not in field["attrs"]
    assert text(said) == "اكتب رمز الدخول في الخيارات، ثم ابدأ المكالمة."
    (minted,) = [r for r in shown["requests"] if r["path"] == "/token"]
    assert minted["body"]["code"] == "made-up-code"
