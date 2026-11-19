# Hosting the flight assistant (internal alpha)

How to serve Saad, the T2 flight assistant, to the company's users over the internet: real
flights from SerpApi, the booking link on the card, no access code, and every call kept in a
local database for learning and debugging. This is the alpha's setup, one server and one process; [serving.md](../../docs/guide/serving.md)
says how the library serves calls in general.

## What the server needs

- **A server with a public address**, Linux preferred (Windows works), and a DNS name for it,
  e.g. `flights.example.com`. Run the process on the host itself, not behind a container's
  NAT (with Docker, `--network host`).
- **A TURN server beside it (coturn)**, so a call works from any network. A call's audio is
  WebRTC: the browser and the server first try UDP directly; a browser behind a strict NAT, or
  on a network that lets only web traffic out (hotels, many offices), reaches the server through
  TURN, which relays the audio over UDP, TCP, or TLS on port 443, wherever HTTPS passes. The
  server mints each call's TURN password from a secret it shares with coturn (D-128); see "TURN"
  below. Open on the server: TCP 443 (the page), UDP and TCP 3478 and TCP 5349 (TURN), and UDP
  49152-65535 (the relayed and direct media).
- **HTTPS in front of it.** A browser gives a page the microphone only on `https://` (or on
  `localhost`). Put a reverse proxy with a certificate for the name (Caddy, which gets one by
  itself, or nginx) in front of `http://127.0.0.1:7862`, passing every path (`/`, `/token`,
  `/api/...`, `/voice/...`). With Caddy, the whole `Caddyfile` is
  `flights.example.com { reverse_proxy 127.0.0.1:7862 }`.
- **Python 3.12 and [uv](https://docs.astral.sh/uv/)**, and git (the call log stamps each call
  with the commit it ran).
