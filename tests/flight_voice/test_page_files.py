"""The flight agent's page files as text (apps/flight-voice-agent/web/): no inline script or
style and nothing loaded from another origin, so the page headers' policy holds; the look
mirrored for Arabic by logical properties alone, never a physical side; a phone's width with a
16px gutter and long text wrapped; every file served, and each at or under 300 lines."""

from __future__ import annotations

import re

from flight_voice.server import FILES, WEB

PAGE = (WEB / "index.html").read_text(encoding="utf-8")
STYLE = (WEB / "app.css").read_text(encoding="utf-8")


def test_the_page_holds_no_inline_script_or_style_and_nothing_from_elsewhere() -> None:
    assert re.findall(r"<script(?![^>]*\bsrc=)", PAGE) == []
    assert " style=" not in PAGE and "<style" not in PAGE
    assert re.findall(r"\bon[a-z]+=", PAGE) == []
    assert "http://" not in PAGE.replace("http://www.w3.org", "")
    assert "https://" not in PAGE
    assert '<html lang="ar" dir="rtl">' in PAGE


def test_the_look_uses_no_physical_side() -> None:
    rules = re.sub(r"/\*.*?\*/", "", STYLE, flags=re.DOTALL)
    assert re.findall(r"\b(left|right)\b", rules) == []
    markup = re.sub(r"<!--.*?-->", "", PAGE, flags=re.DOTALL)
    assert re.findall(r"\b(left|right)\b", markup) == []
    for name in ("app.js", "cards.js", "bookings.js"):
        code = (WEB / name).read_text(encoding="utf-8")
        assert re.findall(r"\.style\.|[\"'](?:left|right)[\"']", code) == [], name
    assert "inline-start" in rules and "inline-end" in rules


def test_the_page_fits_a_phone() -> None:
    assert "padding: 16px;" in STYLE
    assert "padding-inline: 16px;" in STYLE
    assert "overflow-wrap: anywhere;" in STYLE
    assert "@media (max-width: 480px)" in STYLE
    assert 'name="viewport" content="width=device-width, initial-scale=1"' in PAGE
    assert "@media (prefers-color-scheme: dark)" in STYLE
    assert "@media (prefers-reduced-motion: reduce)" in STYLE


def test_every_file_is_served_and_none_passes_300_lines() -> None:
    served = {name for name, _ in FILES.values()}
    assert served == {p.name for p in WEB.iterdir() if p.is_file()}
    for name in served:
        assert len((WEB / name).read_text(encoding="utf-8").splitlines()) <= 300, name
