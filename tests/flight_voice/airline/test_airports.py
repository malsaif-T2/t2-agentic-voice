"""The mock airline's airports: every name a caller may give matches its own code and no other,
every spoken form in each register, and a city the airline does not serve matches nothing."""

from __future__ import annotations

from datetime import timedelta

import pytest
from flight_voice.airline.airports import (
    AIRPORTS,
    CODES,
    HOME,
    NAMES,
    Code,
    airport,
    find_airport,
    served_cities,
)
from t2_agentic_voice.languages import normalize_arabic

# The spoken forms of each city: alone in Arabic, "to" in Saudi and MSA, "from" in Arabic.
FORMS = {
    "RUH": ("الرياض", "للرياض", "إلى الرياض", "من الرياض"),
    "JED": ("جدة", "لجدة", "إلى جدة", "من جدة"),
    "DXB": ("دبي", "لدبي", "إلى دبي", "من دبي"),
    "DOH": ("الدوحة", "للدوحة", "إلى الدوحة", "من الدوحة"),
    "CAI": ("القاهرة", "للقاهرة", "إلى القاهرة", "من القاهرة"),
    "IST": ("إسطنبول", "لإسطنبول", "إلى إسطنبول", "من إسطنبول"),
    "LHR": ("لندن", "للندن", "إلى لندن", "من لندن"),
    "CDG": ("باريس", "لباريس", "إلى باريس", "من باريس"),
    "BOM": ("مومباي", "لمومباي", "إلى مومباي", "من مومباي"),
    "SIN": ("سنغافورة", "لسنغافورة", "إلى سنغافورة", "من سنغافورة"),
}
# The fixed offsets from UTC the lead ruled (no zone database), in hours.
OFFSETS: dict[Code, float] = {
    "RUH": 3,
    "JED": 3,
    "DXB": 4,
    "DOH": 3,
    "CAI": 2,
    "IST": 3,
    "LHR": 0,
    "CDG": 1,
    "BOM": 5.5,
    "SIN": 8,
}


def test_there_are_ten_airports_riyadh_the_home() -> None:
    assert list(AIRPORTS) == list(CODES) and len(CODES) == 10
    assert HOME == "RUH" and CODES[0] == HOME


@pytest.mark.parametrize("code", CODES)
def test_every_name_of_an_airport_finds_it(code: Code) -> None:
    place = AIRPORTS[code]
    names = (place.city_en, place.city_ar, place.name_en, place.name_ar, *place.aliases, code)
    for name in names:
        for said in (name, name.upper(), f"  {name}. ", f"to {name}", f"إلى {name}"):
            found = find_airport(said)
            assert found is not None and found.code == code, said


def test_no_name_belongs_to_two_airports() -> None:
    """Each normalized name is one airport's, so a match is never a pick between two."""
    seen: dict[str, str] = {}
    for place in AIRPORTS.values():
        given = (place.city_en, place.city_ar, place.name_en, place.name_ar, *place.aliases)
        for name in {normalize_arabic(n) for n in (*given, place.code)}:
            assert seen.setdefault(name, place.code) == place.code, name
    assert set(NAMES.values()) == set(CODES)


@pytest.mark.parametrize("code", CODES)
def test_every_spoken_form(code: Code) -> None:
    place = airport(code)
    alone, to_saudi, to_msa, from_ar = FORMS[code]
    assert place.city("saudi") == place.city("msa") == alone
    assert place.to_city("saudi") == to_saudi
    assert place.to_city("msa") == to_msa
    assert place.from_city("saudi") == place.from_city("msa") == from_ar
    assert place.city("en") == place.city_en
    assert place.to_city("en") == f"to {place.city_en}"
    assert place.from_city("en") == f"from {place.city_en}"


@pytest.mark.parametrize("code", CODES)
def test_the_saudi_to_form_and_the_from_form_find_their_airport(code: Code) -> None:
    place = airport(code)
    for said in (place.to_city("saudi"), place.to_city("msa"), place.from_city("saudi")):
        found = find_airport(said)
        assert found is not None and found.code == code, said


def test_each_airport_keeps_its_fixed_offset() -> None:
    for code, hours in OFFSETS.items():
        assert airport(code).utc_offset == timedelta(hours=hours)


def test_a_country_with_one_airport_here_names_it() -> None:
    found = [find_airport(s) for s in ("مصر", "Egypt", "قطر", "تركيا", "India")]
    assert [f.code if f else None for f in found] == ["CAI", "CAI", "DOH", "IST", "BOM"]


@pytest.mark.parametrize(
    "said",
    ["Manchester", "أبها", "Abha", "", "   ", "London Paris", "ل", "لل", "New York", "لابها"],
)
def test_a_city_not_served_matches_nothing(said: str) -> None:
    assert find_airport(said) is None


def test_the_served_cities_are_said_whole_in_each_script() -> None:
    english = served_cities("en")
    assert english.startswith("Riyadh, Jeddah") and english.endswith(", Mumbai and Singapore")
    arabic = served_cities("saudi")
    assert arabic.startswith("الرياض، جدة") and arabic.endswith("مومباي وسنغافورة")
    assert served_cities("msa") == arabic