- **Outbound HTTPS** to Groq (the talker's model and the voice), ElevenLabs (speech-to-text) and
  SerpApi (flights).
- **Disk** for the call log: a call's recording is about 4 to 6 MB a minute (the caller's and
  the agent's audio as WAV), plus a few kilobytes of database rows.

## Install

```bash
git clone <the repository> t2-agentic-voice
cd t2-agentic-voice
uv sync --all-packages
```

## Settings

The owner writes the settings this laptop runs with, secrets left blank, for the server's
manager (never `.env` itself):

```bash
uv run --offline python -m flight_voice.hosting --env-file .env --out alpha.env
```

`alpha.env` lists every setting this laptop gives, each secret (`T2V_GROQ__API_KEY`,
`T2V_ELEVENLABS__API_KEY`, `FLIGHT_VOICE_SERPAPI_KEY`, `FLIGHT_VOICE_ACCESS_CODE`,
`T2V_JOIN__KEYS`) as a blank line under a note. The owner gives the secrets to the manager the
company's way for secrets; the manager writes them into the server's own `.env` beside the rest
(`.env` is never committed). A key may also be a new one made for the server (a new Groq,
ElevenLabs or SerpApi key on the same account), so the laptop's stay the laptop's.

Then set, or change, these for the server:

| Setting | For the alpha |
| --- | --- |
| `FLIGHT_VOICE_AGENT` | `lean` (Saad) |
| `FLIGHT_VOICE_FLIGHT_DATA` | `serpapi` (real flights; needs `FLIGHT_VOICE_SERPAPI_KEY`) |
| `T2V_ENV` | `staging` (not `dev`: no test console, no dev caller) |
| `T2V_SERVER__DEV_PAGE` | `false` |
| `T2V_SERVER__PUBLIC_URL` | the address users open, e.g. `https://flights.t2.internal` |
| `T2V_SERVER__FORWARDED_ALLOW_IPS` | the proxy's address, e.g. `["127.0.0.1"]` |
| `T2V_STORAGE__VAR_DIR` | where the server keeps its data (default `var/` in the checkout) |
| `FLIGHT_VOICE_ACCESS_CODE` | leave it unset: the page asks no code and anyone with the address can call (D-129). Set it to require a code |
| `FLIGHT_VOICE_TOKENS_PER_DAY` | the most calls a day across all users (200 by default, the alpha's): with no code, the cap on what the keys spend |
| `T2V_SERVER__ICE_SERVERS`, `T2V_SERVER__TURN_SECRET` | the TURN server's URLs and its shared secret (see "TURN") |
| `T2V_JOIN__KEYS`, `T2V_JOIN__CURRENT_KID` | a new signing key for the server's join tokens, e.g. `{"k1": "<40+ random bytes>"}` and `k1` |

Leave the rest as `alpha.env` gives them, so the server speaks, hears and searches as the
laptop does: the talker (`openai/gpt-oss-120b` on Groq), speech-to-text (ElevenLabs Scribe),
the voice (Groq's Orpheus, set by the app), Najdi Arabic held for the whole call, and the call
log and recording on (both the app's defaults).

## Run

```bash
uv run poe flight
```

`poe flight` sets `FLIGHT_VOICE_AGENT=lean` and `FLIGHT_VOICE_FLIGHT_DATA=serpapi` and runs
`python -m flight_voice.server --env-file .env` on 127.0.0.1:7862 (add `--host` or `--port` after
it to change them). Without those two settings the server runs the older scripted demo on the
mock airline (the page that greets "Khalid").

One process, one worker (the calls live in its memory). Run it as a service (systemd, NSSM or
the Task Scheduler) that restarts it each night and on failure: the assistant's calendar is
written for the day it starts. It refuses to start, naming the setting, when one is missing or
wrong; `uv run t2v doctor` checks the keys and the voices first.

## TURN (coturn)

Install coturn (`apt install coturn` on Debian or Ubuntu) and give it a certificate for its name
(the page's certificate works when TURN shares the name). `/etc/turnserver.conf`:

```
listening-port=3478
tls-listening-port=5349
fingerprint
use-auth-secret
static-auth-secret=<the same secret as T2V_SERVER__TURN_SECRET>
realm=flights.example.com
cert=/etc/letsencrypt/live/flights.example.com/fullchain.pem
pkey=/etc/letsencrypt/live/flights.example.com/privkey.pem
min-port=49152
max-port=65535
no-cli
```

Then in the server's `.env` (the secret at least 32 random bytes, e.g. `openssl rand -base64 48`):

```
T2V_SERVER__ICE_SERVERS=["stun:flights.example.com:3478","turn:flights.example.com:3478?transport=udp","turn:flights.example.com:3478?transport=tcp","turns:flights.example.com:5349?transport=tcp"]
T2V_SERVER__TURN_SECRET=<the secret>
```

Each call's browser gets a user name and password valid for an hour (`T2V_SERVER__TURN_TTL_S`).
To pass networks that allow only port 443, give coturn its own address and `tls-listening-port=443`,
and use `turns:<that name>:443?transport=tcp`. Test from outside the company with
[Trickle ICE](https://webrtc.github.io/samples/src/content/peerconnection/trickle-ice/): a
`relay` candidate means TURN works.

## The call log

Every call is kept in `var/flight/calls.sqlite3` (under `T2V_STORAGE__VAR_DIR`), and its audio,
when the caller left recording on (on by default; the page says so, and Options turns it off),
in `var/flight/recordings/<call ID>/` (`caller.wav`, `agent.wav`, `timeline.jsonl`):

| Table | One row per |
| --- | --- |
| `calls` | call: start, end, why it ended, the agent and the setup it ran on (models, voice, flight source, commit), the whole report, the recording's folder |
| `events` | event of a call, in order, whole as JSON: what was heard, each reply and how much played, each tool call and result, interruptions, guard blocks, provider failures, each turn's times |
| `turns` | turn: language, what was heard and said, and its times (time to first audio, speech-to-text, the model's first token, the voice's first audio) |
| `tool_calls` | tool call: tool, arguments, result, ok, milliseconds |

Read it with any SQLite tool while the server runs (it is in WAL mode), e.g.:

```bash
sqlite3 var/flight/calls.sqlite3 "select call_id, started_at, ended_by, turns, recording from calls order by started_at desc limit 20"
sqlite3 var/flight/calls.sqlite3 "select turn_id, heard, said, ttfa_ms from turns where call_id = '<call ID>' order by turn_id"
```

The database and the recordings hold what users said: keep `var/` on the server, back it up,
and share it only with the team. `FLIGHT_VOICE_CALL_LOG=false` turns the log off, and
`T2V_PRIVACY__RECORD_AUDIO=false` the recordings.

## Checks after starting

1. Open the public address: the page shows «سعد · مساعد الرحلات في تي تو».
2. Start a call (no code), ask for a flight: Saad answers with real flights; the booking link
   appears on the trip card.
3. End the call: `calls`, `turns` and `tool_calls` have its rows, and `recordings/<call ID>/`
   its audio.
4. From a phone on mobile data (outside the company network), call again: it connects through
   TURN.
