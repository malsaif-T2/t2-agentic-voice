"""The flight page in its alpha (apps/flight-voice-agent/web/), run in the fake browser
(tests/browser.py) on its own markup: the box under Options that records the call ticked by
default, its choice in the join token's consent, and the alpha's notice under the call button in
both languages."""

from __future__ import annotations

from pathlib import Path

from tests.browser import text
from tests.flight_voice.page_support import ENGLISH, call, look, page


def test_the_record_box_is_ticked_and_the_alpha_notice_shows_in_both_languages(
    tmp_path: Path,
) -> None:
    shown = page(
        tmp_path,
        [look("alpha"), look("record"), ENGLISH, look("alpha"), look("options"), *call()],
    )
    arabic, box, english, options = shown["snapshots"]
    assert text(arabic) == (
        "نسخة تجريبية: نحفظ المكالمات لتحسين المساعد، وتقدر توقف التسجيل من الخيارات."
    )
    assert text(english) == (
        "Alpha: calls are saved to improve the assistant. You can turn recording off in Options."
    )
    assert "checked" in box["attrs"] and "hidden" not in arabic["attrs"]
    assert "Record this call to help improve the assistant (alpha)." in text(options)
    (minted,) = [r for r in shown["requests"] if r["path"] == "/token"]
    assert minted["body"]["consent"]["record_audio"] is True
