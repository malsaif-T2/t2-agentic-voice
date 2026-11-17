"""The flight agent's persona: its names, the owner's of 2026-11-16 (Saad / سعد, the voice
assistant of T2 Air / طيران تي تو), and every text built from them.

The names are settings (settings.py, `Names` here), so nothing in agent.py holds one. Each text
that holds a name is built from them with `string.Template` (`$persona`, `$airline`,
`$traveler`, ...), so a brace in a text is safe: the greetings, the instructions (read from
instructions/<tag>.md), the pronunciation entry of the airline's code (`T2`, said "tee two" /
«تي تو»: on cards and flight numbers only, never said unless asked) and the vocabulary entry of
the airline's English name.

**The lines' rule.** No fixed line a call speaks as written (a greeting, a progress line) holds
a stop, wait, repeat or listening word of the agent's, a send word of the booking's or a phrase
the guard reads as a booking's claim, so its echo is never heard as the caller's, nor a line
claim a booking (D-062's lists). `breaking` names each name that makes a line break it, so the
settings refuse it at load naming the setting, never its value. The presets' yes words are not
part of the library's public API: a test holds every line free of them too.

Arabic is written plainly, as the app's other word modules write it.
"""

from __future__ import annotations

import re
from importlib.resources import files
from string import Template
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict
from t2_agentic_voice import Phrases, Vocabulary
from t2_agentic_voice.languages import normalize_arabic, provider_text

from flight_voice.airline.profile import TRAVELER, Traveler
from flight_voice.booking import lines
from flight_voice.said import Tag as ReplyTag

# The languages a call is held in, by tag, each with its instructions file.
Tag = Literal["ar-SA", "en"]
TAGS: Final[tuple[Tag, ...]] = ("ar-SA", "en")
_CODE: Final[dict[Tag, Literal["ar", "en"]]] = {"ar-SA": "ar", "en": "en"}

# The greetings, filled with the names and the traveler's first name.
GREETINGS: Final[dict[Tag, Template]] = {
    # hala wallah ..., ma'ak ... min .... ween waddak tsaafir?: hello ..., ... here, from ....
    # Where would you like to travel? (Riyadh's Najdi, the owner's ask of 2026-11-17)
    "ar-SA": Template("هلا والله $traveler، معك $persona من $airline. وين ودّك تسافر؟"),
    "en": Template(
        "Hi $traveler, this is $persona, $airline's voice assistant. Where would you like to fly?"
    ),
}
# The progress lines the tools name (tools/search.py, cabins.py: `searching`; calendar.py:
# `fares`), said while a search runs long.
PROGRESS: Final[dict[Tag, dict[str, str]]] = {
    # ashoof lak wesh fih riHlaat: I am looking up what flights there are for you (Najdi «وش
    # فيه»; never «لحظة», a wait word); ashoof lak arkhas al-ayyaam: the cheapest days for you.
    "ar-SA": {"searching": "أشوف لك وش فيه رحلات.", "fares": "أشوف لك أرخص الأيام."},
    "en": {"searching": "Checking the flights for you.", "fares": "Looking up the cheapest days."},
}
# The terms a transcript should write as the airline writes them, the airline's name after them.
TERMS: Final = (
    "Riyadh",
    "Jeddah",
    "Dubai",
    "Doha",
    "Cairo",
    "Istanbul",
    "London",
    "Heathrow",
    "Paris",
    "Mumbai",
    "Singapore",
    "economy",
    "business",
)


class Names(BaseModel):
    """The persona's and the airline's names in each language, the airline's code and how the
    code is said; the defaults are the owner's picks."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    persona_name_en: str = "Saad"
    persona_name_ar: str = "سعد"
    airline_name_en: str = "T2 Air"
    airline_name_ar: str = "طيران تي تو"
    airline_code: str = "T2"
    airline_code_said_en: str = "tee two"
    airline_code_said_ar: str = "تي تو"


def _fill(names: Names, traveler: Traveler) -> dict[str, str]:
    """What a template is filled with: each name, in English, and in Arabic as `_ar`."""
    return {
        "persona": names.persona_name_en,
        "persona_ar": names.persona_name_ar,
        "airline": names.airline_name_en,
        "airline_ar": names.airline_name_ar,
        "traveler": traveler.first_en,
        "traveler_ar": traveler.first_ar,
        "tier": traveler.tier,
        "tier_ar": traveler.tier_ar,
    }


def filled(names: Names, traveler: Traveler = TRAVELER) -> dict[str, str]:
    """What an instructions template is filled with (`_fill`), for the lean agent's too."""
    return _fill(names, traveler)


def greeting(tag: Tag, names: Names, traveler: Traveler = TRAVELER) -> str:
    """The greeting of a call held in `tag`, in its own script's names."""
    filled = _fill(names, traveler)
    if tag != "en":
        filled |= {k: filled[f"{k}_ar"] for k in ("persona", "airline", "traveler")}
    return GREETINGS[tag].substitute(filled)


def instructions(names: Names, traveler: Traveler = TRAVELER) -> dict[ReplyTag, str]:
    """The talker's instructions for each language, read from instructions/<tag>.md and
    filled with the names and the traveler."""
    folder = files("flight_voice") / "instructions"
    filled = _fill(names, traveler)
    found: dict[ReplyTag, str] = {}
    for tag in TAGS:
        found[tag] = Template((folder / f"{tag}.md").read_text(encoding="utf-8")).substitute(filled)
    return found


def pronounce(names: Names) -> dict[str, dict[str, str]]:
    """The airline's code said in each language: "tee two", «تي تو»."""
    return {
        names.airline_code: {"ar": names.airline_code_said_ar, "en": names.airline_code_said_en}
    }


def vocabulary(names: Names) -> Vocabulary:
    """The terms a transcript should write as the airline does, and the airline's name."""
    return Vocabulary(terms=(*TERMS, names.airline_name_en))


def spoken_lines(names: Names, traveler: Traveler = TRAVELER) -> dict[Tag, tuple[str, ...]]:
    """Each line a call speaks as written, by language: its greeting, then its progress
    lines."""
    return {tag: (greeting(tag, names, traveler), *PROGRESS[tag].values()) for tag in TAGS}


def _form(text: str) -> str:
    """`text` as the rule reads it: folded, lower case, its marks made spaces, one space
    around each word."""
    folded = normalize_arabic(provider_text(text)).lower()
    return f" {' '.join(re.sub(r'[^\w]+', ' ', folded).split())} "


def held_words(line: str, code: Literal["ar", "en"]) -> tuple[str, ...]:
    """The stop, wait, repeat and listening words of the agent's, the booking's send words and
    the claim phrases that `line` holds as whole words."""
    words = Phrases.defaults().words(code)
    claims = [phrase for tag in lines.CLAIMS.phrases for phrase in lines.CLAIMS.for_language(tag)]
    listed = (
        *words.stop,
        *words.wait,
        *words.repeat,
        *words.backchannel,
        *lines.SEND_WORDS[code],
        *claims,
    )
    form = _form(line)
    return tuple(word for word in listed if _form(word) in form)


def _broken(names: Names) -> bool:
    return any(
        held_words(line, _CODE[tag]) for tag, said in spoken_lines(names).items() for line in said
    )


def breaking(names: Names) -> tuple[str, ...]:
    """The fields of `names` whose value alone, the others the defaults, makes a line a call
    speaks hold a word of the rule (the module's docstring)."""
    default = Names()
    return tuple(
        field
        for field in Names.model_fields
        if _broken(default.model_copy(update={field: getattr(names, field)}))
    )
