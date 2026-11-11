# The browser client

`t2v-client.js` is the library's reference client for the browser: one ES module with no
dependency and no build step, speaking the protocol `t2v/1` ([serving.md](serving.md)). The
runtime serves it at `<prefix>/client/1/t2v-client.js`; a page on another origin may import it
from there or keep a copy on its own site. This page covers the call, its events, Stop and Esc,
the agent's voice lowered while the caller speaks over it, cut captions, the talker's cards and
the `thinking` and `confirming` states, and push-to-talk; and, for engineers, the dev page and
the test console.

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
        state: (s) => state(words().states[s.state] ?? "", s.state),
        caption,
        card,
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
| `state` | `{state}`: `listening`; `thinking`, while a reply asked for has no audio yet (the talker or one of its tools at work) or a turn's transcript is awaited; `speaking` (below, "The agent thinking"); or `confirming`, while an action's read-back waits for the caller's answer and nothing plays ([tools-and-actions.md](tools-and-actions.md)) |
| `caption` | `{speaker, text, final, turn_id, reply_id, clause, cut}`: the caller's turn once heard (`speaker` `caller`, named by `turn_id`), or the agent's reply clause by clause as each starts playing (`agent`, named by `reply_id` and `clause`); `cut` is true for an agent's clause a stop cut while it played, sent again with the mark (below) |
| `card` | `{title, steps, source}`: a reply's whole answer for the screen, its steps a list of text in order (empty when its source lists none) and `source` the document it comes from, `null` when there is none (below, "Cards") |
| `duck` | `{level}`: the caller is speaking over the agent, whose voice now plays at `level` (0 to 1) of its volume until the session decides |
| `unduck` | `{}`: the session has decided, and the agent's voice is back to full volume |
| `volume` | `{level}`: the client changed the agent's volume, 1 at full; the client's own event, sent on each change, whatever caused it |
| `notice` | `{kind, text}`: `error` (a turn's transcript failed, or a reply's speech with none of it heard), `cut_off` (a reply's speech failed after the caller heard some of it, told at the reply's end) or `ended` (the call ended at a limit), its text in the call's language. A talker's failure, or a sentence the output guard held back, is told inside the reply instead: the `error` notice's text, or `cut_off`'s after words already said, said and captioned as one of its clauses |
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

