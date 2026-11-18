"""The airlines the real network names (flight_data/carriers.py): a flight number's prefix gives
the directory's carrier, or the provider's name for one it lacks; `named` is the airline filter,
the generic words dropped, an exact match first and every candidate of an ambiguous one; and
`pronounced` says the four Saudi codes alone."""

from __future__ import annotations

import pytest
from flight_voice.flight_data.carriers import CARRIERS, by_name, carrier, named, pronounced


def _codes(said: str) -> list[str]:
    return [c.code for c in named(said)]


@pytest.mark.parametrize(
    ("number", "code", "name"),
    [("SV 1020", "SV", "Saudia"), ("6E 123", "6E", "IndiGo"), ("F3 111", "F3", "flyadeal")],
)
def test_a_flight_numbers_prefix_gives_the_directorys_carrier(
    number: str, code: str, name: str
) -> None:
    prefix = number.split()[0]
    found = carrier(prefix, "whatever the provider says")
    assert (found.code, found.name_en) == (code, name)
    assert found is CARRIERS[code]


def test_a_carrier_the_directory_lacks_is_named_as_the_provider_names_it() -> None:
    found = carrier("ZZ", "Zed Air")
    assert (found.code, found.name_en, found.name_ar) == ("ZZ", "Zed Air", "Zed Air")
    assert carrier("ZZ", None).name_en == "ZZ"
    assert carrier("ZZ", "  ").name_ar == "ZZ"


def test_every_carrier_has_both_names_and_a_unique_code() -> None:
    assert len(CARRIERS) >= 45
    assert list(CARRIERS)[:4] == ["SV", "XY", "F3", "RX"]
    for code, c in CARRIERS.items():
        assert c.code == code and c.name_en and c.name_ar


@pytest.mark.parametrize("said", ["طيران ناس", "ناس", "fly nas", "XY", "xy", "Flynas", "فلاي ناس"])
def test_flynas_is_named_in_either_script_and_by_its_code(said: str) -> None:
    assert _codes(said) == ["XY"]


@pytest.mark.parametrize(
    ("said", "code"),
    [
        ("Saudia", "SV"),
        ("السعودية", "SV"),
        ("الخطوط السعودية", "SV"),
        ("Saudi Airlines", "SV"),
        ("أديل", "F3"),
        ("flyadil", "F3"),
        ("Riyadh Air", "RX"),
        ("طيران الرياض", "RX"),
        ("Emirates", "EK"),
        ("القطرية", "QR"),
        ("Air India", "AI"),
        ("Air India Express", "IX"),
        ("6E", "6E"),
    ],
)
def test_an_exact_name_or_code_wins(said: str, code: str) -> None:
    assert _codes(said) == [code]


@pytest.mark.parametrize("said", ["طيران", "air", "Airlines", "الخطوط", "fly", ""])
def test_generic_words_alone_name_no_airline(said: str) -> None:
    assert named(said) == ()


def test_an_ambiguous_word_gives_every_candidate() -> None:
    assert _codes("Royal") == ["RJ", "KL", "AT"]


def test_a_word_of_fewer_than_three_letters_matches_no_name() -> None:
    assert named("ab") == ()


def test_by_name_reads_the_operator_as_the_provider_writes_it() -> None:
    assert by_name("Saudia") is CARRIERS["SV"]
    assert by_name("flynas") is CARRIERS["XY"]
    assert by_name("Saudia as Saudia Regional") is CARRIERS["SV"]
    assert by_name("Horizon Air as Alaska Horizon") is None


def test_pronounced_says_the_four_saudi_codes_alone() -> None:
    said = pronounced()
    assert set(said) == {"SV", "XY", "F3", "RX"}
    assert said["SV"] == {"en": "ess vee", "ar": "إس في"}
    said["SV"]["en"] = "changed"
    assert pronounced()["SV"]["en"] == "ess vee"
