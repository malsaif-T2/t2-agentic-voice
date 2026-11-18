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
  carriers (Qatar Airways then British Airways) gets no airline: "on Qatar Airways and British
  Airways" is not understood (Google's home page opens), and the first alone may filter out
  the very itinerary the caller picked.
- A party of two or more adds "for N adults", which Google reads (the page priced flynas for
  two at 858, twice 429); the cabin is left out, since neither "in business" nor "Business
  class flights" is understood, so the page opens in economy and the caller picks the cabin
  there. A flight number is not understood either. The agent says the price is confirmed on
  the airline's site.
- `hl=en`, `curr=SAR` and `gl=sa`. The `q` text is English, and `hl=ar` with it is not
  understood (checked 2026-11-18), so an Arabic call's link opens the English page too.

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
    to, origin = _place(end, offer.destination), _place(start, offer.origin)
    text = f"Flights to {to} from {origin} on {offer.day.isoformat()} one way"
    if len(offer.carriers) == 1:
        text += f" on {offer.carrier.name_en}"
    return text + (f" for {offer.adults} adults" if offer.adults > 1 else "")


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
    url = f"{GOOGLE_FLIGHTS}?q={quote(search_text(offer, route), safe='')}&hl=en&curr=SAR&gl=sa"
    return CardLink(label=link_label(offer, tag, leg), url=url)
