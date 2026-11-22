"""The browser side of an app's call choices (api/static/t2v-client.js's `choice`;
api/choices_route.py): the client sends the ids an app's page gives to `POST choices` after the
join and before the offer, with the call's ID and offer secret alone beside them; it sends
nothing when no id is given; the dev console's `sttChoice` still goes to `dev/stt`; and a
refused choice fails the start, before any offer, as a refused join does. Run in the fake
browser (tests/browser.py) on the client alone."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.browser import Shown, browse

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "packages" / "t2-agentic-voice" / "src" / "t2_agentic_voice" / "api" / "static"
REFUSED = {"code": "invalid_request", "message": "no such choice", "notice": None, "reference": "r"}


def _started(folder: Path, options: dict[str, Any], **answers: Any) -> Shown:
    return browse(
        folder,
        {"t2v-client.js": CLIENT / "t2v-client.js"},
        entry="t2v-client.js",
        location="http://127.0.0.1:7860/",
        steps=[{"do": "start", "options": options}],
        answers={"POST choices": [204, None], "POST stt": [204, None], **answers},
    )


def _paths(shown: Shown) -> list[str]:
    return [r["path"] for r in shown["requests"] if r["method"] == "POST"]


def test_a_choice_is_sent_between_the_join_and_the_offer_with_its_ids_alone(
    tmp_path: Path,
) -> None:
    shown = _started(tmp_path, {"choice": {"stt": "scribe", "voice": ""}})
    paths = _paths(shown)
    assert paths.index("/voice/join") < paths.index("/voice/choices") < paths.index("/voice/offer")
    (sent,) = [r for r in shown["requests"] if r["path"] == "/voice/choices"]
    assert sent["type"] == "application/json"
    assert sent["body"] == {"call_id": "c-1", "offer_secret": "made-up-secret", "stt": "scribe"}


def test_no_choice_or_one_of_empty_ids_sends_nothing(tmp_path: Path) -> None:
    for name, options in {"none": {}, "empty": {"choice": {"stt": "", "model": None}}}.items():
        shown = _started(tmp_path / name, options)
        assert "/voice/choices" not in _paths(shown) and "/voice/offer" in _paths(shown)


def test_the_dev_consoles_choice_still_goes_to_its_own_route(tmp_path: Path) -> None:
    stt = {"provider": "groq", "model": "whisper-large-v3", "live_language": "session"}
    paths = _paths(_started(tmp_path, {"sttChoice": stt}))
    assert "/voice/dev/stt" in paths and "/voice/choices" not in paths


def test_a_refused_choice_fails_the_start_before_any_offer(tmp_path: Path) -> None:
    shown = _started(tmp_path, {"choice": {"model": "klingon"}}, **{"POST choices": [400, REFUSED]})
    assert shown["failed"] == "invalid_request"
    assert "/voice/offer" not in _paths(shown)
