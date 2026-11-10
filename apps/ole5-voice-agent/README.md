# Ole5 Voice Agent

The first app built on T2 Agentic Voice: a voice assistant for Ole5's users that answers from
Ole5's knowledge base, in Saudi Arabic, MSA and English. It uses only the library's public API.

## Try it on this machine

**Once, in the `.env` at the repository's root** (never committed):

| Name | What it is |
| --- | --- |
| `T2V_GROQ__API_KEY` | The Groq key: speech-to-text, the chat model and the voice. |
| `QDRANT_URL`, `QDRANT_LOGIN_EMAIL`, `QDRANT_LOGIN_PASSWORD` | Ole5's knowledge base. With none of the three set, the agent is the echo, which says your words back. |
| `OLE5_VOICE_ACCESS_CODE` | The code the widget asks for before a call. |
| `T2V_JOIN__KEYS`, `T2V_JOIN__CURRENT_KID` | The key that signs a call's join token: `T2V_JOIN__KEYS={"key-1": "<secret>"}` and `T2V_JOIN__CURRENT_KID=key-1`. |

A secret for the join key, at least 32 characters, from:

```bash
uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Each time**, from the repository's root:

```bash
uv run python -m ole5_voice.server --env-file .env
```

It is ready when it logs `knowledge_base_set agent=talker` and `Uvicorn running on
http://127.0.0.1:7861`; its first start takes about 15 s while it records the fixed lines it
speaks. `--port` serves another port.

**Then**, in Chrome or Edge on the same machine, open http://127.0.0.1:7861/:

1. Pick العربية or English. Ask English questions in an English call: Whisper is told the
   call's language, and English words in an Arabic call are written as Arabic.
2. Give the access code, tick the box only if the call's audio should be kept, and allow the
   microphone.
3. Ask about Ole5. While it searches it shows "Thinking", and it says the steps aloud. Say «وقف» or "stop" to stop it, «لحظة» to make it wait, «ممكن تعيد؟» to
   hear its answer again.

**To stop it**, press Ctrl+C in the terminal that runs it. Each call costs a few cents of Groq.

To see each call's steps and times, start Phoenix on this machine and set
`T2V_TRACING__ENDPOINT` to it before starting the server ([the guide's tracing and
logs](../../docs/guide/tracing-and-logs.md)).

## The mock ticket system

The app has no real ticket system: its tickets go to a mock that keeps them across restarts in
`ole5/tickets/tickets.json` under the library's runtime folder (`T2V_STORAGE__VAR_DIR`, `var/`
unless set).
Its numbers have the real shape, 16 digits: the date, `82` and a counter. To see what the calls
made, open http://127.0.0.1:7861/tickets on the same machine (it answers no other); it lists
every ticket, newest first, and reloads itself every few seconds. Nothing on it can change a
ticket. These settings, in the same `.env`, are optional:

| Name | What it is |
| --- | --- |
| `OLE5_VOICE_DEMO_CUSTOMER_EMAIL` | The customer every call is, whose tickets it makes and reads; `ole5.test@example.com` unless set. Nothing said in a call changes it. |
| `OLE5_VOICE_TICKETS_MODE` | How the mock answers each write: `answer` (the default), `refuse`, `timeout` (no answer, nothing done) or `late` (done, the answer after 30 s), to hear how the agent handles each. |
| `OLE5_VOICE_TICKETS_LOOKUP` | `false` makes the mock unable to find a write by its request ID, as the real system is thought to be; `true` unless set. |
| `OLE5_VOICE_TICKETS_DIR` | Another folder for the mock's tickets. |

## Tickets in a call

With the knowledge base set, the agent can also open a ticket on the mock, add a note to a
ticket it opened in the same call, pass a request for a person to the support team as a
ticket, and say the status of the tickets it opened for you. It asks only what is wrong and
how urgent it is, reads the ticket back, and asks «تبيني أرسلها؟» or "Shall I send it?"; a
caller who speaks MSA hears the read-back and what follows it in MSA, the question «هل
أرسلها؟». It is sent only on a clear yes after the whole read-back: say «نعم أرسلها» or "yes,
send it" over the question, or a plain yes once it has ended; a plain yes over the question is
asked again, and a stop word over the read-back stops it with nothing sent. Once the ticket is
made it says the whole number, in four groups of four digits; a status says only the last four.
A number said as your ticket number («رقم تذكرتك», "your ticket number is") is held back unless
a ticket was made or found in the call, and then it must be that ticket's. Asking for a person
makes a ticket for the support team with what both of you said in the call; nobody joins the
call.
