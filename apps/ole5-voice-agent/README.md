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
2. Agree to the consent screen, give the access code and allow the microphone.
3. Ask about Ole5. While it searches it shows "Thinking"; when the passage it found lists steps,
   they show as a card. Say «وقف» or "stop" to stop it, «لحظة» to make it wait, «ممكن تعيد؟» to
   hear its answer again.

**To stop it**, press Ctrl+C in the terminal that runs it. Each call costs a few cents of Groq.

To see each call's steps and times, start Phoenix on this machine and set
`T2V_TRACING__ENDPOINT` to it before starting the server ([the guide's tracing and
logs](../../docs/guide/tracing-and-logs.md)).
