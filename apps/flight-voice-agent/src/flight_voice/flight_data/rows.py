"""The rows the place directory is written in (places_saudi.py, places_world.py): a city with
its country, the other names a caller may give it, and its airports, each with its own names.
places.py turns them into `Place`s."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["AirportRow", "CityRow", "city", "port"]


@dataclass(frozen=True)
class AirportRow:
    """One airport: its code, its own name in English and Arabic, and the other names a caller
    gives that airport alone ("Gatwick")."""

    code: str
    name_en: str
    name_ar: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class CityRow:
    """A city (or a country with one main airport): its names, its ISO country code, its
    airports with the main one first, and the other names a caller gives the whole city."""

    city_en: str
    city_ar: str
    country: str
    airports: tuple[AirportRow, ...]
    aliases: tuple[str, ...] = ()


def port(code: str, name_en: str, name_ar: str, *aliases: str) -> AirportRow:
    """An airport row."""
    return AirportRow(code, name_en, name_ar, aliases)


def city(
    en: str, ar: str, country: str, *airports: AirportRow, aliases: tuple[str, ...] = ()
) -> CityRow:
    """A city row, its main airport first."""
    return CityRow(en, ar, country, airports, aliases)
