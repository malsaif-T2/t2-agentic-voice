"""`uv run poe smoke-flights`: the opt-in live smoke run of the SerpApi adapter (plan 011,
Phase 2), never part of `check`. It spends: two to four searches of the key's quota.

It refuses the main checkout and a tree with changes, as every run does (the library's
`run_checkout`), and refuses to start without `FLIGHT_VOICE_SERPAPI_KEY` (from the environment,
or the `--env-file` given). Then it makes one RUH-JED day search a week from today and one span
of three days from then, and logs only the counts, the statuses and the wall seconds, never a
body or the key. Exit 0 when both answered, 1 when one could not, 2 when refused.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

import httpx
from t2_agentic_voice import T2VoiceError, configure_logging, get_logger
from t2_agentic_voice.evals import Git, run_checkout, run_git, run_refused

from flight_voice import LOGGERS
from flight_voice.airline.system import live_today
from flight_voice.flight_data.places import Directory
from flight_voice.flight_data.port import FlightDataUnavailableError
from flight_voice.flight_data.queries import OfferQuery, SpanQuery
from flight_voice.flight_data.serpapi import SerpApiFlightData
from flight_voice.settings import load_flight_data

log = get_logger(__name__)

SPAN_DAYS = 3
AHEAD_DAYS = 7


def parser() -> argparse.ArgumentParser:
    made = argparse.ArgumentParser(
        prog="poe smoke-flights",
        description="One live SerpApi day search and one span of three days (spends).",
    )
    made.add_argument("--env-file", type=Path, help="the .env the key loads from")
    return made


def _source(env_file: Path | None, transport: httpx.AsyncBaseTransport | None) -> SerpApiFlightData:
    fields = load_flight_data(env_file)
    key = fields.serpapi_key
    if key is None or not key.get_secret_value().strip():
        raise run_refused(
            "FLIGHT_VOICE_SERPAPI_KEY is not set", "put the SerpApi key in .env, then --env-file"
        )
    return SerpApiFlightData(
        key,
        deadline_s=fields.flight_data_deadline_s,
        span_days=fields.flight_data_span_days,
        span_concurrency=fields.flight_data_span_concurrency,
        span_deadline_s=fields.flight_data_span_deadline_s,
        deep_search=fields.serpapi_deep_search,
        transport=transport,
    )


async def _smoke(source: SerpApiFlightData) -> bool:
    places = Directory()
    start, end = places.get("RUH"), places.get("JED")
    if start is None or end is None:
        raise ValueError("the directory holds Riyadh and Jeddah")
    day = live_today() + timedelta(days=AHEAD_DAYS)
    answered = True
    try:
        began = time.perf_counter()
        try:
            found = await source.day(OfferQuery(origin=start, destination=end, day=day))
            log.info(
                "smoke_day",
                status=found.status,
                offers=len(found.offers),
                carriers=len({o.carrier.code for o in found.offers}),
                wall_s=round(time.perf_counter() - began, 2),
            )
        except FlightDataUnavailableError as error:
            log.warning("smoke_day_failed", failure=error.failure, status=error.status)
            answered = False
        began = time.perf_counter()
        last = day + timedelta(days=SPAN_DAYS - 1)
        try:
            fares = await source.days(
                SpanQuery(origin=start, destination=end, first=day, last=last)
            )
            log.info(
                "smoke_span",
                status=fares.status,
                days=len(fares.days),
                known=sum(1 for d in fares.days if d.known),
                wall_s=round(time.perf_counter() - began, 2),
            )
        except FlightDataUnavailableError as error:
            log.warning("smoke_span_failed", failure=error.failure, status=error.status)
            answered = False
    finally:
        await source.aclose()
    return answered


def main(
    argv: Sequence[str] | None = None,
    *,
    folder: Path | None = None,
    git: Git = run_git,
    transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    """`uv run poe smoke-flights` (the module's docstring): 0 answered, 1 not, 2 refused."""
    args = parser().parse_args(argv)
    configure_logging(loggers=LOGGERS)
    try:
        run_checkout(folder or Path.cwd(), git)
        source = _source(args.env_file, transport)
    except T2VoiceError as error:
        log.error("smoke_refused", code=error.code, message=error.message)
        return 2
    return 0 if asyncio.run(_smoke(source)) else 1


if __name__ == "__main__":
    sys.exit(main())
