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
| `src/flight_voice/airline/` | The mock airline: its ten airports, with their names in both languages, the names a caller may give each and a fixed offset from UTC. |

Everything in the mock airline is fixed data or computed from fixed data, so the same inputs give
the same answer on every run and a call's facts are checked in code. Its tests are in
`tests/flight_voice/`:

```bash
uv run pytest tests/flight_voice
```

The server, its page and its scripted calls come with the next parts of the build; this file
says how to run each one as it lands.
