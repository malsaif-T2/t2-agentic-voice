"""What the flight page's tests share (test_page.py, test_page_segments.py, test_page_recording.py,
test_page_mute.py, test_page_access.py): the page's own files and the library's client served
where the server serves them, run in the fake browser (tests/browser.py) on the page's markup with
the profile's and the bookings' answers (the mock's profile, which books; `REAL`, the real
flights' one, which books nothing and names no traveler); a call started with a made-up access
code; a snapshot of an element by its id, or of the page."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flight_voice.server import VOICE_PREFIX, WEB

from tests.browser import Shown, Step, browse

ROOT = Path(__file__).resolve().parents[2]
CLIENT = (
    ROOT / "packages" / "t2-agentic-voice" / "src" / "t2_agentic_voice" / "api" / "static"
) / "t2v-client.js"
SCRIPT = "<script>alert(1)</script>"
PROFILE = {
    "network": "mock",
    "bookings": True,
    "first_name": {"ar": "خالد", "en": SCRIPT},
    "tier": {"ar": "ذهبي", "en": "Gold"},
    "persona": {"ar": "سعد", "en": "Saad"},
    "airline": {"ar": "طيران تي تو", "en": "T2 Air"},
    "lines": {"ar": ["ودي أرجع لدبي"], "en": ["Back to Dubai", "<b>Business</b> to Paris"]},
}
REAL = {
    "network": "real",
    "bookings": False,
    "persona": {"ar": "سعد", "en": "Saad"},
    "company": {"ar": "تي تو", "en": "T2"},
    "role": {"ar": "مساعد الرحلات", "en": "flight assistant"},
    "lines": {"ar": ["من الرياض لجدة الخميس الجاي"], "en": ["Riyadh to Jeddah next Thursday"]},
}
TRIP = {
    "from": {"ar": "الرياض", "en": "Riyadh"},
    "to": {"ar": "دبي", "en": "Dubai"},
    "travelers": 1,
    "cabin": "economy",
    "flown": False,
}
BOOKINGS = {
    "bookings": [
        TRIP
        | {"reference": "731205", "depart": "2026-11-17", "return_date": None, "total_sar": 640},
        TRIP
        | {
            "reference": "482913",
            "depart": "2026-10-08",
            "return_date": "2026-10-11",
            "total_sar": 1380,
            "flown": True,
        },
    ]
}
ANSWERS = {
    "GET profile": [200, PROFILE],
    "GET bookings": [200, BOOKINGS],
    "POST reset": [200, {"reset": True}],
}
ENGLISH = {"do": "click", "query": ["button.language", 1]}


def page(folder: Path, steps: list[Step], answers: dict[str, Any] | None = None) -> Shown:
    names = ("app.js", "cards.js", "bookings.js", "microphone.js", "orb.js", "texts.js")
    files = {name: WEB / name for name in names}
    files[f"{VOICE_PREFIX[1:]}/client/1/t2v-client.js"] = CLIENT
    return browse(
        folder,
        files,
        entry="app.js",
        page=WEB / "index.html",
        location="http://127.0.0.1:7862/",
        steps=steps,
        answers=ANSWERS if answers is None else answers,
    )


def call(*steps: Step) -> list[Step]:
    return [
        {"do": "set", "id": "code", "value": "made-up-code"},
        {"do": "click", "id": "start"},
        {"do": "open"},
        *steps,
    ]


def look(name: str) -> Step:
    return {"do": "snapshot", "id": name}


def html() -> Step:
    return {"do": "snapshot", "query": ["html", 0]}
