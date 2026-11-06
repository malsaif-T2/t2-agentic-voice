# The browser client

`t2v-client.js` is the library's reference client for the browser: one ES module with no
dependency and no build step, speaking the protocol `t2v/1` ([serving.md](serving.md)). The
runtime serves it at `<prefix>/client/1/t2v-client.js`; a page on another origin may import it
from there or keep a copy on its own site. This page covers what M2 and M3 build: the call, its
events, Stop and Esc, the agent's voice lowered while the caller speaks over it, cut captions and
push-to-talk. The `confirming` state and cards come with confirmed actions in M5.

## Starting a call

Call `VoiceClient.start(options)` inside the click that starts the call, so the browser lets the
page play the agent's audio. It resolves with the call, or rejects with a `VoiceClientError`.

| Option | What it is |
| --- | --- |
| `base` | The router's address: `"/voice"` on the same origin, or a full URL |
| `token` or `getToken` | A join token, or an async function that returns one |
| `language` | Optional: the caller's pick, `ar-SA`, `ar` or `en`; with none, the token's `locale`, then the agent's first language |
| `on` | Listeners by event name (below) |
| `audio` | Optional: an `<audio>` element to play the agent in; a new one otherwise |
| `escape` | `false` leaves Esc unbound |
| `pushToTalk` | `true` starts the call with push-to-talk on (below); off otherwise |

It opens the microphone first, with the browser's echo cancellation, noise suppression and gain
control, and only then asks `getToken` for a token, so a missing, busy or refused microphone
spends no token. Then it joins, sends its offer, and sends its ICE candidates once the offer is
answered. The Ole5 widget starts its call so, in
[widget.js](../../apps/ole5-voice-agent/web/widget.js) (a JavaScript sample, which `poe docs`
does not compare with its file):

```js
    const call = await VoiceClient.start({
      base: "voice",
      language: page.language,
      getToken: token,
      pushToTalk: $("push-to-talk").checked,
      on: {
        state: (s) => state(words().states[s.state] ?? ""),
        caption,
        notice: (n) => message(n.text),
        ended,
      },
    });
```

## Events

`call.on(name, listener)` adds a listener and returns a function that removes it; a listener
that throws is logged to the console and the others still run.

| Event | What the listener gets |
| --- | --- |
| `hello` | `{call_id, languages}`, once the data channel opens: the call's languages, its own first |
| `state` | `{state}`: `listening`, `thinking` or `speaking` |
| `caption` | `{speaker, text, final, turn_id, reply_id, clause, cut}`: the caller's turn once heard (`speaker` `caller`, named by `turn_id`), or the agent's reply clause by clause as each starts playing (`agent`, named by `reply_id` and `clause`); `cut` is true for an agent's clause a stop cut while it played, sent again with the mark (below) |
| `duck` | `{level}`: the caller is speaking over the agent, whose voice now plays at `level` (0 to 1) of its volume until the session decides |
| `unduck` | `{}`: the session has decided, and the agent's voice is back to full volume |
| `volume` | `{level}`: the client changed the agent's volume, 1 at full; the client's own event, sent on each change, whatever caused it |
| `notice` | `{kind, text}`: `error` (a turn or an echo failed) or `ended` (the call ended at a limit), its text in the call's language |
| `ended` | `{reason}`: `hangup`, `caller_left`, `max_call`, `idle`, `transport` or `server` |
| `connection` | `{state}`: the peer connection's state as the browser reports it |
| `error` | A `VoiceClientError` from sending candidates, while the call goes on |

Show every text the session sends as text (`textContent`), never as HTML: captions hold what
the caller said.

## Stop, Esc and hanging up

- `call.stop()` makes the agent drop what it was saying and listen again, its voice back at full
  volume: the Stop button. Esc does the same unless `escape: false`.
- `call.hangup()` ends the call; the session says so with `ended`, or the call closes after
  3 s.
- `call.closed` says whether the call has ended; `call.callId` and `call.languages` are set as
  the call starts.

## The agent's voice lowered while the caller speaks

