# Flight-booking voice agent

The second app built on T2 Agentic Voice, and the main one shown (D-101): the booking line of a
mock airline, T2 Air, whose voice assistant is Saad. A caller plans a trip by voice in Saudi
Arabic, MSA or English, hears every option spoken, and books it only after the trip is read
back in full and they say a clear yes (invariant 1). It uses only the library's public API, as
a teammate's app would, and imports no other app.

Its build spec is [flight-voice-agent.md](../../docs/design/flight-voice-agent.md).

## What is here

| Folder | What it holds |
| --- | --- |
| `src/flight_voice/airline/` | The mock airline: its ten airports, with their names in both languages, the names a caller may give each and a fixed offset from UTC; its timetable (every route starts or ends in Riyadh, no Singapore flight on Tuesdays, first class only on the 787-9, no day sold after 2027-03-27, where the fixed offsets stop holding); its fares in Saudi riyals, one way and per person, seeded from SHA-256, and the seats left in each cabin; the dates a caller says, resolved against today in Riyadh (UTC+3 all year); the demo traveler, Khalid, and the counts of his past trips; the bookings store in memory, seeded with those trips, with its modes (answer, refuse, timeout, late); and the facade the tools call, whose reads can be set to fail or be slow. |
| `src/flight_voice/trip.py` | The trip each call is planning, kept in code: its route, dates, travelers and cabin, the options last listed for each leg and the flight chosen, so a pick such as "the second one" is read against what was said. |

Everything in the mock airline is fixed data or computed from fixed data, so the same inputs give
the same answer on every run and a call's facts are checked in code. Its tests are in
`tests/flight_voice/`:

```bash
uv run pytest tests/flight_voice
```

The server, its page and its scripted calls come with the next parts of the build; this file
says how to run each one as it lands.
