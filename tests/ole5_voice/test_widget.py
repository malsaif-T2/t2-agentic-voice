"""Ole5's widget in plan 005 (Track D): a push-to-talk switch, the fallback when the agent's
voice comes back through the laptop's speakers, with the microphone on only while Space or the
talk button is held; and a clause a stop cut, styled cut. Read as text, as test_server.py reads
the widget (the suite runs no browser); its page's headers, and no inline script or style, are
test_server.py's tests, and no markup inserted test_browser_client.py's."""

from __future__ import annotations

import re

from ole5_voice.server import WEB


def _text(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


def _between(source: str, start: str, end: str) -> str:
    at = source.index(start)
    return source[at : source.index(end, at)]


def test_the_page_holds_the_switch_and_the_button_with_their_labels() -> None:
    page = _text("index.html")
    assert '<input type="checkbox" id="push-to-talk"> <span data-text="pushToTalk"></span>' in page
    talk = re.search(r"<button [^>]*\bid=\"talk\"[^>]*>", page)
    assert talk is not None
    assert 'data-text="talk"' in talk.group() and talk.group().endswith(" disabled>")
    script = _text("widget.js")
    # One label of each in Arabic and in English, set with textContent by `render`.
    assert len(re.findall(r'^    pushToTalk: "[^"]+",$', script, re.MULTILINE)) == 2
    assert len(re.findall(r'^    talk: "[^"]+",$', script, re.MULTILINE)) == 2
    assert "node.textContent = words()[node.dataset.text];" in script


def test_push_to_talk_holds_the_microphone_open_only_while_held() -> None:
    script = _text("widget.js")
    start = _between(script, "async function start() {", "\n}\n")
    assert 'pushToTalk: $("push-to-talk").checked,' in start
    assert 'call.pushToTalk = $("push-to-talk").checked;' in start
    switch = _between(script, '$("push-to-talk").addEventListener("change"', "});")
    assert 'if (page.call) page.call.pushToTalk = $("push-to-talk").checked;' in switch
    assert "talk(false);" in switch
    talk = _between(script, "function talk(held) {", "\n}\n")
    assert "page.call?.talk(held);" in talk
    space = _between(script, "function space(event) {", "\n}\n")
    assert (
        'if (event.code !== "Space" || !page.call || !$("push-to-talk").checked) return;' in space
    )
    assert "event.preventDefault();" in space
    assert 'if (event.type === "keyup") talk(false);' in space
    assert "else if (!event.repeat) talk(true);" in space
    assert 'document.addEventListener("keydown", space);' in script
    assert 'document.addEventListener("keyup", space);' in script
    held = _between(script, '$("talk").addEventListener("pointerdown"', "});")
    assert "talk(true);" in held and 'if ($("talk").disabled) return;' in held
    assert 'for (const name of ["pointerup", "pointercancel", "lostpointercapture"]) {' in script
    assert '$("talk").addEventListener(name, () => talk(false));' in script
    assert 'globalThis.addEventListener("blur", () => talk(false));' in script
    # The button is usable only while a call runs with the switch on; the call's end lets go.
    talkable = _between(script, "function talkable() {", "\n}\n")
    assert '$("talk").disabled = $("end").disabled || !$("push-to-talk").checked;' in talkable
    assert "talk(false);" in _between(script, "function ended(e) {", "\n}\n")


def test_a_cut_clause_is_styled_cut() -> None:
    script = _text("widget.js")
    caption = _between(script, "function caption(c) {", "\n}\n")
    assert 'shown.parts[index] = document.createElement("span");' in caption
    assert "shown.parts[index].textContent = c.text;" in caption
    assert 'shown.parts[index].classList.toggle("cut", c.cut === true);' in caption
    style = _text("widget.css")
    assert ".captions .cut { color: var(--muted); }" in style
    assert '.captions .cut::after { content: "\\2026"; }' in style
    assert 'button.talk[aria-pressed="true"]' in style
