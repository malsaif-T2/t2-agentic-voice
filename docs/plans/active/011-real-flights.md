# 011 · Real flights of the Saudi airlines, and a link to book them

Status: active · Milestone: M10 · Started: 2026-11-18

*Drafted on 2026-11-18, after the owner's demo, from the goal their manager set that day; built
from a research round of four topics, each checked again by a skeptic against its sources (the
report: the lead's notes, `real_flights/research_report.md`), and a map of the flight app's seam
with the mock airline. Approved by the owner on 2026-11-18 with their answers below ("The owner's
decisions").*

## Goal

The flight agent (the lean Saad, D-113) answers an employee's questions about **real flights of
the Saudi airlines**, Saudia (SV), flynas (XY), flyadeal (F3) and Riyadh Air (RX), with their real
flight numbers, times, stops and prices, from a flight-data provider, in place of the mock T2 Air.
It is an internal tool of the company: it searches and informs, and in place of booking it gives a
**link to book the chosen flight on the airline's site** (booking through the agent is a later
phase). The voice and the conversation keep improving alongside.

## Acceptance criteria

- [ ] A call asks for flights on a Saudi route and a day, and Saad answers from the provider's
  live answer: each flight's airline, number, times, stops and price in SAR; a round trip leg by
  leg; a span of days for the cheapest day (capped, owner's call).
- [ ] Saad never says a flight, time or price the provider did not give in that call (the guard's
  rule B, over the provider's answers), says a price as the provider's of now, confirmed on the
  airline's site, and never says a trip is booked.
- [ ] Once the caller picks a trip, Saad gives the booking link (how it reaches the caller is the
  owner's call) and says the flight number to pick there.
- [ ] A provider that fails or is slow is said plainly ("I could not check just now"), never "no
  flights"; a search answers within the voice budget measured in Phase 0 (p95 named there).
- [ ] Every test stays offline: a recorded provider replays saved answers; a live smoke run is
  opt-in, behind the key, and refuses the main checkout as the other runs do.
- [ ] `uv run poe check` passes, and the docs this plan touched are updated.

## Plan

**Phase 0 · A spike, no app change (about a day, needs the provider key).**
SerpApi's Google Flights engine (`gl=sa`, `hl=en|ar`, `currency=SAR`) on RUH–JED, RUH–DMM,
JED–DXB, RUH–LHR and one RX codeshare route: does each carrier appear with its flight numbers, do
the booking options name the airline's own (`airline: true`), and how long does a search take
(Best Effort and Ludicrous)? The answers are saved as the recorded provider's fixtures. The
Google Flights search link (`tfs=`, filtered to the carrier) and the exact-itinerary
`booking?tfs=` link are tried by hand; the airlines' own search URLs, as a person captures them in
a browser, are checked for a prefilled search (none is documented; none takes a flight number).

**Phase 1 · The port and the mock behind it (offline; run F stays green).**
A `FlightData` port in the app (`flight_voice/flight_data/`: the model of an offer, its segments,
its money in SAR, places and carriers; the port; the mock adapter over today's `airline/`; a
recorded adapter that replays and records). The trip keeps the offer it was shown (in place of a
flight number re-derived from the mock's schedule), and every direct call of the lean tools into
the mock's schedule goes through the port. Flight ids become the carrier's (`SV1020-2026-11-19`).
Run F reads its facts from what the adapter answered, not from the mock recomputed.

**Phase 2 · The real adapter.**
`SerpApiFlightData` on an async HTTP client, with a timeout and one retry, the outbound and the
return searched at once, a short cache of answers (never of failures), the Saudi airports and
cities with their time zones, the four carriers' names in English and Arabic, and stops and
connections said. Settings: `FLIGHT_VOICE_FLIGHT_DATA = mock | recorded | serpapi`, the key as a
secret in `.env`, the timeout and the cache's life. A span of days fans out under a cap.

**Phase 3 · A link in place of booking, and the persona.**
A `booking_link` tool in place of `book_trip`: read-only, over the call's chosen trip; the
booking check, the send words and the bookings page go. The instructions lose "one airline", "every
flight starts or ends in Riyadh" and the booking section. The persona becomes the company's
travel assistant (its name and greeting, the owner's call). A booking claim is never allowed.

**Phase 4 · Evals and a live check.**
Run F's scenarios over the recorded answers (several carriers, a connection, a price that changed,
a provider that fails, an RX codeshare); the booking-only scenarios become "link given for the
trip agreed". The owner's live call ends the plan.

Each phase is a block, built in its own worktree, reviewed by an agent that did not write it,
fixed, gated and merged; at most two builders at once.

## The owner's decisions

- 2026-11-18, the goal (their manager's): "use real data for real flights, availability and
  prices for different Saudi Airlines … an internal agent for our company to search flights and
  provide information … lets keep the reservation as providing a link to book the flight".
- 2026-11-18, the source: "Did you consider "Almosafer". If it is not good lets proceed with
  SerpApi. I will see what I can do about a proper provider later." Almosafer has no public API
  (its corporate arm, Almosafer Business, integrates partners by agreement; its affiliate deep
  links run through an affiliate network, listed as paused), so SerpApi it is, behind a port a
  proper provider can take later.
- 2026-11-18, the link: a button on the call page's card ("Button on the card"), so Saad says the
  link is ready and never reads it out; cards carry a link (a library change, out of the guard's
  spoken text).
- 2026-11-18, the scope: Saudi domestic and international routes, connecting flights too, and
  other airlines on Saudi routes, not only the four.

## The proposal as approved

**The data.** No airline offers a public API, and every GDS or NDC route (Amadeus Enterprise, the
only one with all four carriers; Sabre and Travelport miss the low-cost ones; Travelfusion) needs a
contract or an agency, which takes months. Amadeus' self-service APIs closed on 2026-07-17;
Skyscanner, Kiwi and Travelpayouts admit only partners with large traffic; Duffel carries Saudia
alone. So the first source is **SerpApi's Google Flights API**: self-serve, all four carriers on
Google Flights (Riyadh Air seen there; the API call itself untested until Phase 0), per-flight
numbers and prices, free for 250 searches a month, $75 for 5,000. It is a scrape of Google:
Google's suit against SerpApi was dismissed twice (2026-07-20 and 2026-11-09, by SerpApi's
account), with leave to refile, so the company should be content with that for an internal tool.
SearchApi.io's same engine is the spare, behind the same port. The contract-grade route (Amadeus
through the company's travel agency) can start in parallel and would later allow booking.

**The link.** No airline documents a link that opens its booking flow prefilled, and none takes a
flight number. So the link is a **Google Flights search for the trip, filtered to its airline**
(route, dates, passengers, cabin), from which the caller books on the airline's site, and Saad says
the flight number to pick; an airline's own prefilled search replaces it where Phase 0 finds one.

## Open questions (each asked when the work needs it)

1. *Answered 2026-11-18:* the source (SerpApi), the link (a button on the card) and the scope (all
   routes, connections, every airline); see "The owner's decisions". The owner creates the
   SerpApi account and puts its key in `.env` as `FLIGHT_VOICE_SERPAPI_KEY`.
4. *Phase 2:* a cap on a span of days searched live (about 14 days)?
5. *Phase 3:* the persona's name and greeting; whether the traveler profile goes or becomes the
   employee's; whether the scripted agent retires or stays on the mock.
6. *Later:* does the company have a travel agency on Amadeus, or a Saudia business account?

## Progress log

- 2026-11-18: the goal set; the research round (aggregators, the Saudi airlines, booking links,
  schedule data) done and checked; the seam mapped; this proposal written; approved the same day
  with the owner's answers. Next: Phase 1 (offline, no key needed) on its own branch from
  plan-010-integration; Phase 0 once the SerpApi key is in `.env`.
- 2026-11-18, block C1 (after Phase 0): a span is one SerpApi fare-calendar search (a price a
  day, no flight count, so the count is left out; day by day only when the calendar prices
  none, as RUH-LHR's and RUH-DXB's did); deadlines 8 s from Phase 0's 1.1-4.1 s (one recording
  search took 6.8 s and two timed out on a cold start, then answered from SerpApi's cache);
  Phase 0's answers as parser fixtures; the app's recorded set (13 answers, 15 searches) in
  `apps/flight-voice-agent/evals/flight_data/`; the real network's persona, Saad, the T2 flight
  assistant (the owner's); an airline the caller names after a listing that left flights out
  comes from find_flights with airline.

## Decision log

- 2026-11-18 (C1): a day the fare calendar does not price is no flight inside the run of days
  it priced and unknown outside it, never no flights; a calendar that failed is said as failed,
  not read day by day (that would double the wait). The calendar's price for a party is taken
  as the party's, as a day's is (not checked live).
- 2026-11-18: SerpApi's Google Flights API first, SearchApi.io the spare, behind one port; the
  alternatives (Duffel, Amadeus, Sabre, Travelport, Kiwi, Skyscanner, Travelpayouts, Wego, schedule
  APIs) are closed to us, miss carriers, or give no prices (the research report); Almosafer has no
  public API. Approved by the owner.
