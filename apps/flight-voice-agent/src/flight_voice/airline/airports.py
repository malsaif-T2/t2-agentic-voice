"""The mock airline's ten airports: each one's code, its city and airport in English and Arabic,
its fixed offset from UTC, and the names a caller may give it; the city said alone, "to" it and
"from" it in each register; and the match of what a caller said against the names.

Callers name cities, not codes, so a tool passes what the caller said and `find_airport` matches
it against every airport's names after `normalize_arabic` (diacritics and letter forms folded,
lower case, punctuation read as space). A name no airport holds is `None`, never a guess: the
tools say it is not served.

Each airport keeps one offset all year, with no zone database: Riyadh keeps UTC+3 with no summer
time, and the booking window ends before Europe's summer time begins (2027-03-28), so London and
Paris keep their winter offsets inside it. Arabic is written plainly, as Ole5's data modules do.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Final, Literal, get_args

from t2_agentic_voice.languages import normalize_arabic

Code = Literal["RUH", "JED", "DXB", "DOH", "CAI", "IST", "LHR", "CDG", "BOM", "SIN"]
CODES: Final[tuple[Code, ...]] = get_args(Code)
# The registers a fixed form is said in: Saudi Arabic, Modern Standard Arabic, English.
Register = Literal["saudi", "msa", "en"]
REGISTERS: Final[tuple[Register, ...]] = get_args(Register)
HOME: Final[Code] = "RUH"


@dataclass(frozen=True)
class Airport:
    """One airport: its code, its city's and its own names in English and Arabic, its offset
    from UTC, and the other names a caller may give it (`aliases`, besides the city's own)."""

    code: Code
    city_en: str
    city_ar: str
    name_en: str
    name_ar: str
    utc_offset: timedelta
    aliases: tuple[str, ...]

    def city(self, register: Register) -> str:
        """The city's name alone, in the register's script."""
        return self.city_en if register == "en" else self.city_ar

    def to_city(self, register: Register) -> str:
        """ "To" the city: «للندن» in Saudi (a name with «ال» takes «لل»: «للرياض»), «إلى لندن»
        in MSA, "to London" in English."""
        if register == "en":
            return f"to {self.city_en}"
        if register == "msa":
            return f"إلى {self.city_ar}"
        bare = self.city_ar.removeprefix("ال")
        return f"لل{bare}" if bare != self.city_ar else f"ل{self.city_ar}"

    def from_city(self, register: Register) -> str:
        """ "From" the city: «من لندن» in both Arabic registers, "from London" in English."""
        return f"from {self.city_en}" if register == "en" else f"من {self.city_ar}"


def _hours(hours: float) -> timedelta:
    return timedelta(minutes=round(hours * 60))


AIRPORTS: Final[dict[Code, Airport]] = {
    a.code: a
    for a in (
        Airport(
            "RUH",
            "Riyadh",
            "الرياض",
            "King Khalid International",
            "مطار الملك خالد الدولي",
            _hours(3),
            ("رياض", "Riyad"),
        ),
        Airport(
            "JED",
            "Jeddah",
            "جدة",
            "King Abdulaziz International",
            "مطار الملك عبدالعزيز الدولي",
            _hours(3),
            ("جده", "Jedda", "Jidda"),
        ),
        Airport(
            "DXB", "Dubai", "دبي", "Dubai International", "مطار دبي الدولي", _hours(4), ("ديبي",)
        ),
        Airport(
            "DOH",
            "Doha",
            "الدوحة",
            "Hamad International",
            "مطار حمد الدولي",
            _hours(3),
            ("الدوحه", "قطر", "Qatar"),
        ),
        Airport(
            "CAI",
            "Cairo",
            "القاهرة",
            "Cairo International",
            "مطار القاهرة الدولي",
            _hours(2),
            ("القاهره", "مصر", "Egypt"),
        ),
        Airport(
            "IST",
            "Istanbul",
            "إسطنبول",
            "Istanbul Airport",
            "مطار إسطنبول",
            _hours(3),
            ("اسطنبول", "تركيا", "Turkey", "Turkiye"),
        ),
        Airport(
            "LHR", "London", "لندن", "Heathrow", "مطار هيثرو", _hours(0), ("هيثرو", "Heathrow")
        ),
        Airport(
            "CDG",
            "Paris",
            "باريس",
            "Charles de Gaulle",
            "مطار شارل ديغول",
            _hours(1),
            ("فرنسا", "France"),
        ),
        Airport(
            "BOM",
            "Mumbai",
            "مومباي",
            "Mumbai International",
            "مطار مومباي الدولي",
            _hours(5.5),
            ("بومباي", "الهند", "Bombay", "India"),
        ),
        Airport(
            "SIN",
            "Singapore",
            "سنغافورة",
            "Changi",
            "مطار شانغي",
            _hours(8),
            ("سنغافوره", "سنقافورة"),
        ),
    )
}

# Words a caller or the talker may put around a city's name, dropped before the match: "to" and
# "from" in both scripts, and "airport" and "international" (or their Arabic) as an airport's
# name holds them.
_AROUND: Final = frozenset(
    normalize_arabic(w)
    for w in ("to", "from", "airport", "international", "إلى", "الى", "من", "مطار", "الدولي")
)


def _names() -> dict[str, Code]:
    """Every name of every airport, normalized, to its code: the city's in both scripts, the
    airport's own and the aliases, each with the words around a name dropped."""
    names: dict[str, Code] = {}
    for airport in AIRPORTS.values():
        given = (airport.city_en, airport.city_ar, airport.name_en, airport.name_ar)
        for name in (*given, *airport.aliases):
            names[_core(normalize_arabic(name))] = airport.code
    return names


def _core(normalized: str) -> str:
    return " ".join(w for w in normalized.split() if w not in _AROUND)


NAMES: Final[dict[str, Code]] = _names()


def find_airport(said: str) -> Airport | None:
    """The airport `said` names (a city, a country with one airport here, an airport's name, in
    either script, with "to" or "from" around it), or `None` when it names none. A Saudi «ل» or
    «لل» on the name («للرياض», «لدبي») is read off when the whole word names none."""
    core = _core(normalize_arabic(said))
    for candidate in (core, *_without_lam(core)):
        if candidate in NAMES:
            return AIRPORTS[NAMES[candidate]]
    return None


def _without_lam(core: str) -> tuple[str, ...]:
    """`core` with a Saudi «لل» read as «ال», or a «ل» dropped, when it is one word."""
    if " " in core or len(core) < 3:
        return ()
    if core.startswith("لل"):
        return ("ال" + core[2:], core[1:])
    if core.startswith("ل"):
        return (core[1:],)
    return ()


def airport(code: Code) -> Airport:
    """The airport of `code`."""
    return AIRPORTS[code]


def served_cities(register: Register) -> str:
    """The ten cities, Riyadh first, joined for speech in the register's script."""
    cities = [AIRPORTS[c].city(register) for c in CODES]
    if register == "en":
        return ", ".join(cities[:-1]) + " and " + cities[-1]
    return "، ".join(cities[:-1]) + " و" + cities[-1]