Under the runtime's `interruptions.mode` `two_step`, the default, the caller can stop the agent
by speaking over it ([concepts.md](concepts.md)). As soon as the server hears the caller over a
reply it sends `duck`, and the client plays the agent at `level` times the volume its audio
element had when the call started (the server's `interruptions.duck_level`, 0.25 by default):
the agent keeps talking, quieter, while the server decides from the caller's words whether to
stop. `unduck` follows once it has decided, whatever it decided, and the client plays the agent
at full volume again.

The client also brings the volume back to full on its own `stop()`, on the first caption of a new
reply, and when the call ends, so no reply plays lowered whatever reaches it. Each change is a
`volume` event; the page need do nothing with it, and may show it (the dev page shows a
percentage). If you pass your own `audio` element, the client sets its volume during the call,
from the volume it had at the start. Under the `drop` mode the server sends neither message.

## Cut captions

Under `two_step`, when a stop cuts a clause while it plays (the server's, or the caller's Stop
button or Esc), the server sends that clause's caption again with `cut: true`. Show it as cut:
the caller heard only its start. Ole5's widget shows a cut clause muted and ended by an ellipsis,
keeping each clause in an element of its own so the mark lands on the right one. A caller's
caption is never cut.

## Cards

A talker's reply says its answer short aloud, one to three spoken sentences, and sends the whole
to the screen as a `card`: a title, its steps in order, and the document they come from. The
knowledge tool shows the passage that answers best as one, when it lists steps; a tool of your
own shows one by returning a `ToolResult` with a `card` ([concepts.md](concepts.md), "Cards").
The session sends a card only once the output guard has read its text, as it reads a clause's.

The client hands the page each card as one `card` event, and drops a message that is not one
(no title, steps that are not text). Show it beside the captions, a new card in place of the
last, and every text as text (`textContent`): a passage's steps are the knowledge base's words,
not your page's. Ole5's widget shows the card above the captions, so the captions growing below
never move it, with its steps numbered and each line in the direction of its own first strong
character (`dir="auto"`): an Arabic step reads right to left and an English one left to right,
in a call of either language. A new call clears it. Its card, in
[widget.js](../../apps/ole5-voice-agent/web/widget.js):

```js
// The newest card in place of the last, or none (`null`, a new call's).
function card(c) {
  const steps = (c?.steps ?? []).map((text) => {
    const step = document.createElement("li");
    step.dir = "auto";
    step.textContent = text;
    return step;
  });
  $("card-title").textContent = c?.title ?? "";
  $("card-steps").replaceChildren(...steps);
  $("card-source-name").textContent = c?.source ?? "";
  $("card-source").hidden = !c?.source;
  $("card").hidden = !c;
}
```

## The agent thinking

`state` is `thinking` while a reply has been asked for and has no audio yet: the talker waiting
on the model, a tool running with nothing left to play, or a turn's transcript still to come.
It turns `speaking` when the reply's first audio plays, and back to `thinking` when the reply has
played all it has while the model still writes or a tool still runs; `listening` once it is
done. A search whose answer takes long gets a progress line ("Let me check the guide."),
which plays as `speaking`. Show it plainly: Ole5's widget says "Thinking" («يفكر») beside a
pulsing dot, so a caller who hears nothing for a second knows the agent is at work.

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
call's state (`thinking` while the talker or a tool works), the agent's volume, the newest card
above the captions (its title, its steps numbered, its source), its captions (a clause a stop cut
marked `[cut]`) and its notices. It loads only the client, and answers only under `env` dev,
with the dev page on, to a browser on the same machine ([quickstart.md](quickstart.md)).

## The test console

`<prefix>/dev/console` is a page for the engineers who test an agent (D-083): every call on the
runtime, turn by turn, read from the runtime's own events. It comes with the dev page, so `t2v
dev` serves it, and so does an app's server under `env` dev with `T2V_SERVER__DEV_PAGE=true`: for
Ole5, `http://127.0.0.1:7861/voice/dev/console`. It shows calls made from any page on that
runtime, and can make its own.

To start a call from the console, leave **Join token** empty and press **Start call**. When your
app declares a dev caller (below), the console makes a signed join token for that caller
(`POST dev/token`) and joins with it: the same kind of token your own page gets, verified once
by your identity source, so the call runs as one from your page. It needs no access code, and
your app's own limits never count it. When the app declares none, or the server holds no join key
that signs (`T2V_JOIN__KEYS` and `T2V_JOIN__CURRENT_KID`), the console joins with `dev`, which
`t2v dev` takes. Under `t2v dev` with no identity source of your own, `DevIdentity` takes any
token and always gives the caller `dev` and a consent that keeps no audio, so the dev caller
shows only on a server that verifies signed tokens, as Ole5's does. A token typed in the field
is used as typed. **Keep the call's audio**, off
unless ticked, is the consent the console's token carries; the audio is kept only when
`privacy.record_audio` is on too ([data-and-privacy.md](data-and-privacy.md)).

The dev caller is `server.dev_caller`: a caller of your app's, its subject and its attributes,
which nothing in a request can change. Declare it in code:

```python
settings = VoiceSettings.from_env(
    server={"dev_caller": {"subject": "tester", "attributes": {"department": "support"}}}
)
```

or as JSON in `T2V_SERVER__DEV_CALLER`. It is read only under `env` dev with the dev page on.
Ole5 declares its demo customer under `env` dev, so a call the console starts makes and reads
that customer's tickets, as a call from the widget does: open the console with `T2V_ENV=dev`
and `T2V_SERVER__DEV_PAGE=true`, leave the token empty and press Start.

For each turn it shows:

- what speech-to-text heard;
- the time of each step from the end of the caller's speech, as numbers and as bars: Smart
  Turn's "complete", the end of the turn, the transcript, the model's first token, a progress
  line, the first audio (the time to first audio) and its playback in the browser; Whisper's and
  Orpheus's own times; and the time the tools took ([latency.md](latency.md));
- each tool call: its name, whether it succeeded or what failed, how long it ran, the arguments
  the model wrote and what the tool returned;
- an action's read-back with the draft it read, the yes rule's decision and whether its lists
  (`words`) or the model decided, and the write: done, failed or unknown, how long after the
  yes, and the write's result (for Ole5, the ticket's number);
- what the agent said, how much of it played, interruptions and what decided them, guard
  blocks and provider failures; and the requests and tokens the turn used.

Beside the turns: the call's median and worst time to first audio, each model's usage, the record
of completed actions, the connection and how the call ended; under them, every event in order,
filtered by kind. **Export JSON** saves the call's events, with the agent's setup, to attach to a
bug report. **Setup** shows what the agent runs with: its tools and actions, its languages, its
models and voices, and the settings that shape a turn's timing, with no secret.

The page reads `GET dev/feed?after=N`, which answers once a new event comes, or after 10 s with
none. The runtime saves every call's events, since these are development calls: one JSON line
per event in `dev-console/<call ID>.jsonl` under the data folder (`storage.var_dir`), which
nothing deletes, so delete the folder to clear it. After a restart the console shows the
newest 20 calls again, read back from there; the page holds the last 20 calls, and the files
hold them all. None of it goes to a log. Since the events hold what callers said and what tools
returned, and its token starts a call as your dev caller, every route of the console answers
only under `env` dev, to a browser on this machine that names it `localhost`, `127.0.0.1` or
`[::1]`; any other request gets a plain 404. The token itself never goes to a log: the line
`dev_token_minted` says only whether its consent keeps the audio.
