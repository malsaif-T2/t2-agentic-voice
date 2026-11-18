"""The booking link of one leg (`leg_link`, plan 011's Phase 3; D-126): a Google Flights search
for that leg, one way, on its day, filtered to its marketing carrier(s), from which the caller
books on the airline's site. No airline documents a link that opens its booking prefilled, and
none takes a flight number (plan 011's research), so the agent says the flight to pick there.

The link is Google Flights' readable `q=` form, checked in a browser on 2026-11-18 (Phase 0):
`GOOGLE_FLIGHTS` with `q` "Flights to JED from RUH on 2026-11-26 one way on flynas" (spaces as
`%20`) and `hl=en&curr=SAR&gl=sa` opened exactly flynas's five flights that day at the prices
SerpApi gave. So:

- `q` is "Flights to {to} from {from} on {YYYY-MM-DD} one way on {carrier}", URL-encoded. A place
  is its IATA code when it has one airport, else its city's English name ("London", searched
  over its airports as SerpApi was); with no route given, the offer's own airports.
- The carrier is the leg's marketing carrier's English name. A connection of two marketing
  carriers (Qatar Airways then British Airways) names both, "on Qatar Airways and British
  Airways": the first alone may filter out the very itinerary the caller picked. (Only the
  one-carrier form was checked in a browser; the two-carrier form is the lead's to check.)
- `hl` is the reply's language (`ar` for either Arabic, `en`), `curr=SAR` and `gl=sa`, as the
  searches are made. The `q` text stays English, the form checked.
- The party and the cabin are left out of `q`: a flight number in `q` was not understood, and
  nothing documents "for 2 adults" or "in business" there (an open issue for the lead), so the
  page opens for one adult in economy, and its price for a party or a cabin may differ from
  the one said. The agent says the price is confirmed on the airline's site.

The label says where the link goes: "Book on flynas", «احجز على طيران ناس», or for a round trip's
leg "Book the way out on Saudia", «احجز الذهاب على السعودية». A label holds no digit and at most
40 characters (the library's `CardLink`): a name too long or with a digit falls back to a
shorter label without it.
"""

from __future__ import annotations

from typing import Final, Literal
from urllib.parse import quote

from t2_agentic_voice import CardLink

from flight_voice.flight_data.model import Offer, Place
from flight_voice.said import Tag, arabic

__all__ = ["GOOGLE_FLIGHTS", "leg_link", "link_label", "search_text"]

GOOGLE_FLIGHTS: Final = "https://www.google.com/travel/flights"
MAX_LABEL: Final = 40
LinkLeg = Literal["outbound", "return"]
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


def _place(place: Place | None, airport: str) -> str:
    """A place as `q` names it: its code for one airport, else its city's English name."""
    if place is None or len(place.airports) == 1 or not place.known:
        return airport if place is None else place.code
    return place.city_en


def search_text(offer: Offer, route: tuple[Place, Place] | None = None) -> str:
    """The leg's search as `q` says it (the module's docstring)."""
    start, end = route if route is not None else (None, None)
    names = " and ".join(c.name_en for c in offer.carriers)
    to, origin = _place(end, offer.destination), _place(start, offer.origin)
    return f"Flights to {to} from {origin} on {offer.day.isoformat()} one way on {names}"


def link_label(offer: Offer, tag: Tag, leg: LinkLeg | None = None) -> str:
    """The link's label (the module's docstring): the leg's first carrier named in the reply's
    language, or none when its name would not fit or holds a digit."""
    lang = "ar" if arabic(tag) else "en"
    said = _ON[lang][leg].format(name=offer.carrier.name("msa" if lang == "ar" else "en"))
    if len(said) <= MAX_LABEL and not any(c.isdigit() for c in said):
        return said
    return _BARE[lang][leg]


def leg_link(
    offer: Offer, tag: Tag, route: tuple[Place, Place] | None = None, leg: LinkLeg | None = None
) -> CardLink:
    """The booking link of `offer`'s leg, from `route`'s start to its end when given (the
    module's docstring), labelled for `leg` of a round trip when given."""
    hl = "ar" if arabic(tag) else "en"
    url = f"{GOOGLE_FLIGHTS}?q={quote(search_text(offer, route), safe='')}&hl={hl}&curr=SAR&gl=sa"
    return CardLink(label=link_label(offer, tag, leg), url=url)
