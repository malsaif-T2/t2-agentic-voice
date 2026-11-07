# Data and privacy

What the library itself stores and sends during a call, so a team can say what happens to its
callers' voices and words. Groq's own terms (what it keeps, and where) are not covered here: the
owner explains them to each team that adopts the library, and whether they suit your data is your
team's call (D-018). The rules behind this page are [SECURITY.md](../SECURITY.md)'s invariants,
8 (audio is kept only with consent) above all.

## What it stores

Everything the library keeps is under one data folder, `storage.var_dir` (`var` by default,
relative to the working folder), on the machine that runs the runtime. It deletes none of it:
there is no purge command yet.

| Under `var_dir` | What it holds | Call content |
| --- | --- | --- |
| `runtime.lock` | The lock that keeps one process on the folder | None |
| `<agent name>/phrases/` | The audio of the agent's fixed phrases (each language's greeting, echo frame, spoken notices and its tools' progress lines), synthesized once at start | None: words heard in a call are never cached |
| `<agent name>/used_tokens.sqlite3` | Each used join token's ID (`jti`) and the last instant it could verify, pruned after that instant | None |
| `reports/<call ID>.json` | Each call's report in numbers: when it started and ended and why, its turns' outcomes and times, each model's usage, the browser's connection type and timings, the consent version | None: no word heard or said |
| `recordings/<call ID>/` | Only when recording is allowed (below): `caller.wav`, `agent.wav`, and `timeline.jsonl`, which holds the words heard and each clause's text | All of it |

Logs hold no call content at INFO and above, and `logging.content`, which lets lines with
addresses and SDP through, is refused outside `env` dev ([tracing-and-logs.md](tracing-and-logs.md)).
The full report, with what was heard and said, goes only to your own code, in the process: an
observer of `CallEnded` (`@runtime.on(CallEnded)`, from the `events` facade).

## Recording, and the consent behind it

A call's audio is stored only when **both** allow it:

- **the setting** `privacy.record_audio` is on (it is off by default), and
- **the caller's consent**, carried in a signed join token that the runtime verified, says
  `record_audio: true`.

Both are read once, as the call starts; nothing said or sent in the call can turn recording on.
A consent built anywhere else, the dev caller's or one from a verifier of your own, never lets a
call be recorded. So a page shows its consent screen before the call, and passes the consent
text's version and the caller's recording choice to whatever mints the token
([browser-client.md](browser-client.md)); with `privacy.consent_version` set, `/join` refuses a
token whose consent names another version ([serving.md](serving.md)). The version is stamped
on the call's report and traces.

## What it sends

| To | What |
| --- | --- |
| Groq (`groq.base_url`, `https://api.groq.com` by default) | Each caller turn's audio, one Whisper request a turn (at most 30 s); with a talker, one to three chat requests a turn, each holding the system prompt (your instructions among it), the call as the caller heard it, the turn's words, your tools' schemas and their results of the last 4 turns; the text the agent says, in Orpheus requests (the echo sends back the words it heard); the fixed phrases, once, at the first start; the key, with each request |
| Your trace backend (`tracing.endpoint`), or your own tracer provider | The spans of each turn and call, with the transcripts unless `tracing.include_transcripts` is off, after `tracing.redact`'s patterns: never audio or a secret ([tracing-and-logs.md](tracing-and-logs.md)) |
| The caller's browser | The agent's audio over WebRTC, and the captions, state, cards and notices on the data channel |

Nothing else: the library contacts no STUN server unless `server.ice_servers` names one, and
sends nothing home. Your tools and your knowledge base adapter are your app's code: what they
reach is yours to say, and what they return goes to the chat model as data, and to the caller's
screen when it is a card. The browser's audio goes straight to your backend over WebRTC, with no
media server between.

## How long Phoenix keeps transcripts

Traces carry what callers said by default, and Phoenix keeps them **forever unless a retention
is set**: `PHOENIX_DEFAULT_RETENTION_POLICY_DAYS` is 0 by default, which means no limit. Set it
where Phoenix runs, or turn transcripts off with `T2V_TRACING__INCLUDE_TRANSCRIPTS=false`.

**For Ole5's owner tests** (the owner's ruling of 2026-11-03): the traces go to the local
Phoenix plan 002 ran on this laptop, on 127.0.0.1, with no retention setting, so they are kept
until the owner deletes the project. A test call the owner chooses to record, in the widget's recording box, is kept
under `var/` on this laptop until the owner deletes it.
