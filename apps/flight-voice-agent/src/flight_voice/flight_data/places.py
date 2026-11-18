"""The places a caller of the real network may name (`Directory`, the `Places` port): Saudi
Arabia's airports and those abroad that Saudi routes reach (places_saudi.py, places_world.py),
for speech and matching, not a whitelist.

`find` reads what was said as `find_airport` does (airline/airports.py): `normalize_arabic`, the
words around a name dropped ("to", "from", "airport", «مطار» ...), and a Saudi «ل» or «لل» read
off a single word («لجدة», «للرياض»). A city's name, a country word or a city alias gives the
city with all its airports (London: LHR, LGW, STN); an airport's own name, alias or code gives
that airport alone ("Gatwick", "LGW"). A miss is a bare place only when what was said is
exactly three capital letters, which is how the model passes a code ("ZZZ"); any other miss is
None, so "Goa" never becomes Genoa's GOA and an Arabic word never reaches the code pattern.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Final

from t2_agentic_voice.languages import normalize_arabic

from flight_voice.flight_data.model import IATA, Place
from flight_voice.flight_data.places_saudi import SAUDI
from flight_voice.flight_data.places_world import WORLD
from flight_voice.flight_data.rows import CityRow

__all__ = ["DIRECTORY_ROWS", "HOME", "Directory"]

HOME: Final = "RUH"
DIRECTORY_ROWS: Final[tuple[CityRow, ...]] = (*SAUDI, *WORLD)
_CODE: Final = re.compile(r"[A-Z]{3}")
# The words around a name, dropped before the match, as find_airport drops them.
_AROUND: Final = frozenset(
    normalize_arabic(w)
    for w in ("to", "from", "airport", "international", "إلى", "الى", "من", "مطار", "الدولي")
)


def _core(said: str) -> str:
    return " ".join(w for w in normalize_arabic(said).split() if w not in _AROUND)


def _without_lam(core: str) -> tuple[str, ...]:
    """`core` with a Saudi «لل» read as «ال», or a «ل» dropped, when it is one word."""
    if " " in core or len(core) < 3:
        return ()
    if core.startswith("لل"):
        return ("ال" + core[2:], core[1:])
    if core.startswith("ل"):
        return (core[1:],)
    return ()


def _city_place(row: CityRow) -> Place:
    only = row.airports[0] if len(row.airports) == 1 else None
    return Place(
        code=row.airports[0].code,
        airports=tuple(a.code for a in row.airports),
        city_en=row.city_en,
        city_ar=row.city_ar,
        name_en=only.name_en if only else None,
        name_ar=only.name_ar if only else None,
        country=row.country,
        aliases=row.aliases,
    )


class Directory:
    """The real network's places (the module's docstring); `home` is Riyadh, `served` None.
    Built from `rows` (every Saudi and foreign row by default); ValueError when one name would
    give two cities."""

    def __init__(self, rows: Iterable[CityRow] = DIRECTORY_ROWS) -> None:
        self._names: dict[str, Place] = {}
        self._owners: dict[str, tuple[str, bool]] = {}  # a name's city and whether city-level
        self._airports: dict[str, Place] = {}
        for row in rows:
            self._add(row)
        if HOME not in self._airports:
            raise ValueError("the directory holds Riyadh, its home")

    def _add(self, row: CityRow) -> None:
        whole = _city_place(row)
        for airport in row.airports:
            alone = whole
            if len(row.airports) > 1:
                alone = whole.model_copy(
                    update={
                        "code": airport.code,
                        "airports": (airport.code,),
                        "name_en": airport.name_en,
                        "name_ar": airport.name_ar,
                        "aliases": airport.aliases,
                    }
                )
            if airport.code in self._airports:
                raise ValueError(f"the directory lists {airport.code} twice")
            self._airports[airport.code] = alone
            for name in (airport.name_en, airport.name_ar, *airport.aliases, airport.code):
                self._index(name, alone, row.city_en, city_level=False)
        for name in (row.city_en, row.city_ar, *row.aliases):
            self._index(name, whole, row.city_en, city_level=True)

    def _index(self, name: str, place: Place, city: str, *, city_level: bool) -> None:
        key = _core(name)
        if not key:
            return
        held = self._owners.get(key)
        if held is not None and held[0] != city:
            raise ValueError(f"the name {key!r} would give both {held[0]} and {city}")
        if held is not None and held[1] and not city_level:
            return  # a city's own name wins over an airport's that reads the same
        self._names[key] = place
        self._owners[key] = (city, city_level)

    @property
    def home(self) -> Place:
        """Riyadh."""
        return self._airports[HOME]

    @property
    def served(self) -> tuple[IATA, ...] | None:
        """None: the directory is no whitelist."""
        return None

    def find(self, said: str) -> Place | None:
        """The place `said` names (the module's docstring), a bare place for an unknown code,
        or None."""
        core = _core(said)
        for candidate in (core, *_without_lam(core)):
            found = self._names.get(candidate)
            if found is not None:
                return found
        code = said.strip()
        return Place.bare(code) if _CODE.fullmatch(code) else None

    def get(self, code: str) -> Place | None:
        """The airport of `code` alone, with its city's names, or None when the directory lacks
        it."""
        return self._airports.get(code)
