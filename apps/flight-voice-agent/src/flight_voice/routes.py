"""The page's own routes, beside the token route and the library's router (server.py):

- `GET /api/profile`: what the page shows, in both languages, with the line's `network`, whether
  it books (`bookings`) and whether the token route asks for a code (`access`: `code`, or `open`
  with no access code set, D-129). On the mock: the demo traveler's first name and tier, the
  persona's and the airline's names, and three lines the caller could say (the most visited
  city, a cheapest-days ask, a business ask). On real flights (plan 011) no traveler at all,
  since anyone at the company calls with no profile (the owner, 2026-11-18): the persona, the
  company, the assistant's role and three lines to say. Shown as text; no secret, for any
  client.
- `GET /api/bookings`: the traveler's bookings, newest first, for the page's "Your trips": each
  one's reference, route, dates, travelers, cabin and total. **On this machine only**: it shows
  the bookings calls made, so a client that is not a loopback address gets 404, as Ole5's ticket
  page does.
- `POST /api/demo/reset`: the bookings back to the seed (the past trips alone). On this machine
  only (404 else), with `Content-Type: application/json` (415 otherwise, before a byte is read,
  so a cross-site form cannot post it) and a body of an empty JSON object, at most
  `MAX_RESET_BYTES` (413 past it, 400 for any other body).

Each answer is JSON, never cached (`Cache-Control: no-store`). The traveler is always the demo
traveler: no request names one (invariant 3).
"""

from __future__ import annotations

import ipaddress
import json
from typing import Final

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from flight_voice.airline.airports import airport
from flight_voice.airline.bookings import Booking
from flight_voice.airline.profile import TRAVELER, insights
from flight_voice.airline.system import Airline
from flight_voice.persona import Names, Network

MAX_RESET_BYTES: Final = 64


NO_STORE: Final = {"Cache-Control": "no-store"}
# The cities of the cheapest-days line and the business line.
CHEAPEST_CITY: Final = "LHR"
BUSINESS_CITY: Final = "CDG"
# The most visited city's line when the traveler has flown nowhere.
FIRST_CITY: Final = "DXB"


def api_router(
    airline: Airline, names: Names, network: Network = "mock", *, open_access: bool = False
) -> APIRouter:
    """The page's routes over `airline`, the persona named by `names`, on `network`, the token
    route asking for no code when `open_access` (the module's docstring)."""
    access = {"access": "open" if open_access else "code"}
    router = APIRouter()

    @router.get("/api/profile")
    async def profile() -> JSONResponse:
        if network == "real":
            return JSONResponse(real_profile_view(names) | access, headers=NO_STORE)
        return JSONResponse(profile_view(airline, names) | access, headers=NO_STORE)

    @router.get("/api/bookings")
    async def bookings(request: Request) -> JSONResponse:
        if not on_this_machine(request):
            return _not_found()
        listed = airline.bookings.listed(TRAVELER.id)
        return JSONResponse({"bookings": [booking_view(b) for b in listed]}, headers=NO_STORE)

    @router.post("/api/demo/reset")
    async def reset(request: Request) -> JSONResponse:
        if not on_this_machine(request):
            return _not_found()
        kind = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if kind != "application/json":
            return _refused(415, "The request's body is sent as application/json.")
        body = await _read(request, MAX_RESET_BYTES)
        if body is None:
            return _refused(413, "The request's body is too large.")
        try:
            empty = json.loads(body) == {}
        except ValueError:
            empty = False
        if not empty:
            return _refused(400, "The request's body is an empty JSON object.")
        airline.bookings.reset()
        return JSONResponse({"reset": True}, headers=NO_STORE)

    return router


def real_profile_view(names: Names) -> dict[str, object]:
    """What `GET /api/profile` answers on real flights: no traveler (the module's docstring)."""
    return {
        "network": "real",
        "bookings": False,
        "persona": {"ar": names.persona_name_ar, "en": names.persona_name_en},
        "company": {"ar": names.airline_code_said_ar, "en": names.airline_code},
        "role": {"ar": "مساعد الرحلات", "en": "flight assistant"},
        "lines": {
            # min ar-riyaadh l-jidda ...: Riyadh to Jeddah next Thursday; arkhaS yoom ...: the
            # cheapest day to Dubai this month; weesh 'ind ...: what does flynas have to Dammam?
            "ar": [
                "من الرياض لجدة الخميس الجاي",
                "أرخص يوم لدبي هالشهر",
                "وش عند طيران ناس للدمام؟",
            ],
            "en": [
                "Riyadh to Jeddah next Thursday",
                "Cheapest day to Dubai this month",
                "What does flynas have to Dammam?",
            ],
        },
    }


def profile_view(airline: Airline, names: Names) -> dict[str, object]:
    """What `GET /api/profile` answers on the mock."""
    flown = [b for b in airline.bookings.listed(TRAVELER.id) if b.flown]
    most = insights(flown).most_visited or FIRST_CITY
    back, cheap, business = airport(most), airport(CHEAPEST_CITY), airport(BUSINESS_CITY)
    return {
        "network": "mock",
        "bookings": True,
        "first_name": {"ar": TRAVELER.first_ar, "en": TRAVELER.first_en},
        "tier": {"ar": TRAVELER.tier_ar, "en": TRAVELER.tier},
        "persona": {"ar": names.persona_name_ar, "en": names.persona_name_en},
        "airline": {"ar": names.airline_name_ar, "en": names.airline_name_en},
        "lines": {
            # widdi arja' ...: I'd like to go back to ...; arkhas al-ayyaam ...: the cheapest days
            # to ...; bizness ...: business to ...
            "ar": [
                f"ودي أرجع {back.to_city('saudi')}",
                f"أرخص الأيام {cheap.to_city('saudi')}",
                f"بزنس {business.to_city('saudi')}",
            ],
            "en": [
                f"Back {back.to_city('en')}",
                f"Cheapest days {cheap.to_city('en')}",
                f"Business {business.to_city('en')}",
            ],
        },
    }


def booking_view(booking: Booking) -> dict[str, object]:
    """One booking as `GET /api/bookings` answers it."""
    origin, destination = airport(booking.origin), airport(booking.destination)
    return {
        "reference": booking.reference,
        "from": {"ar": origin.city_ar, "en": origin.city_en},
        "to": {"ar": destination.city_ar, "en": destination.city_en},
        "depart": booking.depart.isoformat(),
        "return_date": None if booking.return_date is None else booking.return_date.isoformat(),
        "travelers": booking.travelers,
        "cabin": booking.cabin,
        "total_sar": booking.total_sar,
        "flown": booking.flown,
    }


def on_this_machine(request: Request) -> bool:
    """Whether the request's client is a loopback address, IPv4 written in IPv6 included."""
    host = request.client.host if request.client else ""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped.is_loopback
    return address.is_loopback


async def _read(request: Request, limit: int) -> bytes | None:
    """The body, or None once it passes `limit` bytes, by its length or as it streams."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        return None
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            return None
    return body


def _not_found() -> JSONResponse:
    return JSONResponse({"detail": "Not Found"}, status_code=404)


def _refused(status: int, message: str) -> JSONResponse:
    return JSONResponse({"detail": message}, status_code=status)
