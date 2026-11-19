"""The booking link of one leg (`leg_link`, plan 011; D-126): a Google Flights search for that
leg, one way, on its day, from its first airport to its last, filtered to its marketing
carriers, in the call's cabin and for its travelers, from which the caller books on the
airline's site. No airline documents a link that opens its booking prefilled, and none takes a
flight number (plan 011's research), so the page lists that day's flights of the leg's
airline(s), the one the caller chose among them.

The link is Google Flights' `tfs=` form, checked in a browser on 2026-11-19 (round 2): the
readable `q=` text lost the destination for some airports (Qassim to Al Bahah opened with
none) and could carry no cabin. `GOOGLE_FLIGHTS` takes `tfs` (`search_message`, base64url with
no padding), `hl` (`ar` for an Arabic reply, else `en`), `curr=SAR` and `gl=sa`. The message is
protobuf's wire format, written here by hand (varints and length-delimited fields; no
dependency), its fields in the order the checked links use:

- field 3, one leg: { 2: the day "YYYY-MM-DD"; 6: each marketing carrier's code, in the order
  of the segments, once each; 13: { 2: the first segment's origin airport }; 14: { 2: the last
  segment's destination airport } }: the exact airports the offer flew, never a city;
- field 8: a `1` for each adult;
- field 9: the cabin (economy 1, premium economy 2, business 3, first 4);
- field 19: the trip, one way (2), since each leg is its own one-way search (D-127).

The label says where the link goes: "Book on flynas", «احجز على طيران ناس», or for a round trip's
leg "Book the way out on Saudia", «احجز الذهاب على السعودية». A label holds no digit and at most
40 characters (the library's `CardLink`): a name too long or with a digit falls back to a
shorter label without it.
"""

from __future__ import annotations

import base64
from typing import Final, Literal

from t2_agentic_voice import CardLink

from flight_voice.flight_data.model import Cabin, Offer
from flight_voice.said import Tag, arabic

__all__ = ["GOOGLE_FLIGHTS", "leg_link", "link_label", "search_message", "tfs"]

GOOGLE_FLIGHTS: Final = "https://www.google.com/travel/flights/search"
MAX_LABEL: Final = 40
LinkLeg = Literal["outbound", "return"]
# Google Flights' numbers for a cabin and a one-way trip (checked 2026-11-19).
CABINS: Final[dict[Cabin, int]] = {"economy": 1, "business": 3, "first": 4}
ONE_WAY: Final = 2
# The message's fields (the module's docstring).
_LEG, _ADULT, _CABIN, _TRIP = 3, 8, 9, 19
_DAY, _AIRLINE, _FROM, _TO, _AIRPORT = 2, 6, 13, 14, 2
_VARINT, _LENGTH = 0, 2
# The labels, by language: on a carrier, then with no carrier (a name too long or with a digit).
_ON: Final[dict[str, dict[LinkLeg | None, str]]] = {
    "en": {
        None: "Book on {name}",
        "outbound": "Book the way out on {name}",
        "return": "Book the way back on {name}",
    },
    "ar": {
        None: "احجز على {name}",
        "outbound": "احجز الذهاب على {name}",
        "return": "احجز العودة على {name}",
    },
}
_BARE: Final[dict[str, dict[LinkLeg | None, str]]] = {
    "en": {None: "Book this flight", "outbound": "Book the way out", "return": "Book the way back"},
    "ar": {None: "احجز الرحلة", "outbound": "احجز الذهاب", "return": "احجز العودة"},
}


def _varint(value: int) -> bytes:
    """`value` (not negative) as a protobuf varint: seven bits a byte, the lowest first."""
    out = bytearray()
    while True:
        low, value = value & 0x7F, value >> 7
        if not value:
            out.append(low)
            return bytes(out)
        out.append(low | 0x80)


def _number(field: int, value: int) -> bytes:
    return _varint(field << 3 | _VARINT) + _varint(value)


def _field(field: int, value: bytes | str) -> bytes:
    held = value.encode() if isinstance(value, str) else value
    return _varint(field << 3 | _LENGTH) + _varint(len(held)) + held


def search_message(offer: Offer) -> bytes:
    """The leg's search as the protobuf message `tfs` carries (the module's docstring)."""
    leg = b"".join(
        (
            _field(_DAY, offer.day.isoformat()),
            *(_field(_AIRLINE, c.code) for c in offer.carriers),
            _field(_FROM, _field(_AIRPORT, offer.origin)),
            _field(_TO, _field(_AIRPORT, offer.destination)),
        )
    )
    adults = _number(_ADULT, 1) * offer.adults
    return (
        _field(_LEG, leg) + adults + _number(_CABIN, CABINS[offer.cabin]) + _number(_TRIP, ONE_WAY)
    )


def tfs(offer: Offer) -> str:
    """The leg's `tfs` value: its message in base64url, with no padding."""
    return base64.urlsafe_b64encode(search_message(offer)).rstrip(b"=").decode("ascii")


def link_label(offer: Offer, tag: Tag, leg: LinkLeg | None = None) -> str:
    """The link's label (the module's docstring): the leg's first carrier named in the reply's
    language, or none when its name would not fit or holds a digit."""
    lang = "ar" if arabic(tag) else "en"
    said = _ON[lang][leg].format(name=offer.carrier.name("msa" if lang == "ar" else "en"))
    if len(said) <= MAX_LABEL and not any(c.isdigit() for c in said):
        return said
    return _BARE[lang][leg]


def leg_link(
    offer: Offer, tag: Tag, leg: LinkLeg | None = None, *, label: str | None = None
) -> CardLink:
    """The booking link of `offer`'s leg (the module's docstring), labelled for `leg` of a round
    trip when given, or `label` when given; the page in Arabic for an Arabic reply."""
    hl = "ar" if arabic(tag) else "en"
    url = f"{GOOGLE_FLIGHTS}?tfs={tfs(offer)}&hl={hl}&curr=SAR&gl=sa"
    return CardLink(label=link_label(offer, tag, leg) if label is None else label, url=url)
