"""The mock ticket system's page (plan 007): `GET /tickets` lists every ticket the mock holds,
newest first, each with its number, type, priority, status, summary and the time it was made,
so a demo can show what a call made. It is for the person running the demo and is never
spoken: the caller only hears the agent (D-075).

- **Read-only:** its router has this one GET route and no other, and the page holds no form,
  no script and no link but its style and an empty icon.
- **Every value escaped** (`html.escape`, quotes too), so a summary holding markup shows as
  text; a summary is set `dir="auto"`, so an Arabic one reads right to left.
- **Headers:** the widget's page headers (server.py's `page_headers`, given by the server, with
  no website allowed to frame it), its style from the widget's folder (`tickets.css`), no
  cache; it reloads itself every REFRESH_S seconds, so a ticket shows as a call makes it.
- **On this machine only:** it shows what callers said, so a client that is not a loopback
  address (the connection's peer, or the client a trusted proxy forwarded, as uvicorn sets it)
  gets 404.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping, Sequence
from html import escape
from typing import Final

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from ole5_voice.tickets.mock import MockTicket, MockTicketSystem

PAGE: Final = "/tickets"
STYLE: Final = "tickets.css"
REFRESH_S: Final = 5
COLUMNS: Final = ("Number", "Type", "Priority", "Status", "Summary", "Created")
_HEAD: Final = f"""<!doctype html>
<html lang="en" dir="ltr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="{REFRESH_S}">
<title>Ole5 mock tickets</title>
<link rel="icon" href="data:,">
<link rel="stylesheet" href="{STYLE}">
</head>
<body>
<header>
<h1>Mock tickets</h1>
<p class="muted">The tickets Ole5's calls made in the mock ticket system, newest first. This
page reloads every {REFRESH_S} seconds.</p>
</header>
<main>
"""
_FOOT: Final = "</main>\n</body>\n</html>\n"


def tickets_router(tickets: MockTicketSystem, *, headers: Mapping[str, str]) -> APIRouter:
    """The router with `GET /tickets`, the page of `tickets`, served with `headers`."""
    router = APIRouter()
    served = {**headers, "Cache-Control": "no-store"}

    async def page(request: Request) -> Response:
        if not _on_this_machine(request):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        return HTMLResponse(render(tickets.listed()), headers=served)

    router.add_api_route(PAGE, page, methods=["GET"], include_in_schema=False)
    return router


def render(tickets: Sequence[MockTicket]) -> str:
    """The page listing `tickets` (oldest first, as the mock keeps them), newest first."""
    if not tickets:
        return f'{_HEAD}<p class="empty">No tickets yet.</p>\n{_FOOT}'
    head = "".join(f'<th scope="col">{name}</th>' for name in COLUMNS)
    rows = "".join(_row(ticket) for ticket in reversed(tickets))
    table = f"<table>\n<thead><tr>{head}</tr></thead>\n<tbody>\n{rows}</tbody>\n</table>\n"
    return f"{_HEAD}{table}{_FOOT}"


def _row(ticket: MockTicket) -> str:
    """One ticket's row, each value escaped."""
    cells = (
        ('class="number" dir="ltr"', ticket.number),
        ("", ticket.type),
        ("", ticket.priority),
        ("", ticket.status),
        ('class="summary" dir="auto"', ticket.summary),
        ('dir="ltr"', f"{ticket.created_at:%Y-%m-%d %H:%M}"),
    )
    tds = "".join(f"<td{' ' if a else ''}{a}>{escape(text, quote=True)}</td>" for a, text in cells)
    return f"<tr>{tds}</tr>\n"


def _on_this_machine(request: Request) -> bool:
    """Whether the request's client is a loopback address, IPv4 written in IPv6 included."""
    host = request.client.host if request.client else ""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped.is_loopback
    return address.is_loopback
