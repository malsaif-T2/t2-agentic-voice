"""The browser side of plan 005's interruptions (Track D): the reference client
`api/static/t2v-client.js` lowers the agent's playback on `duck` and brings it back on `unduck`,
on its own `stop()`, on a new reply's first caption and at the call's end; a caption marked `cut`
ends its clause's playback and reaches the page marked; and push-to-talk, off by default, turns
the microphone's track on only while the page holds it. The dev page shows the volume and the cut
mark and offers push-to-talk. Read as text, as test_browser_client.py reads them, since the suite
runs no browser (the integrator's browser pane and the owner's live calls check the rest)."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "packages" / "t2-agentic-voice" / "src" / "t2_agentic_voice" / "api" / "static"
CLIENT = STATIC / "t2v-client.js"
DEV_PAGE = STATIC / "dev.html"
FIXTURE = Path(__file__).parent / "fixtures" / "t2v_protocol.json"


def _source() -> str:
    return CLIENT.read_text(encoding="utf-8")


def _between(source: str, start: str, end: str) -> str:
    """The text from `start` to the next `end` after it: one method's body, say."""
    at = source.index(start)
    return source[at : source.index(end, at)]


def _receive(source: str) -> str:
    return _between(source, "  #receive(data) {", "\n  }\n")


def test_duck_lowers_the_element_the_agent_plays_through_and_unduck_restores_it() -> None:
    source = _source()
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))["data_channel"]
    assert fixture["session_to_client"]["duck"] == {"level": "number"}
    receive = _receive(source)
    duck = _between(receive, 'message.type === "duck"', "} else if")
    assert 'if (typeof level !== "number" || !(level >= 0 && level <= 1)) return;' in duck
    assert "this.#volume(level);" in duck
    unduck = _between(receive, 'message.type === "unduck"', "} else if")
    assert "this.#volume(1);" in unduck
    # The level is of the volume the call started at, on the element the agent plays through.
    assert "this.#audio.srcObject = stream;" in _between(source, "  #play(event) {", "\n  }\n")
    assert "this.#full = this.#audio.volume;" in source
    volume = _between(source, "  #volume(level) {", "\n  }\n")
    assert "this.#audio.volume = this.#full * level;" in volume
    assert 'this.#emit("volume", { level });' in volume
    assert "if (level === this.#level) return;" in volume


def test_the_volume_comes_back_on_stop_a_new_reply_and_the_end() -> None:
    """So no reply plays lowered whatever reaches the client (the prototype's `web/voice.js`,
    lines 162-173 and 421)."""
    source = _source()
    stop = _between(source, "  stop() {", "\n  }\n")
    assert stop.index("this.#volume(1);") < stop.index('this.#send("stop")')
    caption = _between(source, "  #agentCaption(caption) {", "\n  }\n")
    assert "caption.reply_id > this.#reply" in caption
    assert caption.index("this.#reply = caption.reply_id;") < caption.index("this.#volume(1);")
    finish = _between(source, "  #finish(reason, quiet = false) {", "\n  }\n")
    assert finish.index("this.#volume(1);") < finish.index('this.#emit("ended"')
    assert "#reply = -1;" in source  # the greeting, reply 0, is a new reply too


def test_a_cut_caption_ends_its_clauses_playback_and_reaches_the_page_marked() -> None:
    source = _source()
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))["data_channel"]
    assert fixture["session_to_client"]["caption"]["cut"] == "boolean"
    receive = _receive(source)
    caption = _between(receive, 'message.type === "caption"', "} else if")
    assert "message.cut = message.cut === true;" in caption
    assert "this.#agentCaption(message);" in caption
    assert receive.rstrip().endswith("this.#emit(message.type, message);")
    agent = _between(source, "  #agentCaption(caption) {", "\n  }\n")
    # A cut clause is not queued to be played again: the playback watch drops its reply.
    cut = _between(agent, "if (caption.cut) {", "}")
    assert "this.#playback?.dropped();" in cut and "return;" in cut
    assert agent.index("if (caption.cut) {") < agent.index("this.#playback?.captioned(caption);")


def test_push_to_talk_is_off_by_default_and_opens_the_track_only_while_held() -> None:
    source = _source()
    assert "#pushToTalk = false;" in source and "#held = false;" in source
    assert "this.#pushToTalk = options.pushToTalk === true;" in source
    microphone = _between(source, "  #microphone() {", "\n  }\n")
    assert "if (this.#track) this.#track.enabled = !this.#pushToTalk || this.#held;" in microphone
    talk = _between(source, "  talk(held) {", "\n  }\n")
    assert talk.index("this.#held = held === true;") < talk.index("this.#microphone();")
    switch = _between(source, "  set pushToTalk(on) {", "\n  }\n")
    assert "this.#pushToTalk = on === true;" in switch
    assert "this.#held = false;" in switch and "this.#microphone();" in switch
    # Set before the track is offered, so no sound leaves before the page holds it.
    begin = _between(source, "  async #begin() {", "\n  }\n")
    assert begin.index("this.#microphone();") < begin.index("addTransceiver")


def test_the_dev_page_shows_the_volume_and_the_cut_mark_and_offers_push_to_talk() -> None:
    page = DEV_PAGE.read_text(encoding="utf-8")
    assert '<input type="checkbox" id="push-to-talk">' in page
    assert re.search(r'<button type="button" id="talk"[^>]*\bdisabled>', page)
    assert '<output id="volume">100%</output>' in page
    dev = _source()[_source().index("function devPage(page) {") :]
    assert "c.cut ? `${c.text} [cut]` : c.text" in dev
    assert '$("volume").textContent = `${Math.round(v.level * 100)}%`' in dev
    assert 'pushToTalk: $("push-to-talk").checked,' in dev
    assert 'if (call) call.pushToTalk = $("push-to-talk").checked;' in dev
    held = _between(dev, '$("talk").addEventListener("pointerdown"', "});")
    assert "talk(true);" in held
    assert 'for (const name of ["pointerup", "pointercancel", "lostpointercapture"]) {' in dev
    assert '$("talk").addEventListener(name, () => talk(false));' in dev
    assert "call?.talk(held);" in dev
