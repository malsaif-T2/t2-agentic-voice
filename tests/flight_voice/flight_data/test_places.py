"""The real network's places (flight_data/places.py): Saudi names and aliases in both scripts,
the Najdi spellings and the Saudi «ل»; a city with several airports searched together and an
airport's own name alone; the country words; a code the directory lacks is a bare place only
when it is exactly three capital letters; and every name and alias of the mock's ten airports
gives the same code."""

from __future__ import annotations

import pytest
from flight_voice.airline.airports import NAMES
from flight_voice.flight_data.model import Place
from flight_voice.flight_data.places import Directory
from flight_voice.flight_data.rows import city, port

DIRECTORY = Directory()


def _found(said: str) -> Place:
    place = DIRECTORY.find(said)
    assert place is not None, said
    return place


@pytest.mark.parametrize(
    ("said", "code"),
    [
        ("Riyadh", "RUH"),
        ("الرياض", "RUH"),
        ("للرياض", "RUH"),
        ("Jeddah", "JED"),
        ("جدة", "JED"),
        ("لجدة", "JED"),
        ("to Jeddah", "JED"),
        ("مطار جدة", "JED"),
        ("Khobar", "DMM"),
        ("الظهران", "DMM"),
        ("Khamis Mushait", "AHB"),
        ("خميس مشيط", "AHB"),
        ("الطايف", "TIF"),
        ("الطائف", "TIF"),
        ("حايل", "HAS"),
        ("جيزان", "GIZ"),
        ("Jizan", "GIZ"),
        ("Buraidah", "ELQ"),
        ("القصيم", "ELQ"),
        ("الحسا", "HOF"),
        ("الأحساء", "HOF"),
        ("Medina", "MED"),
        ("AlUla", "ULH"),
        ("Sakaka", "AJF"),
    ],
)
def test_saudi_names_and_aliases_in_both_scripts(said: str, code: str) -> None:
    place = _found(said)
    assert (place.code, place.airports, place.country, place.known) == (code, (code,), "SA", True)


def test_a_city_of_several_airports_is_searched_together_and_an_airport_alone() -> None:
    london = _found("London")
    assert (london.code, london.airports) == ("LHR", ("LHR", "LGW", "STN"))
    assert london.name_en is None and london.city_ar == "لندن"
    assert _found("لندن") == london
    gatwick = _found("Gatwick")
    assert (gatwick.code, gatwick.airports, gatwick.city_en) == ("LGW", ("LGW",), "London")
    assert gatwick.name_en == "Gatwick"
    assert _found("LGW") == gatwick
    assert _found("Dubai").airports == ("DXB", "DWC")
    assert _found("Dubai International").airports == ("DXB", "DWC")  # the city's name wins
    assert _found("Paris").airports == ("CDG", "ORY")
    assert _found("Istanbul").airports == ("IST", "SAW")


@pytest.mark.parametrize(
    ("said", "code"),
    [
        ("Bahrain", "BAH"),
        ("البحرين", "BAH"),
        ("Kuwait", "KWI"),
        ("الكويت", "KWI"),
        ("Qatar", "DOH"),
        ("قطر", "DOH"),
    ],
)
def test_the_country_words_give_their_main_airport(said: str, code: str) -> None:
    assert _found(said).code == code


def test_goa_is_goa_never_genoa() -> None:
    assert _found("Goa").airports == ("GOI", "GOX")


def test_a_code_the_directory_lacks_is_bare_only_as_three_capitals() -> None:
    bare = _found("ZZZ")
    assert (bare.code, bare.known, bare.city_en) == ("ZZZ", False, "ZZZ")
    for said in ("zzz", "Ula", "علا", "Zzz", "ZZZZ", "Genoa", "nowhere at all"):
        assert DIRECTORY.find(said) is None, said


@pytest.mark.parametrize(("name", "code"), sorted(NAMES.items()))
def test_every_mock_name_and_alias_gives_the_same_code(name: str, code: str) -> None:
    assert _found(name).code == code


def test_get_reads_one_airport_and_home_is_riyadh() -> None:
    assert DIRECTORY.home.code == "RUH" and DIRECTORY.home.city_en == "Riyadh"
    assert DIRECTORY.served is None
    elq = DIRECTORY.get("ELQ")
    assert elq is not None and elq.city_en == "Qassim"
    stn = DIRECTORY.get("STN")
    assert stn is not None and stn.airports == ("STN",)
    assert DIRECTORY.get("ZZZ") is None


def test_a_name_that_would_give_two_cities_is_refused() -> None:
    rows = (
        city("Riyadh", "الرياض", "SA", port("RUH", "One", "واحد")),
        city("Elsewhere", "مكان", "SA", port("ZZA", "Two", "اثنان"), aliases=("Riyadh",)),
    )
    with pytest.raises(ValueError, match="both"):
        Directory(rows)
    with pytest.raises(ValueError, match="Riyadh"):
        Directory(rows[1:])
