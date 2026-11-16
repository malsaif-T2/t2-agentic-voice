"""The flight agent's words with no number in them, by the reply's language (`words.py`).

A reply in Saudi Arabic (`ar-SA`) is given each word's Saudi form, and its Modern Standard Arabic
form beside it for a caller who speaks MSA; a reply in MSA (`ar`) its MSA form; a reply in
English its English form. Numbers are never written in a reply's words: the talker writes them
in digits, the output guard checks them, and the speaking rules say them. Only the lines the app
renders in code, the booking's read-back and its outcome, say numbers, times, dates and amounts
in words (`numbers.py`), by register.
"""

from __future__ import annotations

from typing import Final, Literal

from flight_voice.airline.airports import Register

# A reply's language, as the library's call context gives it.
Tag = Literal["ar-SA", "ar", "en"]
_PRIMARY: Final[dict[Tag, Register]] = {"ar-SA": "saudi", "ar": "msa", "en": "en"}


def register(tag: Tag) -> Register:
    """The register a reply in `tag` is said in: Saudi, MSA or English."""
    return _PRIMARY[tag]


def msa_too(tag: Tag) -> bool:
    """Whether a reply in `tag` is also given the MSA form: a Saudi reply is."""
    return tag == "ar-SA"


def arabic(tag: Tag) -> bool:
    """Whether a reply in `tag` is in Arabic."""
    return tag != "en"
