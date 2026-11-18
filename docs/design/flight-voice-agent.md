# Build spec: the flight-booking voice agent (`apps/flight-voice-agent/`, package `flight_voice`)

Plan 010, Phase F (F.1 to F.4), Q23. Written 2026-11-16 for builder agents who know the library
but not this app, and revised the same day after two reviews (section 12). Read this whole file
before your first commit.

**The lead's ruling of 2026-11-16, over every line below that says otherwise: no tzdata.** It is
not installed, and adding it is a download the owner has not approved. Riyadh keeps UTC+3 all year
(no summer time), so the call's date and "Today is" use a fixed `timezone(timedelta(hours=3))`;
the mock airline gives each airport a fixed UTC offset (London 0, Paris 1, Istanbul 3, Cairo 2,
Dubai 4, Doha 3, Mumbai 5:30, Singapore 8, Jeddah and Riyadh 3) and its booking window ends before
Europe's summer time begins (2027-03-28), so no zone database is needed. `VoiceAgent.time_zone`,
if L3 adds it, takes a fixed offset, not a zone name. No `uv add` of any package.

**The names, the owner's of 2026-11-16:** the persona is Saad / سعد and the airline T2 Air /
طيران تي تو, airline code T2. Every other name in this file that differs is a placeholder.

**L6 as built (B4, 2026-11-16):** `Clock` and `Sleep` are named `RunClock` and `RunSleep` (the
library's core already has a `Clock` protocol), the main-checkout refusal is `run_checkout`,
`check_out` and `run_refused`, and the day counter is `requests_today(histories, day)` with
`every_history(history)`. A flight history line is counted when it has a `requests` object
(model to count) and a `time` (ISO 8601).

**The owner's live-test round, as built (2026-11-17, `VERSION` 2026-11-17.4):** the booking
text (the model never asks its own booking question; a shorter read-back with every value kept;
the confirm verbs as the booking's send words and its own ask-again line, 4.2); the picks by the
dearest and by a fare said, a full flight said as full, nothing changed the caller did not ask
for, the lost flight named in `change_trip`, every option nonstop (3.3); a span of days for the
departure answered at once with a calendar of flights (2.4, 3.3), and the brief day listing of
the owner's ruling, "Brief, voice only" (3.2); four dev calls f29 to f32 and f22's outcome now `done` under the
owner's "any yes books" (7.2); and the page's three segments, outbound, return and review, each
filled in place by the card whose `slot` names it (D-110; 3.4, 6.1).

**The lean agent (D-113, the owner's ruling of 2026-11-17, "Lean next to it"):** a model-led
agent beside today's, chosen by `FLIGHT_VOICE_AGENT`, its booking checked in the app's code, and
run F's outcome mode for it (section 13). Everything above describes the scripted agent.

## 0. Read first

**Why this app exists.** The owner, 2026-11-16: make our voice agent do flight booking "for the
sake of comparison", keep Ole5 "as a reference or an assurance that both benefit from the
improvements", and "make the demo and testing and comparing using the flight booking agent".
Then: "I want the flight agent to be our main agent we show and work on." So this app is the
demo, the main test set and the comparison. Ole5 stays, and its sets rerun as the proof that
each library change is general.

**What the owner answered (plan 010's Q23, recorded 2026-11-16, commit 14b1b0f).**

- (a) "Spoken + optional cards": every option is said aloud. The page may show a card list that
  mirrors what was said; the caller never needs it (D-075's opt-in extra).
- (b) "Read-back + spoken yes": a booking is made only after our full read-back and a clear
  spoken yes (invariant 1). There is no typed code.
- (c) "A male Saudi voice, name later": Orpheus `abdullah` for Arabic, today's English voice
  (`troy`). The names are not chosen yet. The plan records that the agent proposes two or three
  names for the persona and for the airline. They are put to the owner before step A8 (section
  5.1). Until then the names are placeholders in settings, and no test names them.
- (d) "Its own page": served by its own app on its own port (7862).

**What we learn from the public demo, and what we never copy.** We learn patterns only. We
never copy its brand, its persona's name, its text, its prompt or its look. A test holds the
page's texts and the tool descriptions free of the demo's own strings (6.1). The patterns we
take (from `C:/Users/m7ms/Downloads/Teardown.md`):

| Demo pattern | What we do |
| --- | --- |
| Behaviour inside tool descriptions and results ("each result says what to say next") | Each result has a fixed `say` hint written by the app, never built from caller words |
| Errors written for the model ("ask for the return date; do not invent one") | Every failure is a `ToolError` that names the failure and the next step |
| Precompute what a model counts wrong (trip counts) | Dates, "the cheaper one", totals, trip counts: all computed in code |
| A booking context so "the second one" is read against what is shown | The trip draft and the last options listed are kept per call in code (`trip.py`) |
| Slot filling with silent defaults (round trip, economy, home airport) | The same, said in our instructions in our words |
| Never speak IDs, references, JSON or markers | The same; a reference only when asked |
| Filler line at about 1.2 s | The library's progress line now; 1.15's line at the search when it lands |
| Booking confirmed by a typed OTP | **Not taken.** Ours is the read-back and the spoken yes (invariant 1) |
| Tools run in the browser over RPC | **Not taken.** Tools run on the server; the page only shows (D-075) |
| Prompt and tools sent to the browser in the token (its weakness 1) | **Avoided.** Nothing of the prompt or tools leaves the server |
| A failed tool read as "no past trips" (its weakness 2) | **Fixed by design and by eval cases** (f11, f12, a held-out one) |
| Hidden `[event]` messages the client can fake (its smaller weakness) | **Avoided.** The client has no text channel into the call (`t2v/1`'s closed list) |

**Rules that bind every builder.**

- The app uses only the library's public modules (ARCH-PUBLIC): `t2_agentic_voice` and its
  facades (`ports`, `groq`, `identity`, `server`, `stores`, `events`, `languages`, `evals`,
  `tracing`, `classifiers`). Never a layer inside (`t2_agentic_voice.voice...`,
  `...actions...`). Tests may import internals, as Ole5's do.
- No Pipecat, no aiortc in the app (ARCH-BAN). No import of `ole5_voice` (an app never imports
  another app, `scripts/arch_public.py`). When something is missing, change the library (section
  9), never work around it in the app.
- Every module, Python and JavaScript, at or under 300 lines (plan 010's rule; harness's cap is
  400). Split before you pass 300, as a pure move.
- Structured logs only (`get_logger`), no `print`. Never read or print `.env`. Tests never touch
  `var/`, the developer's `.env` or the developer's shell settings.
- Every behaviour change ships with tests; every security change with adversarial tests.
- `uv run poe check` passes before each commit. Commits are small, one concern each, on a branch
  off `plan-010-integration` in your own worktree, ending with the attribution trailer the session
  gives. Never `preview_start` by name in this repository: start the server with Bash
  (`uv run --offline python -m flight_voice.server --env-file .env`) and open the URL.
- **The laptop's load** (it froze under five agents): set `PYTEST_XDIST_AUTO_NUM_WORKERS=4` for
  every `poe check`; run one `poe check` at a time on the machine (a builder waits for another's
  gate to end); remove `.mypy_cache` before each step's last gate (plan 010's rule).
- **Merging**: each step merges into `plan-010-integration` before any step that needs it starts
  (section 8). A step never starts on a branch that lacks what it needs.
- Arabic text in Python is written as Ole5 writes it: `\u` escapes with the sound and meaning in a
  comment, or plain Arabic in data modules where Ole5 does the same (its `drafts.py`, `lines.py`
  use plain Arabic). Pick one per module and keep it.
- Code and TOML never name a plan, its rows, tracks or blocks (D-090, DOC-PLANWORDS). Scenario
  data names capabilities, never plan rows (7.1).

## 1. The app's layout and how it registers

### 1.1 Files

Each line: the file, what it holds, its line budget.

```
apps/flight-voice-agent/
  pyproject.toml                 name "flight-voice-agent"; deps: t2-agentic-voice (workspace),
                                 fastapi, uvicorn, pydantic, pydantic-settings,
                                 tzdata; sys_platform == 'win32'
  README.md                      how to run it, its settings, its page, its run F         ~80
  src/flight_voice/
    __init__.py                  LOGGERS = (__name__, "__main__"), the package docstring  ~20
    agent.py                     the declaration: languages, greetings and progress lines
                                 (from persona.py), vocabulary, pronounce map, tools,
                                 version                                                 <=250
    persona.py                   the names from settings, the greetings, the airline's
                                 spoken form, the pronounce and vocabulary entries, the
                                 instructions read from instructions/ and filled; the
                                 lines' rule run on what it renders                       <=220
    instructions/en.md           the talker's instructions for English replies            ~40
    instructions/ar-SA.md        the same for Arabic replies, with Saudi examples         ~40
    settings.py                  FLIGHT_VOICE_* settings and the library's, one loader   <=280
    server.py                    the FastAPI app: page files, token route, API routes,
                                 the library's router under /voice, uvicorn on 7862      <=280
    routes.py                    GET /api/profile, GET /api/bookings, POST /api/demo/reset <=220
    traveler.py                  the caller as the demo traveler (Caller attributes)      <=80
    trip.py                      the trip draft, the call's state (TripBook)             <=260
    airline/__init__.py          what the package re-exports                              <=30
    airline/airports.py          the ten airports, names, spoken forms, aliases, zones    <=220
    airline/schedule.py          routes, flights a day, numbers, aircraft, durations     <=260
    airline/fares.py             fares by cabin and date, the fare calendar, seats       <=260
    airline/dates.py             DateSpec, its resolution against today in Riyadh        <=260
    airline/profile.py           the demo traveler, past trips, insights                 <=220
    airline/bookings.py          the bookings store in memory, its modes, reset          <=260
    airline/system.py            the Airline facade the tools and the action call;
                                 its read modes (answer, fail, slow)                     <=200
    said/__init__.py             the word forms by language                               <=60
    said/words.py                words with no numbers: routes ("to London", «للندن»),
                                 weekdays, months, cabins, parts of day, fixed phrases
                                 ("per person, one way"), in Saudi, MSA and English      <=260
    said/numbers.py              ONLY until L4 lands: the read-back's Saudi number, time
                                 and date words behind L4's function names; deleted
                                 when L4 lands                                           <=200
    tools/__init__.py            flight_tools(airline, trips) -> the seven tools            <=40
    tools/results.py             result models, failure messages                         <=260
    tools/says.py                the fixed `say` strings                                 <=200
    tools/cards.py               the card for each result, and its evidence texts        <=220
    tools/search.py              search_flights                                          <=280
    tools/overview.py            the search over a span of days, its calendar card       <=200
    tools/listing.py             a leg's options, their order and the listing's say      <=220
    tools/picks.py               a pick as the caller said it, read against the listing  <=160
    tools/calendar.py            fare_calendar                                           <=200
    tools/cabins.py              compare_cabins                                          <=180
    tools/choose.py              choose_flight                                           <=280
    tools/change.py              change_trip                                             <=200
    tools/trip_view.py           get_trip                                                <=140
    tools/profile.py             traveler_profile                                        <=200
    booking/__init__.py                                                                   <=20
    booking/draft.py             BookingDraft (fields filled by validate), BookingMade   <=220
    booking/lines.py             read-back, done, sending, failed, unknown, declined,
                                 claims, send words                                      <=300
    booking/action.py            book_trip: validate, execute, lookup                    <=240
    evals/__init__.py                                                                     <=20
    evals/scenarios.py           run F's scenario model, its capabilities, `problems()`  <=300
    evals/call.py                the seam to TextCall: play one scenario                  <=300
    evals/call_wait.py           how a play waits on its call (bookings, a held yes)      <=300
    evals/checks.py              each turn's checks, L's checks, the play's              <=300
    evals/score.py               play records, the scorecard, the history line           <=260
    evals/run.py                 `poe eval-flights`: arguments, refusals, estimate,
                                 smoke, plays, resume                                    <=300
  web/
    index.html                   the page's markup, no inline script or style            <=150
    app.css                      the page's look, light and dark, right to left          <=300
    app.js                       the call: VoiceClient, state, captions, orb             <=300
    cards.js                     the three segments the cards fill, as text              <=200
    bookings.js                  "Your trips": fetch, list, reference filter             <=200
    texts.js                     every fixed text of the page, Arabic and English        <=200
    mark.svg                     our own airline mark (simple, ours)
  evals/
    calls/f01_*.toml ...         run F's scenarios, dev and held-out by `split`
    recording.toml               the lines the recording session adds (section 7.4)
    history.jsonl                one line per run F session
tests/flight_voice/
  conftest.py, support modules, test_<module>.py for each module above,
  test_own_words.py              the page texts and tool descriptions hold none of the demo's
```

### 1.2 Registration with the harness (in step A1)

1. `harness.toml`:
   - `[[apps]]` `name = "flight_voice"`, `root = "apps/flight-voice-agent/src"`.
   - The Pipecat/aiortc `[[bans]]` table: `within = ["ole5_voice", "minimal_example",
     "flight_voice"]`.
   - `[package] banned_words`: add `"flight_voice"`, so the library never names this app.
   - `[tool.coverage.run] source`: add `"flight_voice"`.
2. Root `pyproject.toml`:
   - `[project] dependencies` and `[tool.uv.sources]`: add `"flight-voice-agent"` (workspace).
   - `[tool.poe.tasks.types]`: add `apps/flight-voice-agent/src` to the mypy command.
   - `[tool.mypy] mypy_path`: add `apps/flight-voice-agent/src`.
   - A task `eval-flights` (`python -m flight_voice.evals.run`), help: "Run F: the flight
     agent's scripted calls over one split, each three times, on the mock airline (spends: model,
     effort and cap on its command line)". It refuses the main checkout, as every run does.
   - Add tzdata with `uv add --package flight-voice-agent "tzdata; sys_platform == 'win32'"`
     (never edit `uv.lock`): the app uses zoneinfo itself, and arrival times cross zones that
     change clocks inside a later booking window (London, Paris). The library gains it too, in
     L3 (section 9).
3. `tests/isolation.py`: add `"FLIGHT_VOICE_"` to `DROPPED_PREFIXES`, as an app-prefixes tuple
   (`APP_PREFIXES = ("OLE5_VOICE_", "FLIGHT_VOICE_")`), so a `FLIGHT_VOICE_ACCESS_CODE`,
   `_TODAY`, `_BOOKING_MODE` or `_SEARCH_MODE` in the owner's shell never reaches a test.
   Extend `tests/harness/test_isolation.py` to check it, and add a flight settings test tying the
   app's prefix to it, as Ole5's settings test does.
4. `CLAUDE.md` is at its cap (120 of 120 lines, `[docs] max_entry_lines`). Add the app to the
   intro sentence, the code map (`apps/flight-voice-agent/src/flight_voice/` and its `web/`) and
   the `eval-flights` command, and win the lines back by joining rows (for example the two
   `apps/ole5-voice-agent` lines of the code map into one). `poe docs` checks the cap.
5. `ARCHITECTURE.md` (its app list, line 28 on), `docs/design/package-design.md` (section 2 and
   the repository layout near line 1556), `docs/harness/quality.md` (a row for `flight_voice`
   after `poe quality`), and a decision: **D-101**, "The flight-booking agent is the second app
   and the main demo; Ole5 is the check that a change is general" (next free number after D-100;
   check `decisions.md` first). DOC-REF reads citations: never cite a decision before it exists.

### 1.3 What it takes from the library, and what it must not

| Takes | From |
| --- | --- |
| `VoiceAgent`, `Language`, `Vocabulary`, `tool`, `Tool`, `ToolError`, `ToolResult`, `CallContext`, `from_caller`, `action`, `Action`, `ActionContext`, `ActionNotSent`, `ActionRejected`, `ReadBack`, `Say`, `Claims`, `Spoken`, `Card`, `Caller`, `Consent`, `VoiceSettings`, `GuardSettings`, `LimitSettings`, `VoiceRuntime`, `configure_logging`, `get_logger`, `ConfigurationError` | `t2_agentic_voice` |
| `SignedJoinTokens` | `t2_agentic_voice.identity` |
| `CallEnded` (to drop a call's trip draft) | `t2_agentic_voice.events` |
| `normalize_arabic`, `normalize_digits`, `register_of`, `speak_number` and L4's new functions | `t2_agentic_voice.languages` |
| `TextCall`, `TextTurn`, `ScriptedLLM`, `FunctionLLM`, `ActionSafetySuite`, `sign_test`, L6's paced chat model, L8's repeat checks | `t2_agentic_voice.evals` |
| `GroqChat` | `t2_agentic_voice.groq` |
| L1's token route and page headers | `t2_agentic_voice.server` |

It must not: import a layer inside the library; import Pipecat, aiortc or `ole5_voice`; build
`HeardWords`, a receipt or a `ConfirmedAction` (the arch check's `[[restricted]]` stops it);
read the environment outside `settings.py`.

## 2. The mock airline

Everything is fixed data or computed from fixed data. Same inputs, same answer, on every run.
Nothing is random; every "seeded" value comes from SHA-256 of a fixed string (Python's `hash()`
is salted per process: never use it). `SEED = "t2air-2026-11"`.

### 2.1 The ten airports (`airline/airports.py`)

Codes are a closed set (`Literal`). Callers name cities, not codes, so tools take what the
caller said and the code matches it against the aliases (after `normalize_arabic` and lower
case). An unknown city is a `not_served` result, never a guess.

| Code | City (en) | City (ar) | Airport (en) | Airport (ar) | Zone | Aliases (besides the city's own names) |
| --- | --- | --- | --- | --- | --- | --- |
| RUH | Riyadh | الرياض | King Khalid International | مطار الملك خالد الدولي | Asia/Riyadh | رياض, Riyad |
| JED | Jeddah | جدة | King Abdulaziz International | مطار الملك عبدالعزيز الدولي | Asia/Riyadh | جده, Jedda, Jidda |
| DXB | Dubai | دبي | Dubai International | مطار دبي الدولي | Asia/Dubai | ديبي |
| DOH | Doha | الدوحة | Hamad International | مطار حمد الدولي | Asia/Qatar | الدوحه, قطر, Qatar |
| CAI | Cairo | القاهرة | Cairo International | مطار القاهرة الدولي | Africa/Cairo | القاهره, مصر, Egypt |
| IST | Istanbul | إسطنبول | Istanbul Airport | مطار إسطنبول | Europe/Istanbul | اسطنبول, تركيا, Turkey, Turkiye |
| LHR | London | لندن | Heathrow | مطار هيثرو | Europe/London | هيثرو, Heathrow |
| CDG | Paris | باريس | Charles de Gaulle | مطار شارل ديغول | Europe/Paris | فرنسا, France |
| BOM | Mumbai | مومباي | Mumbai International | مطار مومباي الدولي | Asia/Kolkata | بومباي, الهند, Bombay, India |
| SIN | Singapore | سنغافورة | Changi | مطار شانغي | Asia/Singapore | سنغافوره, سنقافورة |

Spoken forms, per language, for each city (`said/words.py`): the name alone, "to" and "from".
Saudi and MSA: `للندن` / `إلى لندن`, `من لندن`; English: "to London", "from London". A city
whose Arabic name starts with «ال» takes «لل» in Saudi (`للرياض`, `للدوحة`, `للقاهرة`). Test every
form.

A country alias maps to its one airport here (مصر → CAI). Any other city ("Manchester",
«أبها») is `not_served`, with the list of the ten said in the result.

### 2.2 Routes and the schedule (`airline/schedule.py`)

Every route starts or ends in Riyadh: RUH to each of the other nine, and back. A route between
two other cities (Jeddah to Dubai) is `not_served` with the hint to fly through Riyadh as two
trips. No connections are sold (a decision the owner may change).

Times are local at each airport. Arrival is departure plus the duration, shown in the arrival
airport's zone, with `next_day` set when the date changes. The airline code is a setting,
`T2` by default. Outbound flights are odd, return flights even.

| Route | Out of RUH (local) | Back to RUH (local at the other airport) | Duration out / back | Aircraft | Numbers out / back |
| --- | --- | --- | --- | --- | --- |
| JED | 06:00, 10:30, 15:00, 21:00 | 07:45, 12:30, 17:15, 23:00 | 1h50 / 1h45 | A320neo | 101 103 105 107 / 102 104 106 108 |
| DXB | 07:15, 13:40, 20:30 | 10:20, 17:05, 23:55 | 1h55 / 2h00 | A321neo | 201 203 205 / 202 204 206 |
| DOH | 08:00, 14:20, 19:45 | 10:40, 17:00, 22:30 | 1h25 / 1h30 | A320neo | 251 253 255 / 252 254 256 |
| CAI | 09:30, 18:15 | 13:20, 22:40 | 2h45 / 2h35 | A321neo | 301 303 / 302 304 |
| IST | 02:10, 11:50 | 09:05, 18:30 | 4h30 / 4h15 | A321neo | 351 353 / 352 354 |
| LHR | 09:10, 14:40 | 16:00, 21:45 | 7h05 / 6h20 | 787-9 | 401 403 / 402 404 |
| CDG | 01:55, 08:35 | 11:30, 15:10 | 6h35 / 6h05 | 787-9 | 451 453 / 452 454 |
| BOM | 03:20, 16:45 | 09:30, 21:15 | 4h00 / 4h30 | A330-300 | 501 503 / 502 504 |
| SIN | 22:05 | 08:40 | 8h20 / 9h10 | 787-9 | 601 / 602 |

Every route flies every day, except Singapore: no flight either way on Tuesdays. That one gap
gives the "no flights that day" case and its "nearest days" answer.

First class is sold only on the 787-9 (LHR, CDG, SIN). Asking for first class elsewhere is a
`cabin_not_offered` result, with business offered.

All flights are nonstop. The booking window: from today to today plus 120 days. Before today or
past the window is a `date_problem` result naming the window's last day.

### 2.3 Fares, the fare calendar and seats (`airline/fares.py`)

A fare is one way, per person, in Saudi riyals, whole tens.

Base economy fare by route (the same both ways):

| JED | DXB | DOH | CAI | IST | LHR | CDG | BOM | SIN |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 390 | 650 | 520 | 980 | 1,450 | 2,350 | 2,250 | 1,350 | 2,750 |

economy = round10(base × weekday × season × hour × deal × jitter), then
business = round10(economy × 3.2), first = round10(economy × 5.5).

- **weekday** of departure (the Saudi weekend is Friday and Saturday): Sun 1.00, Mon 0.90,
  Tue 0.85, Wed 0.95, Thu 1.20, Fri 1.10, Sat 1.05.
- **season**: 2026-12-17 to 2027-01-03 × 1.30 (winter break); 2027-03-05 to 2027-03-14 × 1.25
  (the Eid days, as the mock places them); else 1.00. These are the mock's own dates.
- **hour**: a departure from 00:00 to 05:59 local × 0.90; else 1.00.
- **deal**: × 0.80 when `h("deal", route, date) % 13 == 0` (a deal day applies to every flight of
  the route that day, so the calendar shows cheaper days).
- **jitter**: × 0.97, 1.00 or 1.03 by `h("jitter", flight, date) % 3`.

`h(*parts)` is `int(sha256("|".join([SEED, *parts])).hexdigest()[:12], 16)`.

**The fare calendar**: for a route and a span (a month, or 30 days from a date), the cheapest
economy fare of each day (its cheapest flight). `null` for a day with no flight (a Singapore
Tuesday), never a made-up fare.

**Seats left**, per flight, date and cabin, from `h("seats", flight, date, cabin)`:
economy `4 + h % 57`, but 0 when `h % 41 == 0`; business `h % 9`, so 0 about one time in nine;
first (787-9 only) `h % 5`. A flight with fewer seats than the travelers in the cabin asked is
`no_seats` for that cabin, and the result offers the other cabins and the other flights that day.
Seat maps and seat numbers are out of scope.

A builder writes a small test helper that finds, from the airline module, the dates the
scenarios need (a business sell-out, a deal day): scenarios name the dates, the helper's test
proves the dates still have those properties, so a formula change fails loudly.

### 2.4 Today, and Riyadh time (`airline/dates.py`)

- The airline's `today` is a setting, `FLIGHT_VOICE_TODAY`: `live` (the default for the server:
  today's date in Asia/Riyadh at each tool call) or an ISO date. Run F and the tests pin it to
  **2026-11-16, a Monday**.
- The library's prompt says "Today is <date>" from the call's clock in UTC (`agent/turn.py`),
  which is a day behind Riyadh from 00:00 to 03:00 Riyadh time, and on `TextCall`'s virtual
  clock is 2026-01-01. L3 (section 9) makes both match. Until L3 lands, the talker never needs
  the date: it passes date forms and the code resolves them, and every result says the resolved
  date with its weekday.

**`DateSpec`**, what the talker passes for a date (a pydantic union discriminated by `kind`):

| kind | Fields | Caller says | Resolves to (today Monday 2026-11-16) |
| --- | --- | --- | --- |
| `relative` | `when`: `today`, `tomorrow`, `day_after_tomorrow` | «بكرة», «بعد بكرة», "tomorrow" | 11-16, 11-17, 11-18 |
| `weekday` | `weekday`: `sun`..`sat`; `which`: `coming`, `next_week`, `following` | «الخميس الجاي», "next Thursday", "this Thursday" → coming; «الأسبوع الجاي يوم الثلاثاء», "Tuesday next week" → next_week; «الخميس اللي بعده», "Thursday after next" → following | coming Thu 11-19; next_week Tue 11-24 (the week from Sunday 11-22); following Thu 11-26 |
| `on` | `day` 1-31; `month` 1-12, optional | «يوم ١٤», "the 14th"; «١٤ ديسمبر», "December 14th" | the 14th: this month if not past, else next month (12-14 here, since 11-14 has passed); with a month: its next date on or after today (2026-12-14) |
| `in_days` | `days` 1-120 | a departure: "leave in four days", «أسافر بعد أربع أيام»; never a return said after the departure | 11-20 |
| `nights` (return only) | `nights` 1-60 | "back a week later", «أرجع بعد أسبوع», "back four days later", «أرجع بعد أربع أيام», "for four nights" | departure + nights («بعد بكرة ... وأرجع بعد ثلاث أيام»: 11-21) |
| `weekday_after` (return only) | `weekday` | «الأحد اللي بعده», "the Sunday after" | the first such day after departure |
| `days` (`search_flights`' departure only) | `span`: `this_week`, `next_week`, `this_weekend`, `next_weekend`, `coming` | "what flies next week", «وش فيه رحلات نهاية الأسبوع», "the soonest you have" → coming | this_week 11-16 to 11-21; next_week 11-22 to 11-28; this_weekend 11-20 to 11-21; next_weekend 11-27 to 11-28; coming 11-16 to 11-22 |

Rules: `coming` is never today (1 to 7 days ahead). The Saudi week starts on Sunday and its
weekend is Friday and Saturday; a span (`days`, `resolve_span`) is kept inside the booking window
(a day before today or past the window left out; a span wholly past it a `date_problem`), and a
return or the fare calendar never takes one (added 2026-11-17: the owner's "next week" was made a
Monday nobody said). Never a year from the talker: the code picks it. A month-day that does not exist (31 November) is a
`date_problem`. A resolved date carries `assumed` true when the code chose the month or the
year, so the result's `say` asks the talker to say the date back with its weekday.

Every resolved date comes back as `{"iso": "2026-12-17", "day": 17, "month": "December" /
«ديسمبر», "weekday": "Thursday" / «الخميس»}`, the words in the reply's language. The talker
writes the day in digits (3.6).

### 2.5 The demo traveler (`airline/profile.py`)

| Field | Value |
| --- | --- |
| id | `T-0001` |
| name | Khalid Al-Harbi / خالد الحربي (first name Khalid / خالد; addressed in the masculine) |
| tier | Gold / ذهبي (tiers: Blue, Silver, Gold) |
| home airport | RUH |
| preferred cabin | economy |

Past trips, before 2026-11-16 (references are six digits, so the output guard's ID rule
protects them: a reference said without evidence is blocked):

| Reference | Trip | Dates | Travelers | Cabin | Total (SAR) |
| --- | --- | --- | --- | --- | --- |
| 482913 | Riyadh - Dubai, round trip | 2026-10-08 to 2026-10-11 | 1 | economy | 1,380 |
| 517204 | Riyadh - London, round trip | 2026-09-03 to 2026-09-14 | 1 | business | 15,640 |
| 390655 | Riyadh - Jeddah, round trip | 2026-08-20 to 2026-08-23 | 2 | economy | 1,720 |
| 604118 | Riyadh - Cairo, one way | 2026-06-12 | 1 | economy | 1,040 |
| 275930 | Riyadh - Dubai, round trip | 2026-03-19 to 2026-03-22 | 1 | economy | 1,450 |

**Insights, precomputed** (the demo's lesson): trips in all (5), trips per city (Dubai 2,
London 1, Jeddah 1, Cairo 1), the last trip to each city with its date, the most visited
city (Dubai), the cabin used most (economy). The talker never counts.

**The caller is the traveler.** The token route mints every token for the demo traveler:
`Caller(subject="owner", attributes={"traveler_id": "T-0001"})` (`traveler.py`). Tools bind it
with `from_caller("attributes.traveler_id")`, hidden from the talker. Nothing said in the call
changes whose bookings are read or made (invariant 3). The bookings store answers only for the
traveler id it is given.

### 2.6 The bookings store (`airline/bookings.py`)

- In memory. Seeded with the five past trips. `reset()` puts it back to the seed. The server
  resets it at start and on `POST /api/demo/reset`. Nothing is written to disk.
- `create(NewBooking)`: request id (idempotency key), traveler id, legs (flight, date), cabin,
  travelers, the total the read-back said. It re-prices the legs; a different total or seats
  gone is `BookingRefused` (the read-back's price is the price booked, or nothing is booked).
  A new reference: six digits from `h("ref", request_id)`, never one already held.
- `find(request_id, traveler_id)`: the lookup for a write whose reply was lost (invariant 6).
- Write modes, as Ole5's mock tickets: `answer`, `refuse`, `timeout` (waits `late_s`, does
  nothing), `late` (does it at once, answers after `late_s`); `late_s` 30 s, above the action's
  20 s timeout. `lookup` on or off.
- `listed(traveler_id)`: every booking, newest first, for the page and `traveler_profile`.

**Read modes** (`airline/system.py`), set by settings or a scenario: `search_mode` for flight
searches, the calendar and cabins (`answer`, `fail`, `slow`: answers after `slow_s`, 4 s by
default, so the progress line plays), and `profile_mode` for the profile (`answer`, `fail`).
A failing read raises `AirlineUnavailable`; each tool turns it into a `ToolError` that says it
failed (section 3.5).

## 3. The tools, the trip draft and the dates

### 3.1 The trip draft is the call's state (`trip.py`)

`TripDraft` (pydantic, frozen; each change makes a new one):

- `origin` (default the traveler's home, RUH), `destination`, `depart` (resolved date),
  `return_date` (resolved date or none), `one_way` (default false), `travelers` (default 1,
  1-9), `cabin` (default the traveler's preferred, economy);
- `shown`: for each leg, the options last listed to the caller, in the order said, each with
  its ordinal (1, 2, 3...) and its flight and date;
- `chosen`: for each leg, the flight picked, or none.

`TripBook` holds one `TripDraft` per call, keyed by `CallContext.call_id`, at most 64 calls
(the oldest dropped past it). The server drops a call's draft when its `CallEnded` event comes
(`runtime.on(CallEnded, ...)`). Each run F play makes its own `TripBook` and airline.

Why in code and not only in the talker's history: plan 010's 1.4 will shorten old tool results
in the history, and the demo's own teardown shows the model guessing "the second one" wrong.
Code resolves "the cheaper one", "the second one", "the morning one" against `shown`.

A changed date clears that leg's choice. A changed cabin or traveler count re-prices both legs'
choices; a leg whose flight has too few seats in the new cabin loses its choice, and the result
says which leg and lists that leg's options.

Tools write the draft only as their last step, in one assignment, so a tool cancelled by a
barge-in leaves the draft as it was or wholly changed. A written draft whose result the talker
never read is harmless: the next result and the read-back say it whole.

### 3.2 What every result holds (`tools/results.py`)

Each result is a pydantic model returned as the tool's data. Short: under about 1.5 KB of JSON.

- `status`: one word from a closed set per tool (below). `ok` means there is something to say.
- the facts as machine values: times `"09:10"`, fares `2450`, totals `5120`, durations
  `{"hours": 7, "minutes": 5}`, dates as in 2.4. The talker writes numbers in digits, as the
  library's prompt rules say ("Write every number in digits"); the output guard then checks
  every fare, total and reference against the results, and the library's speaking rules turn
  the digits into words after the guard (3.6). Words with no numbers come with a `said` form in
  the reply's language (`ctx.language`; for an `ar-SA` reply, also `said_msa`): routes, cities,
  weekdays, months, cabins, parts of day.
- `fare_basis_said`: a fixed phrase, «للشخص، رايح بس» / «للشخص، ذهاب فقط» / "per person, one
  way", on every result that lists fares.
- `say`: **one of the app's fixed strings**, in English, telling the talker what to say next.
  Never built from caller words or from any free text. A test lists every `say` string.
- at most 4 options, each flying nonstop (`nonstop: true`, so "does it stop anywhere?" is
  answered). **The day listing is brief** (the owner's ruling of 2026-11-17, "Brief, voice only", amending
  D-101's "every option is said aloud" for this agent): one or two flights each said by its
  departure time and fare; three or four by how many there are, the first and last departure
  times and the cheapest by its time and fare, the others only when the caller asks (their data
  stays in the result and the card shows every one). A listing gives `count`, `first_departs`
  and `last_departs`, computed in `listing.py`; options keep their numbers and the card's row
  order, so a number pick still matches the card. The fare's basis is said once a call, on the
  first listing; every other listing and `chosen_then_return` say "Do not say again". The says
  are `tools/says.py`'s (`listed`, `listed_full`, `listed_brief`, `listed_brief_full`, and the
  same for `return_listed` and `relisted`); a full flight's rule comes before the basis: "say it
  by its departure time as full, with no fare, and never as the cheapest."
- `evidence` (`ToolResult.evidence`): the texts of the result's card, so every number the card
  shows has evidence (3.4).

A failure is never a result with an empty list: it is a `ToolError` (the library gives the
talker its message and marks the call failed, `ok: false`). "Nothing found" is a status of its
own (`no_flights_that_day`), with the nearest days that have flights.

### 3.3 The tools

All seven are read tools (`@tool`), `timeout_s` 5, `progress` `searching` (search, calendar,
cabins) after 2.6 s, the library's default. Their descriptions are in English, short, our own
words, and say when to call them. Each one's schema is the only thing the talker sees of it.

**`search_flights`**

- Description: "Find flights for the caller's trip and list them. Call it in the same reply as
  soon as the caller has said where they go and when they leave, and, for a round trip, when
  they come back, with no question to confirm it first; never before, and never with a day they
  did not say. After a listing, never again for a pick or a cabin change. Pass the city as the
  caller said it and dates as date forms; never work out a date yourself. Fares are one way, per
  person, in Saudi riyals." (f-dev-5 missed the search on 7 of 75 first turns that should
  search, two of them with a question to confirm a day.) (Before a listing, after
  `cabin_not_offered` or a day's `no_seats`, the draft holds nothing, so a new cabin is a new
  search.)
- Arguments: `destination` (str, 1-40 chars, the caller's words); `origin` (str, optional,
  default the traveler's home); `depart` (DateSpec or a span of days, "The day they leave, as
  the caller said it; never a day they did not say. A span of days only when they asked what
  flies over days and named no single day."); `return_date` (DateSpec, optional);
  `one_way` (bool, default false); `travelers` (int 1-9, optional, keeps the draft's);
  `cabin` (`economy`, `business`, `first`, optional, keeps the draft's).
- Checks, in order: cities known (`not_served`); the route flies (`not_served`, with "we fly to
  and from Riyadh"); dates resolve and fall in the window (`date_problem`); a round trip with
  no return date gives `needs_return_date` and searches nothing (`say`: "Ask when they would like
  to come back. Do not list flights yet."); return not before departure (`date_problem`); the
  cabin is offered on the route (`cabin_not_offered`, business offered); then the outbound
  flights of the day.
- Result `ok`: `leg: "outbound"`, the route said, the date, up to 4 options (`n`, `flight`,
  `departs`, `arrives`, `next_day`, `duration`, `part_of_day_said`, `fare_sar`, `seats_ok`,
  `mark`: `cheapest` on the cheapest), the travelers and cabin, `fare_basis_said`, `say`: "Say
  the day with its weekday first, in place of saying their request back, then these flights, at
  most three, each by its departure time and fare, the cheapest marked. Say once that fares are
  one way, per person. Then ask which one they want. Do not say flight numbers." (f27 p2's
  first listing named no day, and a bare day said next was heard as an hour.) With four
  options, the say asks for "options 1 to 3 in order, each by its departure time and fare, the
  cheapest marked, then that there is one more and its part of the day (part_of_day_said), never
  its time or its fare." A return listing (`return_listed`, `choose_flight`'s) opens "Say these
  flights" with no day, after the choice said back. When the caller heard another day's flights
  in this call (the draft's `shown.outbound` is of another day), the say (`relisted`) opens "Say
  the new day with its weekday first, then" and has "Do not say again that fares are one way,
  per person." in place of "Say once ..." (f04 and f25 said a corrected day's flights in the
  first listing's words). Then the draft's `shown.outbound` holds them, and its route, dates,
  travelers and cabin are the search's.
- **A span of days** (`depart` a `days` form, added 2026-11-17; `tools/overview.py`): after the
  city and route checks, before the round-trip gate, and writing nothing to the draft, status
  `days`: the span's `first` and `last` days, the route's daily departure times (`departs`), the
  days with no flight (`no_flight_days`), each day with its lowest fare in the cabin (`days`, the
  fare calendar's), the two cheapest marked; `say` (`days`, or `days_some` with days of no
  flight): "Say the span by its first and last days with their weekdays, then that we fly there
  every day of it at these times (departs; for three or four a day, how many and the first and
  last), then the two cheapest days (marked) with their fares, and ask which day they would like
  to leave. Do not list flights yet." Its card is the calendar of flights (3.4). A span past the
  window is a `date_problem`, a cabin not sold `cabin_not_offered`, a span with no flight
  `no_flights_that_day`.
- `no_flights_that_day`: the two nearest days with flights; `say`: "Say there is no flight that
  day and offer these days."
- `no_seats`: what is short, the other cabins with seats, the other flights that day; its `say`
  (and `no_seats_flight`'s) ends "Then wait for their answer; call change_trip only for a cabin
  the caller asks for." (the owner's live call: the cabin changed after a full flight, unasked).
- Card: the options (section 3.4).

**`choose_flight`**

- Description: "Pick the flight the caller chose for one leg, from the flights you listed. Pass
  their choice as they said it: its number in the list, the cheapest, the dearest, the earliest,
  the latest, the morning, afternoon or evening one, its departure time, or its fare."
- Arguments: `leg` (`outbound`, `return`); `choice` ("The caller's pick, as they said it; never
  a flight you worked out, nor the time or number of the flight it means, even one a tool
  already named: a part of the day goes as part_of_day, a comparison of when it leaves as
  earliest or latest, a comparison of fares as cheapest or dearest, a fare they said as fare,
  the only flight listed as its number.", `picks.py`'s `CHOICE`, compare_cabins' too), one of
  `{"pick": "number", "n": 1-4}`, `{"pick": "cheapest"}`, `{"pick": "dearest"}`,
  `{"pick": "earliest"}`, `{"pick": "latest"}`,
  `{"pick": "part_of_day", "part": "morning" | "afternoon" | "evening" | "night"}`,
  `{"pick": "time", "departs": "HH:MM"}`, `{"pick": "fare", "fare_sar": 1 or more}` (the last
  two kinds added 2026-11-17: «أغلى واحدة» had no kind, and a fare said went as a time or a
  number). The dearest is the highest fare among the options with a seat for every traveler
  (all of them when none has one), the first listed of two; a fare names the options at that
  fare in the draft's cabin, two of them `unclear_choice`, none every option listed. Each kind's description (its class docstring in
  `tools/picks.py`) says when it is the caller's: a number only for a number or an order word
  said, or for the only flight listed; the earliest or the latest for a pick by how early or
  late it leaves, never its number; a part of the day even when its time or number is known,
  with the part's hours; a time only for one the caller said. (f-dev-5 passed 13 of 37
  part-of-day picks, and 2 of 3 "latest" ones, as a time or a number; f10's "this one" after a
  one-flight listing went as a time or the cheapest.)
- Checks: a list was shown for that leg (`nothing_listed`, `say`: "Search first."); the choice
  matches exactly one shown option (`unclear_choice` with the options that match, each said by
  time and fare; or, when it matches none, every option listed with its count and first and
  last departure times, said as briefly as their listing, `unclear_choice_brief` for three or
  four, a full one as full, `_full`; compare_cabins' alike, listing.py's `unclear`); seats.
- Result `ok`: the chosen leg; for a round trip with the return not chosen, the return flights
  of the return day, listed as search lists them (`shown.return` set), `say`: "Say the choice
  back in a few words, then the return flights as their listing's say (returns.say) asks, and
  ask which one. Do not say again that fares are one way, per person."; when every leg is
  chosen, the trip whole with its total and `say`: "Call book_trip now, in this reply, even
  right after a read-back the caller declined or changed, and say nothing yourself: never ask
  whether to book or confirm it. The caller hears the trip read back and is asked to confirm
  it; that is the only question." (2026-11-17: after a declined read-back the model asked its
  own booking question, so the caller confirmed twice.) So the read-back is the one summary and
  the one gate: the caller hears the trip and its total once, and says yes once.
- Card: the return options, or the trip.

**`change_trip`**

- Description: "Change the trip the caller is planning: the number of travelers, the cabin,
  one way or round trip. For another day or city, call search_flights again."
- Arguments: `travelers` (1-9, optional), `cabin` (optional), `one_way` (bool, optional); at
  least one.
- Result (`tools/change.py`): what changed; the legs re-priced; a leg that lost its choice,
  the departure time of the flight it lost (`lost_departs`), and its options, listed as briefly
  as a day listing (`count`, `first_departs`, `last_departs`; says `changed_relist*` and
  `changed_lost*`, each with its brief and full variants, a full one said as full); the new
  total when every leg is chosen. `say` as `choose_flight`'s (so a complete trip goes straight to
  `book_trip`). Card: the leg listed again, in its segment, or the trip.

**`get_trip`**

- Description: "Read the trip planned so far: route, dates, travelers, cabin, the flights listed
  and chosen, the total, and what is still missing. Call it when the caller asks what they chose,
  or when you are unsure which flight they mean."
- No arguments. Result: the draft, `missing` (`destination`, `depart`, `return_date`,
  `outbound`, `return`), the total when complete. Card: the trip.

**`fare_calendar`**

- Description: "Find the cheapest days to fly a route, in a month or the 30 days from a date.
  Call it when the caller asks when it is cheapest, or is flexible on dates."
- Arguments: `destination`, `origin` (optional); `month` (1-12) or `from_date` (DateSpec);
  `cabin` (optional, no default shown: "The cabin the caller asked for at any point in this
  call; else leave it out."). Left out, the cabin is the call's draft's (economy until a search
  or a change names one); the calendar reads the draft and never writes it.
- Result `ok`: `days`, the cheapest seven days in date order, each with its date, weekday and
  fare (so every number the card shows is in the data); `cheapest`, the three cheapest of them
  marked for speech; the span's highest fare, so the talker can say "from 1,180 to 2,140
  riyals"; days with no flight left out and counted; `fare_basis_said`. `say`: "Say the three
  cheapest days with their fares, then ask which day suits them." Card: the seven days, the
  three marked.

**`compare_cabins`**

- Description: "Compare economy, business and first class for one listed flight. Pass the
  caller's pick as they said it: its number in the list, the cheapest, the dearest, the
  earliest, the latest, the morning, afternoon or evening one, its departure time, or its
  fare."
- Arguments: `leg`, `choice` (as `choose_flight`'s, described as its is: "The caller's pick, as
  they said it; never a flight you worked out, nor the time or number of the flight it means,
  ...").
- Result: each cabin offered on that flight: its fare, seats ok or not; first marked not
  offered on the A320neo, A321neo and A330-300; `say`: "Say each cabin's fare on this flight,
  one way, per person, and ask which cabin they want. Then wait for their answer; call
  change_trip only for a cabin the caller asked for." (f28 p3 asked, answered for the caller and
  changed the cabin.) Card: the three cabins.

**`traveler_profile`**

- Description: "Read the caller's travel profile: tier, home airport, preferred cabin, past
  trips and bookings made today, with counts already worked out. Call it for any question about
  their past trips, bookings or tier, and when they want the same trip as last time."
- Bound: `traveler` from `from_caller("attributes.traveler_id")`. No talker arguments.
- Result: the profile; the insights; each past trip and each booking with its route, dates,
  travelers, cabin, total and its `reference` (never said unless asked); `say`: "Answer from
  these counts. Say a past trip as one they flew, never as one you booked. Never read a booking
  reference unless the caller asks for it."
- **No `reports_on`.** The profile is called on the main flow and is full of six-digit
  references and 3-5 digit totals, so as status evidence it would let "I've booked it" pass
  beside a past reference with no booking made (D-081's status rule). A booking made in this
  call is in the record, which is the only evidence rule A needs here. Rule B still lets a
  reference be said when the profile's result holds it.

### 3.4 What each result shows on the page (`tools/cards.py`)

Each option is one of the card's rows (`CardRow`, L5): a title, a detail, a value and a mark
(`best`, `chosen`, `unavailable`); a card that lists options sends no steps. The page shows
each row's parts as text and maps its mark to a style and a word of its own (as built,
0224bf9 and 2a2488c).

**The ID rule on cards.** `clause_gate.shown` drops a card whose texts fail the output guard's
ID rule, and the rule reads numbers that stand next to each other with only marks between them
(`·`, `,`, `.`, `|`, `-`) as one group: "T2 401 · 787-9 · 2,450 SAR" reads as 40178792450, which
no result holds, so the card is dropped (checked with `check_ids` and the default
`GuardSettings`, `min_id_digits` 3). So:

- two numbers never stand next to each other with only marks between them: a word always sits
  between them ("flight T2 401 on a 787-9 for 2,450 SAR"); times are joined by "to" / «إلى», and
  colon-joined numbers (a time) are read alone;
- every result that carries a card puts the card's own texts in `ToolResult.evidence` (fixed
  airline data and computed values, never caller words), and its data holds every number the
  card shows (the calendar's seven days, not only the three said).

Each card names its segment of the page (`Card.slot`, D-110; added 2026-11-17 for the owner's
three segments): a leg's flights `outbound` or `return`, the trip `review`; the cabins and the
fare calendar name none.

| Result | Slot | Title (en / ar) | Rows |
| --- | --- | --- | --- |
| search (a day), choose (return list), change_trip (a leg listed again) | `outbound` / `return` | the leg, the route, the day and the cabin: "Outbound: Riyadh to London · Thu 17 Dec · economy" / «الذهاب: الرياض إلى لندن · الخميس ١٧ ديسمبر · الدرجة السياحية», "Return: London to Riyadh · Sun 20 Dec · economy" | one per option, at most four: title the times local at each end ("09:10 to 16:15", «٠٩:١٠ إلى ١٦:١٥», "next day" when it lands then), detail "7 h 5 min, nonstop, flight T2 401 on a 787-9", value "2,450 SAR"; the cheapest with seats marked best, one with no seat for every traveler unavailable; then the other leg's pick, when one is kept, as a row marked chosen (its title its times), which the page marks in that leg's segment |
| search (a span of days) | `outbound` | "Outbound: Riyadh to Paris · Sun 22 Nov to Sat 28 Nov · economy" | the calendar of flights: one row a day ("Sun 22 Nov", its lowest fare as its value), the two cheapest marked best, a day with no flight "No flight" / «لا رحلات», unavailable |
| choose (complete), get_trip, change_trip | `review` | "Your trip: Riyadh to London · round trip · economy" / «رحلتك: الرياض إلى لندن · رايح جاي · الدرجة السياحية» | each chosen leg (title its times, detail the leg and its day with its flight, "Outbound: Thu 17 Dec, 7 h 5 min, nonstop, flight T2 401 on a 787-9", value its fare, marked chosen), then "1 traveler in economy", then "Total" with "5,120 SAR" as its value |
| fare_calendar | none | "Cheapest days to Istanbul in January" | seven days, each "Wed 13 Jan" with "1,180 SAR" as its value, the three said marked best |
| compare_cabins | none | "Cabins on flight T2 401, Thu 17 Dec" | "Economy" with "2,450 SAR", "Business class", "First class"; the trip's cabin marked chosen; one full ("full") or not offered ("not offered on an A321neo") marked unavailable |
| traveler_profile | | none | (the page's "Your trips" shows bookings) |

(These strings were checked with `check_ids` against a result holding the same numbers: they
pass. The arrival time in the first row is an illustration.) Card text is the airline's fixed
data only, never caller words. A card is never needed: the reply says the same. The page shows
the marks with its own words: "Lowest fare" / «أقل سعر» (an outline tag), "Your pick" /
«اختيارك» (the only filled one), "Not available" / «غير متاح» (struck).

Tests (in A5 and A6): every card of every status, of every tool, in both languages, passes
`check_ids` with the default `GuardSettings` against its own result's evidence.

### 3.5 Failures said plainly (the demo's weakness 2)

Every `ToolError` message names what failed and what to say, and forbids reading it as nothing
found:

- search, calendar, cabins: "The flight search did not answer. Tell the caller you could not
  check flights just now and offer to try again in a moment. Do not say there are no flights or
  no seats."
- profile: "The travel profile did not load. Tell the caller you could not open their travel
  history just now. Do not say they have no trips or no bookings."
- a bad argument the library refuses is told back with its field named (invariant 4); the talker
  tries again or asks.

The instructions say it again (section 5), and run F holds it: f11, f12 and a held-out case.

### 3.6 Numbers, times and dates: what the talker writes, what the caller hears

**The talker writes digits.** The library's prompt says "Write every number in digits (3, 4521),
never in words" (`agent/prompt.py`). The output guard reads digits only: a number said in words
passes rule B unread, so an invented fare written as words would never be caught. So results
give machine values, the talker writes them in digits ("the 09:10 at 2450 riyals"), the guard
checks every fare, total and reference, and the speaking rules turn the digits into words after
the guard.

**The speaking rules say them by register.** Today the Arabic words are MSA's (TD-058), and
times and dates are read as written. L4 (section 9) is plan 010's row 1.8 for numbers, times,
dates and amounts, built with the track that owns `domain/text/` (Track D): Saudi, MSA and
English forms, chosen by the reply's register. Until L4 lands, the caller hears today's forms
(a risk, section 11).

**Lines rendered by code** (the read-back, `done`, `failed`, `unknown`) are not the talker's:
they keep their words, rendered by L4's functions (or, until L4 lands, by `said/numbers.py`
behind the same names). The forms they and L4 aim at:

| What | Saudi (`ar-SA`) | MSA (`ar`) | English |
| --- | --- | --- | --- |
| 09:10 | تسع وعشر دقايق الصبح | التاسعة وعشر دقائق صباحًا | nine ten in the morning |
| 16:00 | أربع العصر | الرابعة عصرًا | four in the afternoon |
| 21:30 | تسع ونص بالليل | التاسعة والنصف مساءً | nine thirty at night |
| 2026-12-17 | الخميس سبعطعش ديسمبر | الخميس السابع عشر من ديسمبر | Thursday the seventeenth of December |
| 7h05 | سبع ساعات وخمس دقايق | سبع ساعات وخمس دقائق | seven hours and five minutes |
| 2,450 SAR | ألفين وأربع مية وخمسين ريال | ألفان وأربعمئة وخمسون ريالًا | two thousand four hundred fifty riyals |
| 1 traveler / 2 / 3 | لك أنت / لك ولشخص ثاني / لثلاثة أشخاص | لك وحدك / لشخصين / لثلاثة أشخاص | for you / for two travelers / for three travelers |

Parts of day: Saudi «الفجر» 00:00-04:59, «الصبح» 05:00-11:59, «الظهر» 12:00-14:59, «العصر»
15:00-17:59, «المغرب» 18:00-18:59, «بالليل» 19:00-23:59. English "at night", "in the morning",
"in the afternoon", "in the evening" (18:00-21:59). A native Saudi speaker checks the forms once
(TD-058's check), the owner or a tester, 15 minutes, before the first demo.

## 4. The booking action (`booking/`)

### 4.1 Its draft

`book_trip` takes **no field from the talker**: the talker calls it with `{}`. Its validate reads
the call's trip draft and fills the draft's fields, which the talker never sees:

- fields hidden from the schema with pydantic's `SkipJsonSchema`, each with a default: the legs
  (`outbound_flight`, `outbound_date`, `return_flight`, `return_date`), `one_way`, `travelers`,
  `cabin` (a `Literal` with `Spoken` labels), `total_sar`, and the said parts of the read-back in
  each language (`trip_kind_*`, `route_*`, `outbound_*`, `return_*`, `party_*`, `total_*`);
- `validate` always overwrites every one of them from the trip draft, so a value the talker
  sends (it may guess a field name) never survives. **The first test of the booking step proves
  it**, and proves `tool_schema()` shows no field. If the library's checks refuse such a draft,
  stop and take L2 (section 9) instead; do not work around it.

`validate` refuses, with a `ToolError` the talker reads: a leg not chosen ("The return flight is
not chosen yet. Ask which one they want."), seats gone, a date passed.

**`max_per_call` 1, the library's default.** One booking per call. Two reasons, both checked in
the code: TD-143(3) is open (each read-back's request ID holds its reply number, so with a cap
above 1 one request confirmed in two read-backs is written twice), and after a timeout whose
lookup finds nothing the row is `flagged`, which the cap counts, so a cap of 2 would let a
second confirmed write go out with a new request ID: in `late` mode the mock really books twice
(invariant 6's intent). With 1, the cap refuses the second write in code. A refused booking
(`ActionRejected`, row `rejected`) and a dropped read-back write nothing the cap counts
(`NOT_WRITTEN`), so the caller can still change the trip and try again. Raise the cap only after
TD-143(3) is fixed and the owner asks for two bookings in one call.

`timeout_s` 20 (the library's).

`execute` books from the draft's own fields (what was read back), never from the live trip
draft: `airline.bookings.create(...)` with `ctx.request_id` as the idempotency key and the
traveler from the caller. A refusal is `ActionRejected` (said as `failed`); the store's timeout
is any other error, so the runtime looks it up (`@book_trip.lookup`, by request id) and says
`unknown` when it finds nothing (invariant 6). The result, `BookingMade`: `reference`, and the
city and dates said in each language for `done`.

**`ActionSafetySuite` on `book_trip`.** Each suite case is a fresh `TextCall` that runs nothing
before the case (TD-142(5)), and its default caller is a made-up one with no `traveler_id`. So
the suite's subclass builds the action over a **test `TripBook` that returns a complete, priced
trip for any call id** (built from the mock airline, so validate fills every hidden field), and
sets `caller = Caller(subject="owner", attributes={"traveler_id": "T-0001"})`. The sample draft
is `BookingDraft()` (all defaults; validate overwrites them). The general fix, a `prepare(call)`
step, stays TD-142(5)'s.

### 4.2 Its words (`booking/lines.py`)

The read-back's summary is fixed words with the draft's said parts. It always says the trip's
kind, so a one-way trip is never booked on a read-back that did not name it, and every value
booked: the party, the cabin, the kind, the route, each leg's day and time, and the total. Since
2026-11-17 it says no word that holds no value: no lead verb («بحجز», «سأحجز», "I'll book"), the
return's city not said again (the route said it), the return's month only when it is not the
outbound's, and "Total" for "The total is". Measured on the owner's three call shapes, the
summary's words went from 24 to 23 (Saudi one way, Dubai), 32 to 28 (Saudi round trip, Jeddah)
and 45 to 38 (English round trip, London). Its closing question and its own ask-again line hold
the action's own send word, so the library's «أسجل الطلب؟» / "Shall I go ahead?" is never said
for a booking. Examples below are for Riyadh to London, out Thursday
17 December at 9:10, back Sunday 20 December at 16:00 from London, one traveler, economy, 5,120
riyals (the figures are illustrations; the airline computes the real ones).

| | Saudi (`ar-SA`) | MSA (`ar`) | English |
| --- | --- | --- | --- |
| summary template | {party_ar_sa} على {cabin}، {trip_kind_ar_sa}: {route_ar_sa}، {outbound_ar_sa}{return_ar_sa}. المجموع {total_ar_sa}. | {party_ar} في {cabin}، {trip_kind_ar}: {route_ar}، {outbound_ar}{return_ar}. المجموع {total_ar}. | For {party_en} in {cabin}, {trip_kind_en}: {route_en}, {outbound_en}{return_en}. Total {total_en}. |
| `trip_kind`, round trip | رايح جاي | ذهاب وعودة | round trip |
| `trip_kind`, one way | رايح بس | ذهاب فقط | one way |
| as said | لك أنت على الدرجة السياحية، رايح جاي: من الرياض للندن، الخميس سبعطعش ديسمبر تطلع تسع وعشر دقايق الصبح، والرجعة الأحد عشرين تطلع أربع العصر. المجموع خمسة آلاف ومية وعشرين ريال. | لك وحدك في الدرجة السياحية، ذهاب وعودة: من الرياض إلى لندن، يوم الخميس السابع عشر من ديسمبر تقلع التاسعة وعشر دقائق صباحًا، والعودة يوم الأحد العشرين تقلع الرابعة عصرًا. المجموع خمسة آلاف ومئة وعشرون ريالًا. | For you in economy, round trip: Riyadh to London, Thursday the seventeenth of December at nine ten in the morning, back on Sunday the twentieth at four in the afternoon. Total five thousand one hundred twenty riyals. |
| closing question | تبيني أحجزها؟ | هل أحجزها لك؟ | Shall I book it? |
| ask-again | المعذرة، ما وضح لي ردك. تبيني أحجزها؟ | عذرًا، لم يتضح لي ردك. هل أحجزها لك؟ | Sorry, I didn't catch that. Shall I book it? |
| send words (`ar`, `en`) | احجزها، أحجزها، أكد، أكدها، أكد الحجز، احجز | the same | book it, confirm, confirm it |
| cabin labels | الدرجة السياحية، درجة رجال الأعمال، الدرجة الأولى | the same | economy, business class, first class |
| `done` | تم، رحلتك {city_ar_sa} {when_ar_sa} جاهزة. | تم، رحلتك {city_ar} {when_ar} جاهزة. | Done. Your trip {city_en}, {when_en}, is all set. |
| `sending` | جاري الحجز الحين. | جارٍ الحجز الآن. | Making the booking now. |
| `failed` | للأسف نظام الحجز رفض الطلب، فما صار أي حجز. | للأسف رفض نظام الحجز الطلب، فلم يُجرَ أي حجز. | Unfortunately the booking system turned it down, so no booking was made. |
| `unknown` | ما قدرت أتأكد إذا الحجز وصل، فلا تعتمد عليه الحين. | لم أتمكن من التأكد من وصول الحجز، فلا تعتمد عليه الآن. | I can't tell whether the booking went through, so please don't count on it yet. |
| `declined` | ما سويت أي حجز. إذا تبي ترجع له، قل لي. | لم أُجرِ أي حجز. إن أردت العودة إليه فأخبرني. | No booking was made. Tell me if you'd like to come back to it. |

`{return_*}` is "" for a one-way trip (the trip kind says "one way"), or starts with its own
«، والرجعة» / ", back on", its day said without its month when the month is the outbound's
(`speak_date(..., month=False)`). A reference is never in `done`: the caller hears it only when they
ask, from a result that holds it, digit by digit (six digits are an ID to the speaking rules).

**Claims** (`Claims`), blocked by the guard unless the record holds `book_trip`. Only phrases
that cannot sit in a negative, since the guard's negation rule is Arabic only ("The English
defaults hold no negation to begin with", `domain/claims.py`): a bare "is booked" or "has been
booked" would match inside the talker's honest "Okay, nothing is booked" after a plain no (the
library speaks no `declined` line then, `domain/action_lines.py`), and the guard would replace
the truth with its fixed phrase.

- Saudi: «حجزت لك», «حجزتها لك», «تم الحجز», «تم حجز», «انحجزت», «أكدت لك الحجز», «حجزك مؤكد».
- MSA: «حجزت لك», «تم الحجز», «تم تأكيد الحجز».
- English: "I've booked", "I have booked", "I booked", "you're booked", "you are booked", "your
  trip is booked", "your flight is booked", "your trip has been booked", "your booking is
  confirmed", "booking confirmed", "reservation is confirmed".

No reference phrase is a claim ("your booking reference is", «رقم حجزك» are left out): rule B
already lets a reference be said only when a result of this call holds it.

**The lines' rules**, held by a test as Ole5's `test_lines.py` holds them, run on the final lines
of the table above: no line but the closing question and the ask-again holds a stop, wait,
repeat, listening, yes or send word of the presets or the booking's own (so no «تمام», «أوكي», "okay", «لحظة», "one moment", "book it" in
another line); no line holds a claim phrase; every line is one line of plain words; every
language the agent speaks is covered.

**The guard's tests** (in the booking step), with an empty record:

- "Nothing is booked.", "No booking was made.", "Okay, nothing is booked yet." pass, and «ما تم
  الحجز», «لم يتم الحجز», «ما حجزت لك شي» pass;
- each claim phrase above is blocked;
- adversarial, after `traveler_profile` and no `book_trip`: "482913. I've booked it." and
  «482913، حجزت لك» in one reply are blocked (rule A), and "Your last Dubai trip was 482913"
  passes (rule B, the profile holds it).

### 4.3 The yes rule, the receipt and the outcome

All the library's, unchanged: the read-back's summary must play whole (the receipt), then the
caller's own heard words after it: a yes on the lists, or the chat model's judgement of words the
lists leave unplaced (`ask_on_unlisted_answers=True`, as Ole5's talker with its tickets). Over
the closing question only a yes with a send word («إي احجزها», "yes, book it") or the model's
explicit go-ahead ("go for it") counts; a bare «إي» there is asked again. "Yes, but two people"
is a change: the read-back is dropped, the talker calls `change_trip`, then `book_trip` again,
and a new read-back plays. The outcome line (`done`, `failed`, `unknown`) is the system's.

`ask_on_uncertain_overlaps=True`, as Ole5's.

## 5. The persona and the instructions

### 5.1 The persona (`persona.py`, settings)

**The names are the owner's to choose** (Q23 (c), "name later"). Before step A8, the lead puts
these to the owner, each first checked against real airlines and registered marks:

- the persona: **Saad** («سعد»), **Fahad** («فهد»), **Nawaf** («نواف»): short, male, said cleanly by
  both voices;
- the airline: **T2 Air** («طيران تي تو», our own company's name), **Sahab Air** («طيران سحاب»,
  cloud), **Najm Air** («طيران نجم», star).

Until the owner picks, the defaults are Saad and T2 Air, as placeholders.

| Setting | Default | Notes |
| --- | --- | --- |
| `FLIGHT_VOICE_PERSONA_NAME_EN` / `_AR` | Saad / سعد | the owner's pick |
| `FLIGHT_VOICE_AIRLINE_NAME_EN` / `_AR` | T2 Air / طيران تي تو | the owner's pick |
| `FLIGHT_VOICE_AIRLINE_CODE` | T2 | on cards and flight numbers only, never spoken unless asked |
| `FLIGHT_VOICE_AIRLINE_CODE_SAID_EN` / `_AR` | tee two / تي تو | the pronounce entry for the code |

**Everything that holds a name is built from the settings** in `persona.py`, with
`string.Template` (`$persona`, `$airline`, `$traveler`): the greetings, the instructions, the
pronounce entry (`AIRLINE_CODE` → its said form in each language), and the vocabulary entry
(the airline's English name). Nothing in `agent.py` holds a name. At settings load, the lines'
rule (no command, yes, send or claim word) runs on the rendered greetings and progress lines;
a name that breaks it is refused with a `ConfigurationError` that names the setting, never its
value. Tests read the names from settings, so the owner's pick changes no test, and one test
builds the agent with a non-default name and checks the greeting, the pronounce map and the
vocabulary all hold it.

The voice: the owner's pick by ear of 2026-11-17 (D-114), ElevenLabs' `eleven_v4_turbo` in the
voice `nhJWWCFdNdusuVUT3x19` for Saudi, MSA and English alike, one voice for Saad: the library's
default; Groq's Orpheus, `abdullah` and `troy`, the fallback with `T2V_TTS__PROVIDER=groq`. The persona says it is the airline's voice
assistant (Q14 may change how it names itself).

Greeting templates:

- Saudi, in Riyadh's Najdi (the owner's ask of 2026-11-17): «هلا والله $traveler، معك $persona
  من $airline. وين ودّك تسافر؟» (hala wallah Khalid, Saad here, from the airline. Where would
  you like to travel?)
- English: "Hi $traveler, this is $persona, $airline's voice assistant. Where would you like to
  fly?"

Progress lines (plan 010's 1.15), each said as its search starts (`find_flights`,
`search_flights`, the fare calendar; `compare_cabins` keeps the library's 2.6 s), in one of a few
short wordings, never the one the call said last, then 0.1 s of silence before the answer:
`searching`: «أشوف لك.», «أدوّر لك الحين.», «خلني أشوف لك.» / "Checking now.", "Let me look.",
"Let me check.", "Looking that up."; `fares` (the calendar's own key): «أشوف لك الأسعار.»,
«أشيّك على الأسعار.» / "Checking the fares.", "Looking at fares.", "Let me check prices." Drafts
for the owner's pick, rendered in Saad's voice.

`VOCABULARY` (the Whisper prompt's terms): Riyadh, Jeddah, Dubai, Doha, Cairo, Istanbul, London,
Heathrow, Paris, Mumbai, Singapore, economy, business, and the airline's English name from
settings.

### 5.2 The instructions

Written in English for both files (models follow English rules more reliably: `agent/prompt.py`),
the Arabic file with Saudi examples, as Ole5's are. Filled at build with the persona, the airline
and the traveler (`string.Template`, so a brace in the text is safe). Both files hold the same
sections; `ar-SA.md` adds the register rule and the examples in brackets below.

```
You are $persona, the voice assistant of $airline, on a call with $traveler, a $tier member,
who wants to plan or book a flight. $airline flies between Riyadh and nine cities: Jeddah,
Dubai, Doha, Cairo, Istanbul, London, Paris, Mumbai and Singapore. Every flight starts or ends
in Riyadh.

How you talk:
- [en] Plain, warm spoken English. If the caller speaks Arabic, answer in their Arabic: Saudi,
  or Modern Standard Arabic for a caller who speaks it.
  [ar-SA] Answer in the caller's Arabic, in the Saudi spoken register, as a friendly Saudi agent
  talks on the phone («وين ودك تسافر؟», «متى ودك ترجع؟»; "now" is «الحين», never «الآن»).
  Address the caller in the masculine. If the caller speaks Modern Standard Arabic, answer in it
  («إلى أين تودّ السفر؟», «متى تودّ العودة؟», «الآن»), never with «ودك», «وين» or «الحين», and say
  a tool's `*_said_msa` words in place of its `*_said` ones. Your greeting is in Saudi; once the
  caller speaks MSA, every reply is in MSA, from your first one. If they speak English, answer
  in English.
- One to three short sentences a turn. One question at a time, at the end of the turn.
- Say a day's flights briefly: one or two each by its departure time and its fare ("the 09:10
  at 2450 riyals"); three or four by how many there are, the first and last departure times
  and the cheapest by its time and fare, and the others only when the caller asks. Say once a
  call that fares are one way, per person. Never say that anything is on a screen.
- Write times and fares in digits, exactly as the tools give them. Say a date by its weekday,
  its day in digits and its month's full name ("Friday, March 5" [«الجمعة 5 مارس»]); never
  shorten a month or a weekday.
- Never say a flight number, an aircraft, an airport code or a booking reference unless the
  caller asks for it.
- Never mention tools, searches, systems, data or anything in square brackets.

Planning a trip:
- You already know who the caller is: never ask their name, email, phone or passport.
- Find out, one question at a time: where they are going, when they leave [«متى ودك تسافر؟», to
  an MSA caller «متى تودّ السفر؟»], and when they come back. Assume Riyadh as the start, a round
  trip, economy and one traveler; never ask for them and never say that you assumed them. Ask
  "When would you like to come back?" [«متى ودك ترجع؟», to an MSA caller «متى تودّ العودة؟»],
  never whether it is one way. Change any of them when the caller says so.
- Pass every date as a date form, as the caller said it ("next Thursday" is the coming Thursday,
  "the 14th" a day of the month, "a week later" seven nights after leaving, "back four days
  later" [«أرجع بعد أربع أيام»] four nights after leaving, "leave in four days" [«أسافر بعد أربع
  أيام»] four days from today). Never work out a date yourself. Say back the date the tool
  gives, with its weekday.
- Once the caller has said where they go and the day they leave, and for a round trip the day
  they come back, call search_flights in that same reply, with no question first: never ask
  them to confirm a day they said or anything you assume. Until then ask only for what is
  missing, and never fill in a day they did not say.
- When the caller asks what flies over days and names no single day ("anything during the
  weekend", "the soonest you have" [«وش عندكم آخر الأسبوع», «أقرب شي عندكم»]), call
  search_flights at once with that span as the day they leave, before asking when they come
  back, and never pick a day for them.
- When the caller picks ("the lowest fare", "the priciest one", "option three", "the afternoon
  one", "the last flight out", "the one for 1250 riyals" [«أرخص وحدة», «اللي سعرها أعلى», «رقم
  ثلاثة», «اللي الظهر», «آخر وحدة تطلع», «اللي بـ 980», to an MSA caller «الرحلة الليلية»]),
  call choose_flight with their pick (its result lists the return flights); never guess which
  flight it is. Pass a pick in the kind the caller said it, to choose_flight and compare_cabins
  alike: a part of the day as its part, a comparison of when it leaves as the earliest or the
  latest, a comparison of fares as the cheapest or the dearest, a fare they said as its fare, a
  place in the list only for a number or an order word they said or for the only flight listed,
  and a time only for a time they said. Never turn a pick into the
  time or the number of the flight you think it is, even one a tool already named.
- Search again when they change the day or the city. A number said alone as a correction after
  a listing ("no, the 19th" [«لا، تسعطعش»]) is a new day. Once flights are listed, call
  change_trip when they change the cabin, the number of travelers or one way, and never search
  again for that or for a pick.
- Say a total only as a tool gives it.
- Never invent a flight, a time, a seat, a fare or a past trip. Say only what a tool gave in this
  call.
- For a question about their past trips or bookings, or for the same trip as last time, call
  traveler_profile and answer from its counts. Say a past trip as one they flew, never as one
  you booked. For the same trip, keep its city, travelers and cabin and ask when they leave
  [«متى ودك تسافر؟», to an MSA caller «متى تودّ السفر؟»]: its dates have passed, so never offer
  them or search with them.

Booking:
- When every flight of the trip is chosen, call book_trip at once, in that same reply, even
  right after a read-back the caller declined or changed, and say nothing more in that reply:
  the caller hears the whole trip read back, with its total, and is asked to confirm it. Do not
  sum the trip up yourself first, and never ask yourself whether to book or confirm it: the
  read-back is the only question.
- A trip is booked only after the caller's spoken yes to that read-back. Never say a trip is
  booked unless the system said so in this call. This line takes no payment: never ask for card
  details; if asked, say payment is not part of this call.
- If the caller says no, answer in your own words. If they change something, make the change;
  the trip is read back again.
- One booking per call. If the system could not confirm a booking, do not book again. Say you
  cannot tell whether it went through, and never say that it did or did not. If asked to book
  again, say it cannot be booked again in this call, with no offer to try again.
- Say a booking reference only when the caller asks for it: get it from traveler_profile (a
  booking made in this call is the first in its `booked`) and say it as its six digits; never
  say you do not have it before you call it.

When something fails:
- When a tool fails, say plainly that you could not check that just now, and offer to try again
  [«ما قدرت أشيك الحين، تبي أجرب مرة ثانية؟»]. A failure never means there are no flights, no
  seats or no past trips: never say so after one.
- When there is truly no flight that day or no seat, say so and offer the days or cabins the
  tool gives, and change nothing until the caller picks one.

What you cannot do:
- Other airlines, connections between two other cities, hotels, cars, visas, seats on the
  plane, meals, baggage or changes to a past booking: say in one sentence that you cannot do it
  on this line, and come back to the trip.
```

`VERSION` in `agent.py` stamps every trace ("2026-11-17.1" at the first build, "2026-11-17.3"
with run F's second round of text fixes, "2026-11-17.4" with the owner's live-test round), changed with each change to the instructions, the
tools' texts or the lines.

## 6. The page

### 6.1 Its layout (our own design, the demo's layout learnt)

Served by the app at `http://127.0.0.1:7862/`, light by default, dark on the system's setting,
`lang="ar" dir="rtl"` for Arabic and `lang="en" dir="ltr"` for English, mirrored by CSS logical
properties only (`margin-inline-start`, never `left`). Phone width works: a 16 px gutter, no
side scroll. Every text is our own, in `texts.js`; the Arabic is written fresh, never translated
from the demo's page.

```
header:  [our mark] <airline>      Your trips      Khalid · Gold      Start over      العربية | English
main:    Where are you flying, Khalid?               («وين ناوي تسافر يا خالد؟»)
         ( orb )  <persona> · <airline> voice assistant
         [ Start a call ]  [ End ]   state line: Listening / Thinking / Speaking / Waiting for your yes
         You could say:  "Back to Dubai"   "Cheapest days to London"   "Business to Paris"
         Your trip, step by step: three segments, each filled in place by its card
           outbound: the outbound flights, or the calendar of flights for a span of days
           return:   the return flights (none for a one-way trip)
           review:   the trip for confirmation; "Waiting for your yes", then "Booked · Reference …"
         then one card of no segment (the cabins of a flight, the cheapest days)
         Show conversation (collapsed): the captions
         Options (collapsed): access code, "record this call" box, push to talk
panel:   Your trips: each booking (route, dates, travelers, cabin, fare, reference shown as text),
         a filter by reference (local, no request), newest first
```

- **The orb** follows `state` events today (listening, thinking, speaking, confirming), each a
  look and a word. Phase 3's `level` event drives it by the voices once it lands.
- **The "You could say" chips** are text, not buttons: the client has no typed text into the
  call, by design (`t2v/1` has no such message, which closes the demo's fake-event weakness).
  They come from `GET /api/profile` (the most visited city, a cheapest-days ask, a business ask).
- **Cards** mirror what was said and are never needed. Each card's text is set with
  `textContent`, each line `dir="auto"`, the airline's mark as an image file. **Three segments**
  (the owner's ruling of 2026-11-17; `cards.js`): each card goes in the segment its `slot` names
  (3.4), a new one in place of the last. A leg's card never marks its own flights as picked: a
  row it marks chosen is the other leg's kept pick, which the page marks in that leg's segment in
  place of the row with its title (the flight's times); the review card's chosen rows mark both
  legs. So after the outbound pick the outbound segment marks it (the page marks it from the
  return card, the simpler of the two ways: no tool sends a second card), and a pick a change
  drops is no longer marked, since each card says the picks anew. An outbound card that keeps
  no return pick is a new search and clears the return segment; every leg card clears the review
  and the extra card; a review card that no longer holds the return's pick, or one of the whole
  trip (its total) with one leg picked (the trip made one way, before or after a return pick),
  clears the return segment, so a one-way trip shows none. The review segment's status line
  reads "Waiting for your yes" / «ننتظر موافقتك» from when the whole trip's review card comes,
  so while the read-back plays (the call need never show `confirming`: a yes held over the
  summary books with no state between), then "Booked · Reference …" / «تم الحجز · رقم الحجز …»
  once "Your trips", loaded at the call's start and again at each state after that card or a
  read-back, holds a booking it did not (`bookings.js`'s `Made`; none when the list did not
  load at the start). A leg's card after it forgets that booking, so a later trip of the call
  never shows it.
- **The language toggle** sets the call's starting language (`VoiceClient.start({language})`)
  and the page's texts and direction. Mid-call, the caller switches by voice (plan 010's 2.5).
- **"Your trips"** refreshes when a call starts and ends, after a read-back until the booking
  is found, and every 10 s while open. **"Start over"** asks
  "Clear the trips booked in this demo?" in the page's language, then `POST /api/demo/reset`.
- **The access code** is typed once and kept in a JavaScript variable for the page's life, never
  in storage (a decision the owner may change).
- No manual search form, no "select" button: the call is the product (D-075).

**`test_own_words.py`**: the page's texts (`texts.js`, `index.html`), the tool descriptions and
`say` strings, the greetings and the instructions hold none of the demo's strings, case-blind:
"Where to,", "again?", "Best fare", "Reset demo", "My bookings", "Show chat", "Start a
conversation", "Explore flights", "Select flight", "Flexible dates", and the demo persona's name.

### 6.2 Its routes (`server.py`, `routes.py`)

| Route | What | Guard |
| --- | --- | --- |
| `GET /`, `/app.js`, `/cards.js`, `/bookings.js`, `/texts.js`, `/app.css`, `/mark.svg` | the page's files | L1's page headers: CSP `default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors <website or 'none'>`, nosniff, no referrer, microphone for this origin |
| `POST /token` | a join token for the access code (L1's route), the caller the demo traveler | L1's guard (constant-time compare, slow-down, close after 20 wrong an hour, `FLIGHT_VOICE_TOKENS_PER_DAY` a day, 50 by default) |
| `GET /api/profile` | first name, tier, chips in both languages | same origin; no secret; fictional data |
| `GET /api/bookings` | the traveler's bookings | loopback clients only (404 else), as Ole5's `/tickets` |
| `POST /api/demo/reset` | the bookings back to the seed | loopback only, `Content-Type: application/json` required (so a cross-site form cannot post it), body `{}` at most 64 bytes |
| `/voice/...` | the library's router (join, offer, the client at `/voice/client/1/t2v-client.js`) | the library's |

Fifty tokens a day, not Ole5's ten: this is the agent shown and worked on (demos, live calls by
agents with the fake-microphone rig, F.4's recordings, tester days), one token per call.

`settings.py` adds, beside the persona's and `FLIGHT_VOICE_TODAY`: `FLIGHT_VOICE_ACCESS_CODE`
(required, at least 16 characters), `FLIGHT_VOICE_WEBSITE_ORIGIN`, `FLIGHT_VOICE_TOKENS_PER_DAY`,
`FLIGHT_VOICE_BOOKING_MODE`, `FLIGHT_VOICE_BOOKING_LOOKUP`, `FLIGHT_VOICE_SEARCH_MODE`,
`FLIGHT_VOICE_PROFILE_MODE`, `FLIGHT_VOICE_SLOW_S`. Its loader also:

- **always** sets the runtime's `storage.var_dir` to `<storage.var_dir>/flight`, whatever sets
  the base (the default, or `T2V_STORAGE__VAR_DIR` in `.env`): its own used tokens, outbox,
  clause cache and lock, apart from Ole5's. The runtime's lock allows one process per
  `storage.var_dir` (`api/lockfile.py`), and both servers start with `--env-file .env`, so a
  shared folder would refuse whichever server starts second. A test sets
  `T2V_STORAGE__VAR_DIR` and checks the flight folder nests under it;
- sets `limits.actions_per_caller_per_day` to 50 unless the environment sets it (a demo day
  books more than the default 20);
- turns on `guard.question_stop_drops_calls` (a reply the question limit stopped drops its
  request's tool calls unrun, so the question ends the turn) and `guard.drop_stage_notes` (a stage
  note or a tag the model writes is a leak of its reasoning: nothing of that request is said from
  it on, and none of its tools runs), and sets `llm.max_requests_per_turn` to 4 (a refused
  booking's next pick and its read-back fit in one turn), each unless the environment sets it; the
  library's defaults keep each off and 3 (run F's round 2: f27's search on a day nobody said, f10's
  spoken stage notes, f26's spoken book_trip tag);
- under `env` dev, names the demo traveler the dev caller, as Ole5's names its customer.

### 6.3 What it needs from the library

Today's client already gives `state`, `caption`, `card`, `notice`, `ended`, `duck`, `unduck`,
`volume`. The flight cards send option rows (L5); the page reads `rows` when present and `steps`
otherwise.

## 7. The measurement

### 7.1 Run F: scripted flight calls (the plan's main set)

Played through the library's `TextCall` on the system clock with the real talker
(`gpt-oss-120b` at medium by default, D-074), each scenario three times, against a new airline
and `TripBook` per play, with the scenario's modes and today pinned to 2026-11-16. Deterministic
checks only: the mock airline is exact, so every fact is checked in code, and no judge is needed
for the first version (no spend on a judge, no waiting for the trusted check, 0.5).

**A scenario** (`evals/calls/*.toml`): `id`, `split` (`dev` or `held-out`), `language`
(`ar-SA`, `ar`, `en`), `kind`, `notes`, `needs` (capabilities it waits for, from a closed list in
`evals/scenarios.py`, each with a docstring: today only `language_switch`, the caller switching
language mid-call; skipped and reported until it lands), `modes` (`search`, `profile`,
`booking`, `lookup`), `today` (default 2026-11-16), and `[[turns]]`. Code never reads the plan;
plan 010 records which row provides each capability (2.5 provides `language_switch`).

A turn is either `says` (the caller's words, with `when`: unset, `agent_speaking`,
`tool_running`, `read_back`, `closing_question`, and `after_s`) or `stop = true` with `at` (a
point of the reply, mapped to `TextCall.user(..., at=...)`'s point, then `TextCall.stop()`), and
its expectations:

- `calls`: tool names the reply called, in order (`["search_flights"]`), or `[]` for none;
- `args`: values the call held, resolved (`destination = "LHR"`, `depart = "2026-11-19"`,
  `return_date = "2026-11-22"`, `pick = "cheapest"`, `cabin = "economy"`);
- `outcome`: `read_back`, `asked_again`, `done`, `failed`, `unknown`, `declined`, `none`;
- `read_back`: `{outbound = "T2 401@2026-11-19", return = "T2 404@2026-11-22", one_way = false,
  travelers = 1, cabin = "economy"}`, the total computed from the airline in the check, never
  written in the file, so a fare change never breaks a scenario;
- `said_any`: keyword groups, each a list of variants in both scripts ("couldn't", «ما قدرت»;
  "per person", «للشخص»); `said_none`: words that must not be said ("no trips", «ما سافرت»,
  "search_flights", a reference's digits unless asked);
- `language` (held by script and, for Arabic, by register: `saudi` or `msa`; amended 2026-11-17
  before any result, rule F's: a Saudi reply says no form only MSA says, an MSA one no Saudi form,
  the caller's list of `register_of` or the agent's own, `evals/spoken.py`, since `register_of`
  alone, which reads the caller's words, failed the Saudi forms of 5.2);
- `notice`, on every turn (amended 2026-11-17, rule F's): no failure notice heard (the error or
  cut-off line) and no clause the guard blocked, which f13 below asks;
- `stage_note`, on every turn (amended 2026-11-17 before any later result, rule F's): nothing the
  caller heard holds a stage note or markup: a parenthesis or bracket holding a Latin letter in a
  reply in Arabic script, one that opens a stage word in any language and case (the guard's closed
  list: Waiting, Awaiting, Wait for, Pause, Silence, No output, No reply, No response, No further,
  No answer, Listening, Thinking, «انتظار»), or a "<" that opens a tag; `evals/spoken.py`, in its
  own code, never the guard's rule, since f-dev-5's callers heard «…(Waiting for user response)…»
  and `<action tool="book_trip"/>` and no check failed them on its own;
- `max_words` (45 by default), `max_options` (3: how many listed options' departure times the
  reply says, digits normalized; amended 2026-11-17 before any result, rule F's: a brief listing
  says at most three of them, the first, the last and the cheapest, which `max_options` holds
  as before; a full flight said as full is one more when it is none of them, and a span's
  overview says the route's daily times, so a turn on a route with four a day sets
  `max_options = 4`);
- `asks_repeat` (true when the caller asks to hear something again: the repeat check is off);
- `repeat_of_cut` (true on the turn after a `stop`: L's cut-repeat check runs).

`said_any` for the fare's basis (f01, f02, f03, f05, f15, f24) is held on the first listing's
turn only, where the basis is still said once a call; no turn checks it on a return listing,
which no longer says it (amended 2026-11-17, rule F's, the brief listing). `args` reads a span
of days as `span` and a fare pick's `fare_sar`.

**L's checks, per turn** (plan 010's L, the same definitions, from L8's functions): no identical
reply and no near repeat (the same first clause, or a token overlap of 0.8 or more with an
earlier reply) unless the turn `asks_repeat` or the reply is a read-back said again (a brief
relisting of another day shares its frame, "four flights, from ... to ..., the cheapest ...", with
the first listing, and is still held to it, amended 2026-11-17 before any result); after a
`stop` cut a reply at about 10%, the `repeat_of_cut` turn's reply shares 60% or more of its
tokens with the cut reply's whole text; a detail given early (travelers, cabin, a date) is still
used late, checked by `args` and `read_back` on the late turn; the reply in the call's language.

**The play's checks**: bookings made (`booked = 1`, with its legs), none for anyone else, no
reference said unless a turn asks, the turn after the last choice calls `book_trip` with no
summary of its own before the read-back, `TextCall.violations` empty (rules A to C and the yes
rule: zero in every play is the hard constraint), each turn's checks.

**Kept rule**: a scenario passes when at least 2 of its 3 plays hold every check; a change to
the library or the app is kept when no dev scenario that passed before fails, the targeted ones
pass, and violations are zero in every play; for a target among L's checks, plan 010's L rule
(all three plays). Held-out is read once per milestone, with `--split held-out` named.

**Registered before any result.** Before step A10 (the scenarios), the lead writes a dated
amendment of plan 010: its measurement section gains rule **F** (run F: its data, the kept rule
above, its held-out read among M9's reads, so eight in all), and F.3's text says run F's
machinery in place of "run S and run A scenarios". No run F result is read before it.

### 7.2 The scenarios

Dev (written now, before any run). Each line: id, language, what it tests.

| id | lang | what |
| --- | --- | --- |
| f01_round_trip_saudi | ar-SA | «أبي أروح لندن الخميس الجاي وأرجع الأحد اللي بعده» → LHR 11-19, back 11-22; fares said once as per person; «حقت الصبح»; return «الأخيرة» → book_trip at once, read-back «رايح جاي»; «إي احجزها» → done |
| f02_one_way_english | en | "a one-way to Dubai tomorrow morning" → DXB 11-17 one way; "the earliest" → book_trip at once, read-back holds "one way"; "yes, book it" → done |
| f03_round_trip_msa | ar | «أريد السفر إلى القاهرة في العاشر من ديسمبر والعودة بعد أسبوع» → CAI 12-10, back 12-17; MSA replies |
| f04_date_correction_saudi | ar-SA | «جدة يوم ثلطعش ديسمبر» then «لا لا، أربعطعش» → search again, depart 12-14 |
| f05_cheaper_one_english | en | London next Thursday, back Sunday; "per person" said on the first listing; "the cheaper one" → pick cheapest, the read-back holds it |
| f06_cabin_change_saudi | ar-SA | Paris in business, then «لا خلها سياحي» → change_trip economy; read-back economy |
| f07_cheapest_days_english | en | "When is it cheapest to fly to Istanbul in January?" → fare_calendar month 1; three days said; the card shown (not dropped by the guard) |
| f08_relative_dates_saudi | ar-SA | «بعد بكرة للدوحة وأرجع بعد ثلاث أيام» → DOH 11-18, back 11-21 |
| f09_switch_ar_to_en | ar-SA→en | (needs `language_switch`) Saudi start; "can we do this in English? Mumbai on the third of December" → English replies |
| f10_switch_en_to_ar | en→ar-SA | (needs `language_switch`) English start; «طيب كمل معي عربي، أبي سنغافورة» → Saudi replies |
| f11_profile_failure_english | en | profile fails; "How many times have I flown to London?" → says it could not load; never "no trips" (the demo's weakness 2) |
| f12_search_failure_saudi | ar-SA | search fails → «ما قدرت أشيك الحين»; never «ما فيه رحلات» |
| f13_no_at_read_back_english | en | "no, don't book it" → declined, nothing booked; the talker's own "nothing is booked" not blocked (no violation, no fixed error phrase) |
| f14_yes_but_change_saudi | ar-SA | «إي بس خلها لشخصين» over the summary → change_trip travelers 2 → new read-back → yes → done for 2 |
| f15_not_served_english | en | "Jeddah to Dubai" → not served, explains Riyadh (with or without a search); then Riyadh to Dubai works |
| f16_business_sold_out_msa | ar | business on a flight and day with no business seats → says so, offers economy or another flight |
| f17_same_as_last_time_saudi | ar-SA | «أبي نفس رحلتي الأخيرة لدبي» → traveler_profile then asks the dates (one question); no claim of a booking |
| f18_booking_refused_english | en | booking mode refuse → failed line; no claim |
| f19_booking_timeout_saudi | ar-SA | booking mode timeout, lookup on → unknown said; asked to book again → the per-call cap refuses it in code; one write in the store's log, none booked twice |
| f20_reference_asked_english | en | after a booking, "what's my booking reference?" → six digits said; before asking, never |
| f21_first_class_narrowbody_english | en | first class to Dubai → not offered there, business offered |
| f22_bare_yes_closing_saudi | ar-SA | bare «إي» over the closing question, the summary played whole → done (amended 2026-11-17, the owner's "any yes books"; it was asked again, then «إي احجزها» booked) |
| f23_singapore_tuesday_english | en | Singapore on a Tuesday → no flight that day, the nearest days offered |
| f24_slow_search_saudi | ar-SA | search mode slow (4 s) → the progress line plays, then the answer |
| f25_long_no_repeat_saudi | ar-SA | 8 turns: a city, a calendar ask, two date changes, a cabin question, a pick; no identical or near repeat in any reply |
| f26_cut_repeat_english | en | the listing of London flights cut by `stop` at about 10%; "one more time" → the reply shares 60% of its tokens with the cut reply |
| f27_detail_kept_saudi | ar-SA | turn 1 «أنا وزوجتي على بزنس»; turns 2-5 dates, the calendar, a date change; turn 6 a pick → the read-back holds 2 travelers in business with neither said again |
| f28_city_change_msa | ar | Istanbul for three turns, then «لا، أفضّل باريس» → search again; Istanbul never said after, the read-back holds CDG |
| f29_week_overview_english | en | (added 2026-11-17) "which days have flights to Paris during next week?" → search_flights with the span `next_week`, at once, no return asked first, the card shown; then Thursday, back the Sunday after → CDG 11-26, back 11-29 |
| f30_dearest_saudi | ar-SA | (added 2026-11-17) Jeddah tomorrow, back Thursday; the afternoon one out; «عطني أغلى وحدة فيهم» on a return list whose 07:45 and 17:15 share the top fare → pick `dearest`, the read-back holds the 07:45 (the first listed); a yes with the send word → done |
| f31_yes_over_read_back_saudi | ar-SA | (added 2026-11-17; needs the flight app's yes-over-the-read-back setting on) Doha next Sunday, one way; «الأولى لو سمحت» → read-back; a bare «إيه» over its summary, nothing after it → done once the summary has played whole |
| f32_full_flight_msa | ar | (added 2026-11-17) Doha next Monday in business: the morning flight, the lowest fare, has no business seat → the listing says it as full; picked by its part of the day → `no_seats` with `choose_flight` alone (no change_trip unasked), economy or the other flights offered |

Held-out (about 12), written by a builder who has never seen a dev result, before the first run,
on other routes and words: a Saudi round trip to Singapore with "the second one"; an English
Istanbul trip with a corrected return day; an MSA one-way to Mumbai for three; a Saudi
cheapest-days ask for Dubai in December then a booking; an English cabin change from business to
first on London; a Saudi switch to English while a read-back waits (needs `language_switch`); an
English fare calendar failure; an MSA "no" then a booking on another day; a Saudi «الأسبوع الجاي
يوم الثلاثاء»; an English "yes, but make it one way"; a long Saudi call with a cut and a repeat;
an English call with a detail kept from turn 1 to turn 6.

As built (h01-h15): fifteen, so every dev kind has one (booking_outcome: a late write the
lookup finds, MSA; profile: the last London trip, English; unavailable: a city not served,
Saudi); "the second one" is on Paris (h01), since Singapore flies once a day, and Singapore is
the long Saudi call with a cut (h11). A turn also carries `forms` (the date form of each
expected date), `asks_reference`, `shows_card` and `hears_progress`; `problems()` is in
`evals/rules.py`.

`problems()` refuses a set that breaks a rule: an id twice, a dev and held-out pair that share a
route and a date, a kind with no dev or no held-out scenario, a `needs` name not on the closed
list, an expected date the airline cannot resolve, a `repeat_of_cut` turn not right after a
`stop`; a test runs it inside `poe check`.

### 7.3 How run F runs with what exists

What exists: `TextCall` (multi-turn calls in text, on the system clock with a real model, with
`user(..., during=..., at=...)`, `stop()`, the turn data, `violations`), `AudioCall` and
`TurnReplay` (a clip over a reply, a clip as a turn), `ScriptedLLM`/`FunctionLLM`. Ole5's run S
and run A runners live in `ole5_voice.evals` (about 5,600 lines of the app's 22,000 lines of
evals), and an app may not import another.

| Option | What | Cost | Risk |
| --- | --- | --- | --- |
| (a) Move run S and A into the library's testing kit | the scenario model, the TextCall seam, the session runner, pacing, history, the judge, made general | about 30 modules touched, 1-2 weeks, a long review | Ole5's registered runs, scorecards and history format change under the plan's measurements |
| (b) The flight app's own run F | five modules (`evals/scenarios.py`, `call.py`, `checks.py`, `score.py`, `run.py`), about 1,400 lines and their tests, checks in code only | 2-3 days | some duplication with Ole5's (the seam, the scorecard) |
| **(b) plus L6 and L8** (recommended) | (b), and the paced, capped chat model with its spend, clock and day counter (L6) and L's repeat checks (L8) in `t2_agentic_voice.evals` | (b) plus about a day | small: L6 is a move with Ole5's imports changed; L8 is new pure functions |

Recommended: (b) plus L6 and L8. The parts both apps need for money, safety and L's checks
(pacing, the cap, the day's limit across both apps, the main-checkout refusal, the repeat
measures) live once, in the library; the scenario format stays each app's, since their facts
differ (an exact airline, against a knowledge base a judge must read). If a third app needs
scripted calls, the seam moves too, then.

`poe eval-flights --split dev --repeats 3 --out <main checkout>/var/runs/<name> [--model ...]
[--effort medium] [--cap-usd 10] [--resume]`: the out folder is always under the main checkout's
`var/` (an absolute path: a relative one given from a run's worktree resolves inside it, which
`check_out` refuses); refuses the main checkout as the run's tree, a dirty tree, an out folder in
use; a dry estimate of the most spend before anything is sent (each play's most requests × the
input budget × the price), refused past the cap; a smoke play first (the first dev scenario
once: no failed, retried or refused request, no violation); then every scenario once, then
again, until each has its repeats; a record per play, progress lines of ids and verdicts only,
never a text; the scorecard (`scorecard.json`, `scorecard.md`) and one line in
`evals/history.jsonl`. Exit 0 complete, 1 incomplete (scorecard still written), 2 refused. By
run A's numbers, a dev pass is about 25-35 minutes and under $0.20.

**The day's limit is shared.** Both apps' runs use the same Groq key. L6's day counter reads the
day's requests from every app's run history (the list of history files it is given, Ole5's and
the flight app's), so run F after Ole5's run A, on the same day, counts both, and no run stops
part way for a limit it did not see.

**Audio.** Run F is text, like run A. The spoken side is measured where the plan measures it:
the STT bake-off and run H on the golden set, which gains the recording session's flight lines
(7.4); run T (first audio) on recorded flight requests once they exist. A spoken multi-turn run
(audio clips said as a whole call) is not built now; it needs `AudioCall` to play a scripted
call, a library change for later.

**Ole5's sets as the check.** Every library change that can move a measured outcome (plan 010's
rows 1.x, 2.x) runs both: run F dev and Ole5's run A dev with its long scenarios (L). A change
that moves no outcome (L1, L3, L6, L8) needs `poe check` alone. Rows 1.3, 1.4 and 1.6 are read on
run F's L checks (f25-f28) and Ole5's L.

**F.4, the comparison.** The owner makes the same scripted booking call (f01's words, then
f02's) on the public demo and on ours, recorded; we read first audio, the words heard, turns to
book and listeners' scores into `docs/project/` (plan 010's F.4). The demo's typed timings
(about 1 s to speak after a tool) are not voice timings, so only the recordings compare.

As built (A11, 2026-11-17): the runner is seven modules, `call.py`, `checks.py`, `score.py`,
`folder.py` (the out folder, its `run.lock`, `scorecard.md`), `run_setup.py` (arguments, the
set's rules, prices and limits, the estimate, each play's settings) and `run.py`; a booking is
expected when a turn's outcome is `done`; `declined` and `none` are checked alike; said checks
read what the caller heard (the runtime's lines among it), the language, register, words,
options and repeat checks the talker's own words; the defaults are `gpt-oss-120b` at
0.15/0.60, 30/100000/10000, an input budget of 8000; the history line must be committed before
`--resume`, which goes on at the run's commit or a later one that changed only the apps'
`evals/history.jsonl`, the run keeping its first commit and each session recording its own;
the talker's prompt says the scenario's today, as the mock airline does; a call that needs
`language_switch` plays under `stt.live_language = "detected"` (D-103), a typed turn heard in
the call's language as it stands (b1749ba).

### 7.4 What a recording session adds (0.6's list gains these)

About 40 lines, each said by the owner and any tester who agrees, through Ole5's `poe record`,
into the golden set as a new stratum `flight` (the STT bake-off reads the golden set):

- **Cities**, Saudi and English, alone and in a sentence: الرياض، جدة، دبي، الدوحة، القاهرة،
  إسطنبول، لندن، باريس، مومباي، سنغافورة; "Riyadh", "Jeddah", "Doha", "Istanbul", "Mumbai",
  "Singapore"; «أبي أروح لندن», "I want to go to Paris".
- **Dates**: «بكرة», «بعد بكرة», «الخميس الجاي», «الأحد اللي بعده», «الأسبوع الجاي يوم الثلاثاء»,
  «يوم أربعطعش», «سبعطعش ديسمبر», «العاشر من ديسمبر» (MSA), "next Thursday", "the fourteenth",
  "December the third", "a week later", «أرجع بعد أسبوع».
- **Numbers**: «شخصين», «ثلاثة أشخاص», «أنا وزوجتي», "two adults", "just me", fares said back
  («ألفين وخمس مية»).
- **Times and picks**: «حقت الصبح», «اللي بالليل», «الأرخص», «الثانية», «الأخيرة», "the morning one",
  "the cheaper one", "the second one", "the nine o'clock".
- **Cabins**: «سياحي», «بزنس», «رجال الأعمال», «درجة أولى», "economy", "business", "first class".
- **Yes, no and changes at a read-back**: «إي احجزها», «أكيد احجزها», «لا لا تحجز», «إي بس خلها
  لشخصين», "yes, book it", "go for it", "no, wait, make it the fourteenth".
- **Names**: the persona's and the airline's names the owner picks, in both languages, and «خالد».
- **Switches**: "can we do this in English?", «كلمني عربي».

The terms file gains the ten cities in Latin script, the airline's name, economy, business.

## 8. The build order

Small commits, each gated by `uv run poe check` (with `PYTEST_XDIST_AUTO_NUM_WORKERS=4`, one gate
on the machine at a time, `.mypy_cache` removed before each step's last gate). **Two slots, never
more**: slot A (the app) and slot B (the library). A review takes a slot: it never runs beside
two builders. Each step merges into `plan-010-integration` before any step that needs it starts.

**Slot B is shared with plan 010's item 1** (the STT model and the language switch, which the
owner put first, "What happens first"). The lead orders slot B: item 1's steps first, the
flight's library steps between them when item 1 waits (a run in progress, a key awaited), or
after it. f09, f10 and their held-out case need item 1's switch (2.5) and are skipped until it
lands.

**Ownership.** L3, L4, L5, L7 and L8 touch files plan 010's tracks own (`agent/turn.py` and
`context.py`, Track C; `domain/text/`, Track D; `voice/protocol.py`, Track E; `t2v-client.js`,
Track F; the measurement, Track A). Each is built by, or handed over by, the track that owns the
files, and the hand-over is recorded in the plan's progress log.

**Slot A, the app, in this order** (each after the one before it, merged):

| Step | Needs | What | Tests |
| --- | --- | --- | --- |
| A1 | | The skeleton and its registration (1.2): package, pyproject, `__init__`, harness, root pyproject, tests/isolation.py, CLAUDE.md, ARCHITECTURE.md, tzdata; `airline/airports.py` | arch passes with the new app; every alias matches its code; every spoken form; unknown city; no app imports another; `FLIGHT_VOICE_` dropped from the shell (isolation test) |
| A2 | A1 | `airline/schedule.py`, `airline/fares.py` | every route both ways, arrival times in the arrival zone (RUH 09:10 + 7h05 lands LHR 13:15 in winter), across London's and Paris's clock change (2027-03-28) and Cairo's, with a later `today` (the pinned window ends 2027-03-16, before any change); fares deterministic (same value across two processes); round to tens; Tuesday gap; first only on 787-9; the helper that finds the scenarios' dates |
| A3 | A2 | `airline/dates.py`, `airline/profile.py`, `airline/bookings.py`, `airline/system.py` | every DateSpec row of 2.4 against 2026-11-16 and against a Saturday and a month's end; past and out-of-window; store modes, find, reset, scoped by traveler (adversarial: another traveler id sees nothing) |
| A4 | A3 | `trip.py` | per call id, bounded at 64, dropped on CallEnded, one assignment per change, a cancelled tool leaves it whole |
| A5 | A4 | `said/words.py`, `tools/results.py`, `tools/cards.py`, `tools/search.py` | every status; failure is a ToolError with its message; at most 4 options; `say` from the fixed list; `fare_basis_said` on every listing; every card passes `check_ids` with the default `GuardSettings`, in both languages; a `TextCall` with `ScriptedLLM` that searches and shows a card |
| A6 | A5 | `tools/choose.py`, `tools/trip_view.py`, `tools/calendar.py`, `tools/cabins.py`, `tools/profile.py` | every pick; unclear pick; a complete trip's `say` sends to book_trip; cabin change re-prices and drops a leg short of seats; calendar's seven days in its data and `null` days; profile's counts; profile failure says so; every card passes `check_ids`; `traveler_profile` has no `reports_on` |
| A7 | A6, and B3 if merged (else `said/numbers.py`) | `booking/draft.py`, `booking/lines.py`, `booking/action.py` | hidden fields: absent from the schema, overwritten when sent; read-back rendered in three registers, with its trip kind (a one-way read-back holds «رايح بس» / «ذهاب فقط» / "one way"); lines' rules on the final lines; the guard's tests of 4.2 (negatives pass, claims blocked, profile-plus-claim blocked); `max_per_call` 1: a second write after `unknown` refused, nothing booked twice in `late` mode; `ActionSafetySuite` with the test TripBook and the demo caller (4.1); a refused, a timed-out with lookup, a late write; booking for another traveler impossible |
| — | | **The owner picks the names** (5.1), asked by the lead | |
| A8 | A7, B1 | `agent.py`, `persona.py`, `instructions/`, `settings.py`, `server.py`, `routes.py`, `traveler.py` | the declaration builds; greetings, pronounce map and vocabulary built from settings, checked with a non-default name; a name that breaks the lines' rule refused, the setting named; settings refusals name the setting, never its value; var_dir always nested, with `T2V_STORAGE__VAR_DIR` set; tokens a day from the setting; routes: loopback only, JSON only, reset; CSP headers; the token names the demo traveler, and no request changes it (adversarial); the server serves an echo when no Groq key, as Ole5 does; `test_own_words.py` on the tool texts and instructions |
| A9 | A8 | `web/` (index, css, app.js, cards.js, bookings.js, texts.js, mark) | in Ole5's fake browser (`tests/browser.py`): text set as text (markup shown as text), `dir="auto"` lines, RTL page in Arabic, cards newest first and at most three, the toggle sets the call's language, "Your trips" list and filter, "Start over" asks first; CSS: no physical left/right, phone width; `test_own_words.py` on the page texts |
| — | | **Run F registered** in plan 010 by the lead (7.1) | |
| A10 | A3, the registration | `evals/scenarios.py` and the dev scenarios f01-f28 | every file reads; `problems()` holds none; every expected date resolves; `needs` only from the closed list |
| A11 | A10, B4, B6 | `evals/call.py`, `checks.py`, `score.py`, `run.py`, the poe task | a fake call through the seam; each check on a crafted turn, L's checks included (a near repeat caught, an asked repeat exempt, a cut repeat measured); the estimate refuses past the cap; refuses the main checkout; an out folder inside the worktree refused; resume |
| A12 | A10 | the held-out scenarios, by a builder who has seen no dev result, in slot A | as A10 |

**Slot B, the library, in the order the lead sets** (with item 1's steps):

| Step | Needs | What | Tests |
| --- | --- | --- | --- |
| B1 | | L1: the access-code token route and the page headers into `t2_agentic_voice.server`, general names, with tokens a day and wrong codes an hour as parameters and the caller built by the app; Ole5 switched, keeping 10 a day | the route's tests moved from `tests/ole5_voice/test_token_route.py` to the library's tests, same assertions; Ole5 keeps a test of its own caller and its 10; a test with a different limit |
| B2 | | L3: the call's date (`TextCall(today=...)`, `AudioCall`'s) and `VoiceAgent.time_zone`; tzdata in the library | prompt says the pinned date; Riyadh's date after 21:00 UTC; a zone unknown to zoneinfo refused at declaration with a `ConfigurationError` naming the field; defaults unchanged for Ole5 |
| B3 | | L4 (row 1.8's numbers, times, dates and amounts), with Track D | every row of 3.6's table; 0-99 999 in Saudi words; ordinals 1-31; parts of day; the register chosen from the reply; a native check noted (TD-058); Ole5's speaking tests |
| B4 | | L6: the paced, capped chat model, `ModelSpend`, `Clock`/`Sleep`, the day counter over every app's history, the main-checkout refusal, into `t2_agentic_voice.evals` | Ole5's pacing and run tests moved to the new imports, same assertions; the day counter sums two histories |
| B5 | after A9 | L5: option rows on cards, with Tracks E and F | 9's contract; Ole5's widget card tests unchanged |
| B6 | | L8: L's repeat measures, with Track A | identical and near repeat by C's definitions; token overlap; the exemptions |
| B7 | with 1.4 | L7: `ToolResult.brief`, with Track C | 1.4's tests; run A dev, L |

**Then**: a smoke of run F dev (one play), the first full dev pass on the owner's laptop, a live
call through the page (the owner or an agent with the fake microphone rig, memory "Live call
without a microphone"); the persona's lines heard once by a Saudi ear. After that: the page's use
of L5; the recording lines into 0.6; plan 010's rows, each run on run F dev and Ole5's sets.

**Reviews** (each in a slot): an agent that did not write the step reviews it; security review on
B1 (the token route), A7 (invariants 1, 2, 3, 4, 6), A8's routes; harness review on A1, B4 and
A11.

## 9. What stays general: the library changes

Each change is named so Ole5 benefits too; each lands with its tests and Ole5's run as the check
where an outcome can move.

| # | Change | Where | Size | Why general | Ole5's check |
| --- | --- | --- | --- | --- | --- |
| L1 | The access-code token route (`POST /token`, its guard) and the page headers move into the `server` facade, with tokens a day and wrong codes an hour as parameters and the caller built by the app (a function the app gives) | library `api/`, `server.py` facade; Ole5's `token_route.py` and `server.py` shrink; the route's tests move to the library | small | any team's demo page needs it; copying 226 lines would cost both apps' duplication grade (`poe quality`) | the moved tests; Ole5's own caller test, 10 a day |
| L2 | (only if 4.1's hidden fields are refused) A read-back of looked-up values: `validate` may return the draft plus a `quote` model whose fields the read-back may name, as `done` names the result's | `actions/action.py`, `action_checks.py`, `spoken_lines.py` | small-medium | any action whose read-back states a price, a name or a date the team's system looks up | `ActionSafetySuite`; run A dev |
| L3 | The call's date: `TextCall(today=...)` and `AudioCall`'s, and a `VoiceAgent.time_zone` (default UTC) for the prompt's "Today is", checked at declaration; `tzdata; sys_platform == 'win32'` added to the library (`uv add --package t2-agentic-voice`), since zoneinfo finds named zones on Windows only through it and ARCH-DEPS cannot see an unimported package | `testing/text_call.py`, `testing/text_side.py`, `agent/turn.py` (Track C), `domain/declaration.py` | small | Ole5 is Saudi too; a pinned day makes every scripted run reproducible | defaults unchanged; `poe check` |
| L4 | Spoken numbers, times, dates and amounts by register (Saudi, MSA, English), applied after the guard: `speak_number(n, language, register=)`, `speak_time`, `speak_date`, `speak_amount`. This is plan 010's row 1.8 for these forms, built with Track D, not a second change | `domain/text/speaking.py` (split first if past 300), `languages` facade | medium | Ole5's numbers and 1.8's dates and times; the Saudi words today are MSA's (TD-058) | Ole5's speaking tests; run A dev |
| L5 | Option rows on cards: `Card.rows` (at most 8; each `title` up to 80 chars, `detail` up to 120, `value` up to 40, `mark` from a closed set `best`, `chosen`, `unavailable`), and `t2v/1`'s `card` with the same optional field; the client passes it to the page | `domain/cards.py`, `voice/protocol.py` (Track E), `voice/session/speaker.py`, `api/static/t2v-client.js`, `dev-console.js` (Track F) | small-medium | Ole5's ticket card (Q21) and its steps; any team's lists | Ole5's widget card tests unchanged (steps still work) |
| L6 | The paced, capped chat model for runs (prices, the cap), `ModelSpend`, `Clock` and `Sleep`, the day's request counter reading every app's run history, and the main-checkout refusal, into `t2_agentic_voice.evals` | from `ole5_voice/evals/chat_pacing.py`, `pacers.py`, `talker_data.py`'s `ModelSpend`, `groq_answerer.py`'s `Clock`/`Sleep`, `worktree.py`'s refusal | small-medium | every team's spending runs; one key's day counted once | Ole5's tests at the new imports, same assertions |
| L7 | Aging tool results (plan 010's 1.4) keeps a tool's own one-line brief: `ToolResult.brief`, given by the tool, used when its result ages | `actions/tools.py`, `agent/context.py` (Track C) | small | 1.4 today knows only the knowledge tool's shape; the flight tools give "listed 3 flights to London on 17 Dec" | run A dev, L |
| L8 | L's repeat measures as pure functions: identical and near repeat (same first clause, token overlap 0.8), token overlap for the cut repeat (0.6), with plan 010's exemptions | `testing/`, `evals` facade (Track A) | small | Ole5's run S needs the same checks for L; one definition for both | its own tests |

**L5's contract and its security.** A card is data, never instructions: the page shows it and
does nothing it says. Every text of a row passes the output guard's ID rule with the card's
title and steps (`Card.texts()` gains the rows), so no number the call has no evidence for
reaches the screen. The client checks each field's type and drops a row that is not one, and a
page sets every text with `textContent`, never as HTML. The `mark` is a closed set, so a page
maps it to a style, never to markup. Nothing the caller must read is ever only on a card: the
reply says it (D-075). The session-to-client direction has no size bound today; L5 bounds rows
and lengths in the model, so a card stays small.

**Plan 010's own rows the flight app leans on** (already planned, general by design): 2.5 (the
language switch: `language_switch`, f09, f10 and a held-out case), 1.15 (the line at the
search), 1.8 (speech shaping, with L4), 1.3 and 1.6 (no repeats, f25-f28), 1.4 with L7, 1.5 (the
cut repeat, f26), 1.11 and 2.1 (end of turn). Each runs on run F dev and Ole5's sets.

**Not proposed now** (the demo has them, we do not need them yet): slow tools moved to the
background after about 4 s, and soft interruptions are already ours (`duck`, plan 005). The
background tool job is a later library change if run F's slow-search scenario (f24) shows the
caller waiting too long.

## 10. Decisions the owner may want to change

1. **The names**: put to the owner before A8: persona Saad, Fahad or Nawaf; airline T2 Air,
   Sahab Air or Najm Air; Saad and T2 Air as placeholders until then. The traveler "Khalid
   Al-Harbi", Gold. All settings or data, one place each.
2. **No connections**: every trip starts or ends in Riyadh; Jeddah to Dubai is not sold.
3. **The fixed today in runs** (2026-11-16) and `live` on the server.
4. **"Next Thursday" means the coming Thursday**, never today; "Tuesday next week" means the
   week starting next Sunday. The date is always said back with its weekday, so a wrong guess is
   caught by the caller.
5. **Travelers as a count only**, no names of other travelers, no seat maps, no payment.
6. **The booking reference is six digits** (so the guard's ID rule protects it), said only when
   asked.
7. **A booking needs both legs chosen**, re-priced at the write; a changed fare refuses the
   write rather than booking a price not read back.
8. **One booking per call** (`max_per_call` 1); a second trip needs a second call.
9. **One confirmation, not two**: once every flight is chosen, the read-back plays at once, with
   no summary of the agent's own before it.
10. **The read-back always names the trip's kind** (round trip or one way) and states every
    value booked in words rendered by code.
11. **The talker writes numbers in digits**, so the guard checks every fare; the voice says them
    in words after the guard, in Saudi forms once L4 (1.8) lands.
12. **"One way, per person" said once** on each listing, so the larger total in the read-back is
    no surprise.
13. **At most three options aloud**, then "and one more"; the card shows up to four.
14. **No manual search form and no clickable chips** on the page: the call is the product.
15. **Our own page words** ("Where are you flying, Khalid?", "Your trips", "Start over",
    "Lowest fare"), held free of the demo's by a test.
16. **The access code kept in memory only** for the page's life; **50 tokens a day**.
17. **Run F checks in code, no judge**, since the airline is exact; L's checks added; run F
    registered as rule F in plan 010, its held-out read an eighth M9 read.
18. **The flight app's own runner (b) plus L6 and L8**, not moving all of Ole5's runners now.
19. **The recording's flight lines join Ole5's golden set** as a stratum, since the STT
    bake-off reads that set.
20. **The flight server's own storage folder**, always `<var_dir>/flight`, and a per-day action
    cap of 50.
21. **tzdata as a dependency** of the app and the library (Windows only).
22. **The hidden-field draft** (4.1) rather than L2, unless the library refuses it.
23. **Slot B shared with item 1** (STT and the switch), item 1 first, as the owner ordered.

## 11. Risks to watch

- The talker passing a date as a raw string instead of a DateSpec: the schema refuses it and
  says which field; f01-f08 watch for retries.
- A long Arabic read-back (about 25-30 words) cut by a caller's "mm": the receipt needs the whole
  summary; the overlap rule and the `asked_again` line handle it; f14 and f22 hold it.
- Calling book_trip straight after the last pick: a caller who only meant to hear the trip gets
  a read-back and must say no. The read-back says it all, and a no books nothing; watch f01,
  f02, f05 and the live calls.
- Until L4 (1.8) lands, fares and times written in digits are said in MSA number words (or read
  as written, for times) in a Saudi reply. The read-back, rendered by code, is not affected.
- 1.4's aging before L7: the flight results' briefs would be lost; the trip draft in code covers
  the picks meanwhile.
- The Saudi number words are the agent's until a native speaker checks them (3.6).
- The claim list is English-negation-safe only by its wording: a new English phrase must be
  checked against "nothing ...", "no ..." sentences before it is added (4.2's tests).

## 12. Review notes

Two reviewers (safety-voice, harness-build) read the first version. Each finding was checked
against the code at 14b1b0f before it was taken. **All were taken**; three in a slightly
different form, said below.

**Safety-voice**

1. *"is booked" blocks the honest "nothing is booked".* Taken. Checked: `domain/claims.py`
   negates only in Arabic, and `domain/action_lines.py` leaves the reply after a plain no to the
   talker. Bare "is booked" and also "has been booked" dropped (the same trap); `failed` and
   `declined` reworded in all three languages; guard tests for negatives added (4.2); f13 checks
   it.
2. *`traveler_profile`'s `reports_on` lets a booking be claimed.* Taken. Checked: status
   evidence is any ID-shaped token in the results (D-081), and the profile is full of them.
   `reports_on` removed; "your booking reference is" and «رقم حجزك» removed from the claims; the
   adversarial test added; the profile's `say` and the instructions say a past trip as flown.
3. *`max_per_call` 2 allows a second booking after an unknown outcome.* Taken. Checked:
   `_capped` counts `flagged` rows, and `NOT_WRITTEN` is only `rejected` and `not_sent`. The cap
   is the library's 1; f19 now checks the refusal in code. The reviewer's alternative (a
   `validate` refusal) was not needed with a cap of 1.
4. *The spec copies the demo's page text.* Taken. Our own words throughout (6.1), f17 renamed,
   the tool description reworded, and `test_own_words.py` added.
5. *Names hard-coded in greetings, pronounce map, vocabulary.* Taken (5.1): all built from
   settings, the lines' rule run at load, tested with a non-default name.
6. *The trip confirmed twice.* Taken: a complete trip goes straight to `book_trip`; the
   instructions and run F's play check match. The trade-off is listed as a risk (11).
7. *A one-way read-back never says "one way".* Taken, and widened: the read-back names the
   trip's kind both ways («رايح جاي» / "round trip" too), so a wrong `one_way` is heard either
   way.
8. *Fares per person, one way, never said.* Taken: `fare_basis_said`, the `say` hints, the
   instructions and f01/f05's checks.

**Harness-build**

1. *`max_per_call` 2 and TD-143(3).* Taken (with safety 3). Checked: TD-143(3) is open.
2. *Card texts fail the ID rule.* Taken. Checked by running `check_ids` with the default
   `GuardSettings`: the first version's option step fails, the new ones pass (3.4). Cards put
   their texts in `ToolResult.evidence`; the calendar's data holds all seven days; tests per card.
3. *Said-form words contradict the digits rule and pass the guard unread.* Taken. Checked:
   `agent/prompt.py`'s "Write every number in digits", and `guard_ids.py`'s "Numbers said as
   number words are not read". Results now give machine values; the talker writes digits; L4 is
   row 1.8's forms after the guard, with Track D. Word forms stay only in the lines code renders,
   with `said/numbers.py` as a stopgap until L4 lands, so the booking step does not wait on it.
4. *Run F can't measure L's rows, and is not registered.* Taken: L's per-turn checks, the
   `stop` turn and four long scenarios (f25-f28) added, plus two held-out; run F is registered
   as a dated plan amendment before A10. Added beyond the finding: L8, the repeat measures as
   library functions, so Ole5's run S and run F share one definition.
5. *The build order.* Taken: two slots, slot B shared with item 1 (owner's order), steps ordered
   by dependency with a merge rule, the booking step after the tools and the server step after
   the booking, the runner in slot A after the scenarios, the held-out builder in slot A, reviews
   taking a slot, `PYTEST_XDIST_AUTO_NUM_WORKERS=4` (checked: pytest-xdist 3.8 reads it), one
   gate at a time, `.mypy_cache` removed, and the track-owned files named (checked against plan
   010's Tracks section). The step names changed (A1-A12, B1-B7).
6. *Tests don't drop `FLIGHT_VOICE_` variables.* Taken. Checked: `DROPPED_PREFIXES` holds only
   Ole5's app prefix. Added to A1 (1.2 item 3).
7. *`ActionSafetySuite` fails as written.* Taken. Checked: the suite's `caller` defaults to
   none and TD-142(5) is open. The test TripBook and the demo caller are in 4.1 and A7.
8. *L6 is not a pure move; two histories undercount the day.* Taken. Checked: `chat_pacing.py`
   imports `Clock`, `Sleep`, `MinutePacer` and `ModelSpend` from three Ole5 modules; `check_out`
   refuses an out folder in a worktree. L6 widened, the day counter reads every app's history,
   Ole5's tests move imports, the out folder is under the main checkout's `var/`.
9. *The moved token route keeps 10 tokens a day.* Taken. Checked: `TOKENS_PER_DAY` 10,
   `WRONG_PER_HOUR` 20 in Ole5's route. L1 takes both as parameters; the flight app 50 a day.
10. *`needs` names plan rows.* Taken: a closed list of capabilities (`language_switch`); the plan
    maps rows to them.
11. *var_dir from the environment can stop the flight server beside Ole5.* Taken. Checked:
    `api/lockfile.py` locks one process per `storage.var_dir`. Always nested, tested.
12. *L3's time zone needs tzdata in the library.* Taken: in L3 and B2, with the declaration check.
13. *Section 0 misstates Q23.* Taken. Checked: plan 010 records the four answers and the names
    proposal (commit 14b1b0f). Section 0 cites them; the names are put to the owner before A8.

## 13. The lean agent (D-113, the owner's ruling of 2026-11-17)

**Why.** In the owner's live test the agent felt clunky because the code kept overriding the
model: a scripted read-back and a strict yes rule, six fixed pick kinds, closed date forms and a
gate that listed nothing before a return day, and tool results that dictate every sentence. The
owner ruled "Lean next to it": a model-led agent beside today's (`src/flight_voice/lean/`), the
same airline, trip state, persona, names, words and page, compared on live calls, the winner
kept. The setting `FLIGHT_VOICE_AGENT` chooses it (`scripted` by default, or `lean`); the server
declares the agent chosen and, for the lean one, registers its booking check's observers
(`AgentSpeechEnded`, `UserTurnEnded`, `CallEnded`). Its settings path turns on
`guard.plain_speech`, `guard.drop_stage_notes` (a sentence opening as the reasoning does, "We
need…", after an Arabic sentence is a leak after a space too: f-dev-lean-4's f25 said one),
`guard.question_stop_drops_calls`, four model requests a turn and `tts.spoken_numbers = "by_register"` (D-107: the times and fares it writes in
digits are said as words in the caller's register, "14:00" «ثنتين الظهر»), as the scripted
agent's does, and not the yes held over a read-back, which it has none of: it turns on `interruptions.answer_yes_over_question` instead (D-116), so a yes
said over its closing question ("Shall I book it?", «أحجزها لك؟») is answered once the reply
ends, unless the caller said other words after it, and adds the booking's send words
(`booking/lines.py`'s `SEND_WORDS`: «احجزها», «احجز», "book it", "confirm" and the like) to
`words.send`, so «إي احجزها» and «نعم، احجزها» there are that yes too; and, as for the scripted
agent, `guard.retry_claims` and the caller read as Saudi first (below, "The owner's call of
2026-11-18"); each unless the environment sets it. Its name is `flight-lean`, so its traces and
its runtime's folder are its own.

**What stays in code, and nothing more.**

1. *Facts only from tools.* The library's output guard (rule B) and plain speech stay on; the
   prompt says every flight, time, fare and reference comes from a tool result of this call.
2. *One booking check, in the app's code* (`lean/booking_check.py`; the owner: "code only checks
   that the booking matches what was said"). `book_trip` books the trip chosen so far only when
   the trip is complete (every leg chosen, seats for the travelers in the cabin); since the trip
   was last completed or changed, a reply of the agent ended; and the caller spoke after that
   reply (a turn heard after it ended, or, for a reply cut short, a later turn heard before it
   ended: a turn that cuts a reply can end before the reply's end is told; or a later turn heard
   before it ended whose speech began once some of the reply had played, as
   `UserTurnEnded.reply_played` says: a yes over the closing question, answered once the reply
   ends, D-116). Until 2026-11-18 the reply also had to state the trip's total and play past it;
   the owner loosened that ("the confirmation can be done before the agent saying the total, I
   have it on screen"): the review card shows the total and the caller has heard the fares. What
   stays is a caller turn after the trip as it is now was set. The check reads the call's events,
   kept per call and dropped at `CallEnded` as the trip book drops a trip (a call held in text
   reads them from `TextCall.emitted`); the tools mark the trip each time they write it, so a
   total said before a change never books the changed trip. When the check fails, `book_trip`
   books nothing and answers `not_confirmed`, its one fixed `say`: "Say the trip with its total
   in one sentence and ask whether to book it. Book only after the caller agrees." The model's
   own judgement that the caller agreed is the yes: any yes books, a bare one too.
   **This departs from the library's "only actions act" design** (invariant 1: the read-back and
   its receipt), for the mock airline alone, by the owner's ruling. The lean agent declares no
   action, so its prompt gets no action rules, and `book_trip` is one of its tools, writing to the
   mock airline's booking store as the scripted agent's action job does, for the call's verified
   traveler (invariant 3), one booking a call, a write whose end is not known never sent again.
3. *The voice layer is untouched:* turn-taking, interruptions, speech-to-text, text-to-speech and
   the language switch.

**The tools** (plain data in and out, no scripted `say`; a short `note` only where the data alone
would mislead: a full flight, a route not served, a date outside the window):

- `find_flights` (`lean/find.py`, `span.py`) takes a city in any language or its code (Riyadh
  the start unless another), the day they leave as an ISO date or a span of at most two months, 62
  days (`{"first", "last"}`, the owner's ruling of 2026-11-17), the return day or null (one way, or not said yet), and the cabin and the
  travelers (the trip's own, economy and one at first). A day gives the route in the caller's
  register (`route`, with `route_msa` beside a Saudi reply's), the fares' basis in it
  (`fares_are`, with `fares_are_msa`: "per person, each way" on a round trip, "per person" on a
  one way, «للشخص، رايح بس», «للشخص، ذهاب فقط»; no English digit word, as "910, one way" reads
  as one number to the output guard, f-dev-lean-3), and the outbound flights, with a round
  trip's return by its day alone and a note that its flights come with `choose_flights` once the
  outbound is chosen, or with its `list_leg` when the caller asks about the way back first
  (given both days' flights, the model listed both in one reply, over the words a reply may
  have, and took one pick for both legs: f-dev-lean-4, 34 of 38 round-trip listings, f30's and
  f09's wrong bookings); a search that keeps a leg's pick (its route and day the same) names it
  in `chosen` by its id, and with the outbound's kept gives the return's flights, so a new
  return day after the outbound pick never asks for the way out again: each outbound flight a
  stable id
  (`T2-401-2026-11-19`), its name and aircraft (said only when asked, as the card shows them),
  its times, its length, its fare per person, `seats_ok`, `nonstop` and `part_of_day`, with
  `count`, `first_departs`, `last_departs` and `cheapest_id`; the trip takes
  the route, the days and the options; its card is the outbound segment. A span gives the daily
  departure times and the two cheapest days with their fares; up to 14 days each day's weekday,
  flight count and lowest fare and the days with no flight, for longer week by week (the Saudi
  week, each week's days with a flight and its cheapest day), so the result stays short; it
  writes nothing, and its card is the outbound segment's calendar. Its
  refusals are data: `not_served` with the cities, `date_problem` naming the window,
  `cabin_not_offered`, `no_flights` with the nearest days.
- `choose_flights` (`lean/choose.py`) takes `outbound_id`, `return_id`, `cabin`, `travelers`
  and `list_leg` (a leg's flights the caller asks to hear, listed without choosing: the way
  back's before the way out is chosen too, leg by leg being the default, never a rule), each
  optional: the model resolves the caller's pick itself from the options it was given. It
  gives the trip so far: the route and the trip's kind (`trip`, with `trip_msa` beside a Saudi
  reply's), each chosen leg's id, name, aircraft, day, times, length, `nonstop` and fare
  (`book_trip`'s `already_booked` gives the legs booked in the same shape), the travelers, the
  cabin,
  `missing` (the first of it listed again in `listed`, one leg at a time: the outbound's until
  it is chosen, then the return's; `list_leg`'s leg in its place), a full flight's note as
  `find_flights` gives it when a leg listed has one, `lost` (a leg a change left with no seats,
  by its departure time) and, once complete, `total`; a changed cabin or traveler count prices the trip
  again. Its card is the return segment with the outbound pick kept beside it, then the review.
  Its refusals, nothing written: `nothing_listed`, `unknown_id` and `no_seats` with the leg's
  other ids, fares and seats, `cabin_not_offered`. Its description says it books nothing, and
  `book_trip` books: told only that it returns the trip, the model said «حجزت لك» of a trip
  chosen with its total (f-dev-lean-4, f01 and f30, the run's three violations).
- `book_trip` (`lean/book.py`) takes nothing: the booking check, then the store. It gives
  `booked` with its total, the caller having just heard the trip, and the review card
  ending "Booked · Reference ...", and its data holds the reference: the owner ruled on
  2026-11-18 that saying it unasked is fine ("it is not a hard requirement"), after a booking
  result with no reference left f20's caller told there was none (f-dev-lean-4); run F's lean
  `reference` fails only a turn that asks for it and is not answered with it. Else `not_confirmed`,
  `incomplete`, `refused` (the store's reason), `unknown` (a write that did not answer and was
  not found by its request ID) or `already_booked` (the booking and the trip as it was booked,
  never the call's trip changed since, but for its reference).
- `traveler_profile` is today's tool.

**The prompt** (`lean/instructions/en.md` and `ar-SA.md`, about 30 lines each, filled by
`lean/prompt.py`): Saad of T2 Air, the existing names and greeting; speech first, one to three
short sentences, one question at the end, never a list read out, never markdown, never a screen
(D-075). A calendar written in code in the reply's language: today with its weekday, the next 21
days each with its weekday, and the days "this week", "this weekend", "next week" and "next
weekend" cover (the Saudi week Sunday to Saturday, the weekend Friday and Saturday), then the
booking window's last day, any day up to it searched; the model reads every date from it, never a
day the caller did not say, and searches a span for days asked about; in Saudi, the teens said
the Najdi way («…طعش»), a bare number naming a day that day. The defaults (Riyadh, economy, one
traveler) never asked and said in the summary; the return asked only when not said. One leg's
day listed at a time, briefly (its count, its first and last departures, the cheapest by time
and fare, each flight once; the others only when asked; `fares_are` once a call): on a round
trip the way out first, then the way back once it is chosen, as `listed` gives it, and the way
back first when the caller asks about it (`list_leg`). A span by its
departures and its two cheapest days (a span past two weeks, given week by week, by its two
cheapest days and an offer to look at a week). The pick resolved by the model for the leg picked,
asked with the fares only when truly unclear, one of two that fit it alike taken and named. The
trip confirmed in one sentence (the route, each leg's day and time, the cabin, the travelers,
the total choose_flights gives, never a sum of the model's), booked only after any yes; a pick or
change after it made in the same reply and said with its new total; a booking said in a few
words. A trip only chosen is said as chosen, in Saudi words («اخترت لك…», «رحلتك من الرياض
لجدة…»), a booking word («حجزت», «تم الحجز») only once `book_trip` has booked, and the booking
question in each register («تبيني أحجزها؟», «هل أحجزها لك؟»); the failure line's example has its
MSA twin; the reference of the booking just made is read from `traveler_profile` too; and a
caller who asks to go on in the other language gets `switch_language` when the agent has it,
the reply already in that language or not (f10: the call never moved, so its short yes was
answered under the English tag; the talker now tells the session of every switch the tool
makes, agent/turn.py).
Facts only from tool results of this call. The register first:
Najdi to a Saudi caller, MSA in every reply to an MSA caller, short ones too, never a Saudi form
named there, each result's `_msa` field said in place of the one beside it; and the greeting
rule copied from today's instructions. No example copies a line
of a scripted call (D-011; `tests/flight_voice/lean/test_lean_prompt.py`). The calendar is
written when the agent is declared, so a server holds the day it started, and its airline keeps
that day as its today; the library's "Today is" line follows the clock, so the server is restarted
each day and `FLIGHT_VOICE_TODAY` pinned only to today, and each call on a calendar whose day is
not Riyadh's today logs an error (`lean_calendar_stale`).

**Run F's outcome mode** (`poe eval-flights --agent lean`; `evals/lean_call.py` and
`lean_checks.py`): the same scenarios, the lean agent in each play, scored by outcomes. Kept:
`failure`; `violations` (the call's own, each reply plain speech drops, and a booking claimed
before the store held one); `booked` (one booking exactly when the scenario books, holding its
read-back's flights, days, travelers and cabin, for the demo traveler alone, none otherwise);
`reference`; and on each turn `language`, `register`, `stage_note`, `notice`, `max_words` and
`repeat`. Not used: `calls`, `args`, `outcome`, `own_summary`, `said_any`, `said_none`,
`max_options`, `card`, `progress` and `cut_repeat`. Measured, never pass or fail: the caller
turns and the seconds until the booking, and the words the agent said. The library's read-back
moments become the lean agent's: a turn said `when = "closing_question"` is said over the last
clause of the reply before it, its question, once every clause before it has played and those
clauses stated the trip's total (by the booking check's `stated_at`, the total priced from the
play's trip; `TextCall`'s `during="agent_speaking"`), and the call is then moved on until that
reply has ended and the turn was answered, or 2 s passed, so a yes there (f22's «إي», f01's
«إي احجزها») is said where a caller says it and answered as the library answers it (D-116);
when the reply has ended first, or none came, or the total is said in the question's own clause
or not at all, it is said once the agent is silent, so the play never measures a refusal the
agent did not cause. A turn said `when = "read_back"` is said right after the agent's reply,
once it is silent: a yes over a summary that goes on is never answered. A stop at either moment
stops the reply playing. A scenario whose
`asked_again` only makes sense for the read-back counts on its booking alone. The run, its
scorecard and its history line name the agent (`scripted` or `lean`), so the two compare by
scenario.

**Run F's outcome mode, the lead's amendments of 2026-11-18**, registered before any result of
it, for the lean outcome mode alone (the scripted mode and the library's repeat definitions,
D-101, stay as they are; `evals/lean_checks.py` and `lean_repeats.py`). The owner, 2026-11-17:
"do not be too strict on edge cases that it would restrict the agent too much and make it feels
deterministic or robotic"; run F measures Saad, never punishes a natural agent.

1. **`booked`, a tie.** Where the read-back's flight of a leg ties another flight of its route
   on the same day at the same fare in the cabin, read from the airline's own fares (`tied`),
   and the scenario's last pick of that leg is by fare (`cheapest`, `dearest` or `fare`), a
   booking holding either flight passes: f30's "the dearest" on 19 Nov, T2 102 and T2 106 at
   470 each. Everything else in the booking must still match: the other leg, the days, the
   travelers, the cabin, the demo traveler alone. The pick by fare is the builder's reading of
   the amendment, for the lead to confirm: a tie on a leg picked by time, part of day or order
   is a wrong booking (f02's "the earliest", T2 201, ties T2 203 at its fare).
2. **`repeat`, a reply with new facts.** A near repeat (`find_repeat`'s) counts only when the
   two replies hold the same facts: the same number tokens once `normalize_digits` has read
   them (days, times, fares, totals, travelers; "2,290" read as 2290, "09:10" as "9:10"), and
   the same weekday and city words (a city by its airport), read from each reply as written. A
   read-back after a change (f14: one traveler made two, 260 made 520) or a new day's or city's
   listing in the same frame (f25) is not a repeat; an identical repeat always is. Each
   earlier reply is read on its own, so a true repeat of an older reply is still found. "The
   same facts" is read as no new fact: the near repeat goes only when the later reply states a
   number, weekday or city the earlier one did not, so a reply that only leaves a fact out
   (f22's booked trip said again without its arrival time) is still a repeat. The word one
   («واحد») is no fact: mostly a pronoun ("Which one", "one-way", «أي واحد»), and a change of
   travelers moves the total, so "Which one would you like?" for "Which would you like?" is
   still a repeat. Both are the builder's reading, after a review, for the lead to confirm.
3. **`repeat`, the first clause alone.** A match that rests only on a first clause of 3 or more
   words, the whole reply's overlap under the library's near-repeat threshold (0.8), is not a
   repeat: f19's required «ما أقدر أأكد إذا تم الحجز ولا لا» said again with a new sentence.
4. **`max_words`, one unit for every reply.** The words of the reply as written are counted
   (`TextTurn.written`, the talker's clauses as the output guard passed them, digits one word
   each), in every language: the caller hears an English clause cut into several requests
   with its numbers said in words (f29's first reply, over the cap as heard, under it as
   written), where an Arabic one keeps its digits. The cap stays the one the scenario sets (45
   unless it sets another). A lean play's record keeps each turn's reply as written
   (`written`).

**The owner's call of 2026-11-18 (05:57)**, the lean agent's first live test by the owner: "is
there a switch for Najdi call? it is only standard Arabic", and "it confirmed the reservation
before actually reserving it". Two changes, each behind a library setting the app turns on:

1. **Saudi first.** The caller greeted «السلام عليكم. كيف الحال؟» and went on «شوف يا طويل العمر،
   ودي أروح من الرياض إلى القاهرة», «امم، شوف لي الأسبوع الجاي», «إي نعم»: no turn held a form of
   the library's dialect list, so the library read every one as MSA, and Saad answered in MSA
   throughout («إلى أين تودّ السفر؟», «هل تريد حجزها؟»). The app now turns on `words.saudi_first`
   (an `ar-SA` call is Saudi unless the caller's turn plainly speaks MSA, by a short list of
   forms only MSA says, «أريد»، «أودّ»، «هل»، «ماذا»، «الآن»، «سوف»، «أرغب»، «غدًا»، «القادم»،
   «لدي» and the like, never a Najdi caller's «أبي»، «بكرة»، «الجاي»، «عندي»; a turn with
   neither keeps the call's register; once MSA, the call stays MSA until a Saudi form is heard)
   and adds its own forms as `words.dialect` (`caller_register.py`: «ودي»، «الجاي»، «بكرة»،
   «نبي»، «تبغى»، «حقت»، «خلها»، «طويل العمر»، «شوف»), for either agent. Every turn of that call now
   reads Saudi; run F's four MSA scenarios still read MSA at every turn, and three Saudi ones
   whose first turn read MSA (f08, f27, f30) read Saudi from it. Ole5 sets neither, so its
   reading is as it was (GP-18; `tests/ole5_voice/test_caller_register.py`).
2. **No booking claimed before `book_trip` booked.** At the caller's yes the model called
   `find_flights`, `choose_flights` (picking 18:15, though its summary had said 09:30) and
   `book_trip`, which answered `not_confirmed` (the total of the trip as changed had not been
   said), then said «تم حجز رحلتك … الساعة 18:15»; the booking check held, and the trip was
   booked only after the read-back of the next turn. The lean agent declares no action, so the
   library's claim rule (rule A) was off. `book_trip` now declares `LEAN_CLAIMS` as its
   `claims`: the booking's claim phrases (`booking/lines.py`'s `CLAIMS`) and the rewordings
   of them a model writes that they miss (`REWORDED`: «حجزتها», «تم حجزها», «تم حجزه»,
   «حجزت رحلتك», «تم تأكيد حجزك», "you're all booked", "I've got you booked", "your
   flight's booked" and the like; none sits in a negative but after ma, which the guard
   reads, and never «محجوزة» alone, since «الرحلة محجوزة بالكامل» says a flight is sold out).
   Its `booked` and `already_booked` results are `done` (`ToolResult.done`), so rule A holds
   those phrases to them as an action's are held to its record: «تم حجز رحلتك» is said only
   once this call's booking was made. The library's default phrases are not read for an
   agent that declares no action, so an honest "nothing has been booked yet" is said. A claim it holds back is not answered with the error
   notice: under `guard.retry_claims` the request is sent once more, one past the turn's four,
   with what it said before the claim and a note that the claim was held back, so the model
   says what `book_trip`'s `say` asked (`tests/flight_voice/lean/test_lean_claims.py`). The
   booking check is unchanged. Run F's `notice` check still counts the blocked clause of such a
   turn, a defect of the model's, and its `violations` a claim the guard lets pass ("is all
   set", which the outcome check reads wider than the guard).
