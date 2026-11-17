# Flight-booking voice agent

The second app built on T2 Agentic Voice, and the main one shown (D-101): the booking line of a
mock airline, T2 Air, whose voice assistant is Saad. A caller plans a trip by voice in Saudi
Arabic, MSA or English, hears a day's flights briefly (one or two each by time and fare; three or
four by their count, their first and last departure times and the cheapest; the others when they
ask), and books it only after the trip is read back in full and they say a yes (invariant 1;
D-108: a yes said over the read-back books once its summary has played to its end). It uses only the library's public API, as
a teammate's app would, and imports no other app.

Its build spec is [flight-voice-agent.md](../../docs/design/flight-voice-agent.md).

## What is here

| Folder | What it holds |
| --- | --- |
| `src/flight_voice/airline/` | The mock airline: its ten airports, with their names in both languages, the names a caller may give each and a fixed offset from UTC; its timetable (every route starts or ends in Riyadh, no Singapore flight on Tuesdays, first class only on the 787-9, no day sold after 2027-03-27, where the fixed offsets stop holding); its fares in Saudi riyals, one way and per person, seeded from SHA-256, and the seats left in each cabin; the dates a caller says, resolved against today in Riyadh (UTC+3 all year); the demo traveler, Khalid, and the counts of his past trips; the bookings store in memory, seeded with those trips, with its modes (answer, refuse, timeout, late); and the facade the tools call, whose reads can be set to fail or be slow. |
| `src/flight_voice/said/` | The words the agent says with no number in them, in Saudi Arabic, MSA and English: weekdays, months, cabins, the parts of the day, routes ("Riyadh to London", «من الرياض للندن»), a trip's kind and the fare's basis ("per person, one way"); and, for the lines the app renders in code alone (the booking's read-back and its outcome), numbers, times, dates, amounts and the travelers in words by register («تسع وعشر دقايق الصبح», «التاسعة وعشر دقائق صباحًا», "nine ten in the morning"), until the library says these forms itself. |
| `src/flight_voice/tools/` | The read tools the talker calls: what each result holds (its status, its facts as values, its words in the reply's registers and a fixed `say` telling the talker what to say next), the card it shows on the page (each option a row with its mark), `search_flights`, `choose_flight` (a pick as the caller said it, "the second one", "the morning one", read in code against the options listed), `change_trip` (travelers, cabin, one way, with the chosen legs priced again), `get_trip`, `fare_calendar` (the seven cheapest days of a month or of 30 days, three marked to be said), `compare_cabins` (each cabin's fare and seats on one listed flight) and `traveler_profile` (the caller's tier, trips and bookings with every count worked out, read for the verified caller alone); `flight_tools` gives all seven. Once every leg is chosen, the result sends the talker straight to the booking's read-back, so the caller hears the trip and its total once. A read of the airline that fails is said as a failure, never as nothing found. |
| `src/flight_voice/booking/` | The booking, `book_trip`, the one action: the talker calls it with no arguments, and its draft, hidden from the talker, is filled from the call's trip, priced again; the read-back says the trip whole in words, its kind ("round trip", "one way") first, then asks "Shall I book it?" / «تبيني أحجزها؟»; only the caller's spoken yes books it (said over the summary, it books once the summary has played to its end; D-108), for the verified traveler alone. `done` says the city and the day, never the reference; a refusal is said as failed; a write with no answer is looked up and said unknown when nothing finds it; one booking a call. |
| `src/flight_voice/lean/` | The lean agent (D-113, the owner's "Lean next to it"), served beside today's when `FLIGHT_VOICE_AGENT=lean`: the same airline, trip, persona, words and page, the model leading with short instructions and a calendar written into its prompt (`prompt.py`, `instructions/`), and four tools of plain data with no scripted lines: `find_flights` (a day's flights each way by stable ids, or a span of days), `choose_flights` (the picks the model resolved, a changed cabin or traveler count, the trip so far and its total), `book_trip` and today's `traveler_profile`. One booking check in code (`booking_check.py`): the trip is booked only once a reply stated its total, played up to it, and the caller spoke after it, read from the call's events. It declares no action: `book_trip` writes to the mock store itself, for the mock airline alone. |
| `src/flight_voice/trip.py` | The trip each call is planning, kept in code: its route, dates, travelers and cabin, the options last listed for each leg and the flight chosen, so a pick such as "the second one" is read against what was said. |
| `src/flight_voice/agent.py`, `persona.py`, `instructions/` | The declaration the runtime runs: Saudi Arabic, then English, Riyadh's fixed UTC+3 (D-106), the seven read tools and `book_trip`; the persona's greetings, progress lines, instructions, the airline code's pronunciation and the vocabulary, all built from the names in the settings, each line a call speaks as written held to the lines' rule (no stop, wait, repeat, listening or send word, no booking's claim). |
| `src/flight_voice/settings.py`, `traveler.py` | Its settings under `FLIGHT_VOICE_` (every one is in [.env.example](../../.env.example)) and the library's under `T2V_`; the demo traveler every join token names. |
| `src/flight_voice/server.py`, `routes.py` | The server on 127.0.0.1:7862: the page's files with the library's page headers, the token route (`POST /token`, 50 tokens a day), `GET /api/profile`, and on this machine alone `GET /api/bookings` and `POST /api/demo/reset`; the library's router under `/voice`, its test console under `env` dev. |
| `src/flight_voice/evals/`, `evals/calls/` | Its scripted calls, one TOML file each, dev or held-out: the caller's turns (words, said over the reply or a read-back, or the client's Stop) and what each reply is expected to do (the tools called and what they held, every date beside the form the caller's words name, the trip read back, with no total, the outcome line, words said and never said, the language and register, the length); the model that reads them at the boundary (`scenarios.py`), the capabilities a call may wait for (`NEEDS`), and the rules a set keeps (`rules.py`: every expected date resolved by the airline's own date code, every flight read back flying on its day with seats, every kind in dev and held-out, no leg a dev and a held-out call share); and their runner, `poe eval-flights`: one play of a call through the library's `TextCall` with this agent and the real talker on a new mock airline (`call.py`), each turn's checks and the play's in code (`checks.py`, the long-call checks from the library's repeat measures), the records, the scorecard and the history line (`score.py`, `folder.py`, `history.py`), the run itself (`run.py`, `run_setup.py`, its command line `run_args.py`), and the lean agent's play and outcome checks (`lean_call.py`, `lean_checks.py`, `--agent lean`). |
| `web/` | Its page, plain HTML, CSS and JavaScript on the library's client: the airline's mark and name, "Your trips", the traveler, "Start over" (asked first) and the language toggle (Arabic first, right to left; it sets the call's starting language); the orb and the state line following the call; the lines the caller could say, as text; the cards mirroring what was said, in three segments, the outbound flights (or a calendar of days), the return flights and the trip for review (waiting for the yes, then booked with its reference), each filled in place by the card whose slot names it, each option a row (the flights listed, the days, the cabins, the trip) whose mark, the lowest fare, the caller's pick or one not available, is a style and a word of the page's own; the conversation and the options (the access code, kept in the page's memory alone, the box to record the call, push to talk) folded away. Every text is our own (`texts.js`) and set as text. |

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
time out for a demo of each. `FLIGHT_VOICE_AGENT` chooses the agent served: `scripted` (today's,
the default) or `lean` (the model-led one beside it, D-113; its traces and files under the name
`flight-lean`). The lean agent's calendar is written as the server starts, and its airline keeps
that day as its today, so restart the server each day and pin `FLIGHT_VOICE_TODAY` only to
today: the library's "Today is" line follows the clock, and each call on a calendar whose day is
not Riyadh's today logs `lean_calendar_stale`:

```bash
FLIGHT_VOICE_AGENT=lean uv run --offline python -m flight_voice.server --env-file .env
```

## Its scripted calls (run F)

Its scripted calls (`evals/calls/`, f01 to f28 the dev set, h01 to h15 the held-out set, written
apart on other days, routes and words, every kind held in both) are read and checked by the tests,
and played by `poe eval-flights`, which spends: each scenario of one split three times, on the
system clock with this agent and the real talker (`openai/gpt-oss-120b` at medium unless
`--model` and `--effort` say otherwise), against a new mock airline each play with the
scenario's modes and its today pinned, every fact checked in code (no judge). Run it from a
clean linked worktree at the commit it measures, never the main checkout, into a new absolute
folder under the main checkout's `var/runs/`, as Ole5's runs do:

```bash
uv run --offline poe eval-flights --split dev --out C:/path/to/main-checkout/var/runs/f-dev-1   --env-file C:/path/to/main-checkout/.env
```

It prints a dry estimate of its most spend before anything is sent and is refused past
`--cap-usd` (10); a smoke play (the first dev scenario once) must end with no failed, retried or
refused request and no violation; then every scenario is played once, then again, until each
has its `--repeats`. Its progress lines are identifiers and verdicts, never a text. The folder
gets each play's record (`plays.jsonl`, each turn's words kept for reading a failure),
`sessions.jsonl`, `scorecard.json` and `scorecard.md`; a scenario passes when every check holds
in at least two of its three plays, and one violation in any play breaks the hard constraint.
Each session appends one line to `evals/history.jsonl`, which the library's day counter reads
with Ole5's, so both apps' runs share the key's day: commit that line before `--resume`, which
goes on with a run stopped by the cap, the day's limit or an interrupt, each play played once
(at the run's commit, or a later one that changed only the apps' `evals/history.jsonl`; the
run keeps its first commit, and each session records its own).
It exits 0 when the run is complete, 1 when it is not, 2 when it is refused. `--price` and
`--limits` give another model's price and limits; the defaults are `gpt-oss-120b`'s as Ole5's
runs give them. The held-out set is read rarely, by the lead, with `--split held-out` named; its
smoke play is still the first dev scenario, so no held-out call is played but in its own run.

`--agent lean` plays the same scenarios with the lean agent and scores their outcomes (the
booking made or not, its flights, days, travelers and cabin, the reference, the violations, the
language, register, stage notes, notices, length and repeats), not the scripted agent's tools and
lines; it reports, beside them, the caller turns and the seconds until the booking and the words
the agent said. A turn said over the read-back's summary or its closing question is said right
after the lean agent's reply, which has no read-back. The run, its scorecard and its history line
name the agent, so the two compare by scenario (section 13 of the build spec).