With the runtime's `interruptions.mode` set to `two_step`, the caller can stop the agent by
speaking over it ([concepts.md](concepts.md)). As soon as the server hears the caller over a
reply it sends `duck`, and the client plays the agent at `level` times the volume its audio
element had when the call started (the server's `interruptions.duck_level`, 0.25 by default):
the agent keeps talking, quieter, while the server decides from the caller's words whether to
stop. `unduck` follows once it has decided, whatever it decided, and the client plays the agent
at full volume again.

The client also brings the volume back to full on its own `stop()`, on the first caption of a new
reply, and when the call ends, so no reply plays lowered whatever reaches it. Each change is a
`volume` event; the page need do nothing with it, and may show it (the dev page shows a
percentage). If you pass your own `audio` element, the client sets its volume during the call,
from the volume it had at the start. Under the default `drop` mode the server sends neither
message.

## Cut captions

Under `two_step`, when a stop cuts a clause while it plays (the server's, or the caller's Stop
button or Esc), the server sends that clause's caption again with `cut: true`. Show it as cut:
the caller heard only its start. Ole5's widget shows a cut clause muted and ended by an ellipsis,
keeping each clause in an element of its own so the mark lands on the right one. A caller's
caption is never cut.

## Push-to-talk

When the agent's voice comes back through a laptop's speakers past the browser's echo
cancellation, push-to-talk keeps the microphone off except while the caller holds a key or a
button. It is off by default:

- `pushToTalk: true` among the options starts the call with it on; the `call.pushToTalk`
  property turns it on or off during the call, and lets go of any hold.
- `call.talk(true)` as the page's key or button goes down, and `call.talk(false)` as it comes up.
  While push-to-talk is on, the microphone's track sends sound only between the two, and silence
  otherwise; the call goes on either way. With it off, `talk` changes nothing.

The server is not told: it hears silence while nothing is held. Ole5's widget has a switch the
caller turns on before or during the call, then holds Space or a Talk button to speak. It sets
`call.pushToTalk` from the switch again once `start` resolves, in case it was flipped while the
call started; the button is usable only once the call exists, so a hold begun while the call
starts is not lost; and the hold ends when the window loses focus. Its hold, in
[widget.js](../../apps/ole5-voice-agent/web/widget.js):

```js
// Push-to-talk's hold: the microphone on while Space or the talk button is held.
function talk(held) {
  $("talk").setAttribute("aria-pressed", String(held));
  page.call?.talk(held);
}

// Space holds the microphone open while push-to-talk is on, and then neither clicks a focused
// button nor flips the switch.
function space(event) {
  if (event.code !== "Space" || !page.call || !$("push-to-talk").checked) return;
  event.preventDefault();
  if (event.type === "keyup") talk(false);
  else if (!event.repeat) talk(true);
}
```

## Errors

A `VoiceClientError` has a `code`, a `message`, and, from the server, its HTTP `status`, a
`notice` to show (a client of another protocol version gets one) and a `reference` the server
logged. Its codes are the server's (`join_rejected`, `protocol_mismatch`, `forbidden` and the
rest: [serving.md](serving.md)) or the client's own:

| Code | Why |
| --- | --- |
| `microphone_missing` | No microphone was found |
| `microphone_busy` | Another program holds the microphone |
| `microphone_refused` | The browser refused the page the microphone |
| `microphone_failed` | It could not be opened, or the page is not HTTPS or this machine's own address |
| `network` | The voice server could not be reached |
| `no_token` | `getToken` gave no token |
| `ended` | The call ended while it was starting |

## Tokens and consent

Your page shows its consent screen before the call starts, then passes the consent text's
version and the caller's recording choice to whatever mints the token: your own route, behind
your sign-in. The token carries the consent, and no later message can change it. The Ole5
widget's `getToken` asks its token route for one, sending the owner's access code and the
consent its screen recorded, in
[widget.js](../../apps/ole5-voice-agent/web/widget.js):

```js
    response = await fetch("token", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        code: $("code").value,
        consent: { version: CONSENT_VERSION, record_audio: $("record").checked },
      }),
      cache: "no-store",
    });
```

## What the client reports

Once connected, the client sends `client_stats` (the selected candidate's type, the time to
connect, whether echo cancellation applied) and again when the first audio plays, and a
`playback` report as each clause of the agent's reply starts and ends playing, read from the
level of the agent's audio. The session keeps them in the call's report; the page does nothing
for them.

## Browsers

Chrome and Edge are the supported browsers (D-018). A page needs a secure context to open a
microphone: HTTPS, or `localhost` or `127.0.0.1` on the caller's own machine.

## The dev page

`<prefix>/dev` is a call page with no code of its own: a join token field (any text for the dev
caller), a language, Start, Stop and Hang up, push-to-talk (a switch and a Talk button held), the
call's state, the agent's volume, its captions (a clause a stop cut marked `[cut]`) and its
notices. It loads only the client, and answers only under `env` dev, with the dev page on, to a
browser on the same machine ([quickstart.md](quickstart.md)).
