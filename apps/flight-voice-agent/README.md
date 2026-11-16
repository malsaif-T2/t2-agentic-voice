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
| `src/flight_voice/said/` | The words the agent says with no number in them, in Saudi Arabic, MSA and English: weekdays, months, cabins, the parts of the day, routes ("Riyadh to London", «من الرياض للندن»), a trip's kind and the fare's basis ("per person, one way"); and, for the lines the app renders in code alone (the booking's read-back and its outcome), numbers, times, dates, amounts and the travelers in words by register («تسع وعشر دقايق الصبح», «التاسعة وعشر دقائق صباحًا», "nine ten in the morning"), until the library says these forms itself. |
| `src/flight_voice/tools/` | The read tools the talker calls: what each result holds (its status, its facts as values, its words in the reply's registers and a fixed `say` telling the talker what to say next), the card it shows on the page, `search_flights`, `choose_flight` (a pick as the caller said it, "the second one", "the morning one", read in code against the options listed), `change_trip` (travelers, cabin, one way, with the chosen legs priced again), `get_trip`, `fare_calendar` (the seven cheapest days of a month or of 30 days, three marked to be said), `compare_cabins` (each cabin's fare and seats on one listed flight) and `traveler_profile` (the caller's tier, trips and bookings with every count worked out, read for the verified caller alone); `flight_tools` gives all seven. Once every leg is chosen, the result sends the talker straight to the booking's read-back, so the caller hears the trip and its total once. A read of the airline that fails is said as a failure, never as nothing found. |
| `src/flight_voice/booking/` | The booking, `book_trip`, the one action: the talker calls it with no arguments, and its draft, hidden from the talker, is filled from the call's trip, priced again; the read-back says the trip whole in words, its kind ("round trip", "one way") first, then asks "Shall I book it?" / «تبيني أحجزها؟»; only a spoken yes with "book it" / «احجزها» (or the model's clear go-ahead) books it, for the verified traveler alone. `done` says the city and the day, never the reference; a refusal is said as failed; a write with no answer is looked up and said unknown when nothing finds it; one booking a call. |
| `src/flight_voice/trip.py` | The trip each call is planning, kept in code: its route, dates, travelers and cabin, the options last listed for each leg and the flight chosen, so a pick such as "the second one" is read against what was said. |
| `src/flight_voice/agent.py`, `persona.py`, `instructions/` | The declaration the runtime runs: Saudi Arabic, then English, Riyadh's fixed UTC+3 (D-106), the seven read tools and `book_trip`; the persona's greetings, progress lines, instructions, the airline code's pronunciation and the vocabulary, all built from the names in the settings, each line a call speaks as written held to the lines' rule (no stop, wait, repeat, listening or send word, no booking's claim). |
| `src/flight_voice/settings.py`, `traveler.py` | Its settings under `FLIGHT_VOICE_` (every one is in [.env.example](../../.env.example)) and the library's under `T2V_`; the demo traveler every join token names. |
| `src/flight_voice/server.py`, `routes.py` | The server on 127.0.0.1:7862: the page's files with the library's page headers, the token route (`POST /token`, 50 tokens a day), `GET /api/profile`, and on this machine alone `GET /api/bookings` and `POST /api/demo/reset`; the library's router under `/voice`, its test console under `env` dev. |

Everything in the mock airline is fixed data or computed from fixed data, so the same inputs give
the same answer on every run and a call's facts are checked in code. Its tests are in
`tests/flight_voice/`:

```bash
uv run pytest tests/flight_voice
```

## Running it

Add to `.env` the access code the page asks for, `FLIGHT_VOICE_ACCESS_CODE` (at least 16
characters: `python -c "import secrets; print(secrets.token_urlsafe(24))"`); the library's
settings it needs are the ones Ole5's server needs (`T2V_ENV`, the join keys, the Groq key). Then:

```bash
uv run --offline python -m flight_voice.server --env-file .env
```

It serves on `http://127.0.0.1:7862/`, and under `T2V_ENV=dev` with `T2V_SERVER__DEV_PAGE=true`
the library's test console at `http://127.0.0.1:7862/voice/dev/console`. Its runtime keeps its
files in `flight/` under `T2V_STORAGE__VAR_DIR`, apart from Ole5's, so both servers run at once.
The mock airline is in memory: each start, and the page's "Start over", puts its bookings back to
the five past trips. `FLIGHT_VOICE_TODAY` pins the airline's today (`live` by default), and the
`FLIGHT_VOICE_*_MODE` settings make its searches, its profile or its bookings fail, slow down or
time out for a demo of each.

Its scripted calls come with the next parts of the build.
