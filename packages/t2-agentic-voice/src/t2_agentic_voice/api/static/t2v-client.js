// t2v-client.js: the reference browser client of T2 Agentic Voice, speaking its wire protocol
// t2v/1 (the package design's 5.5). One ES module with no dependency and no build step: copy it
// to a site, or import it from a backend's `<prefix>/client/1/t2v-client.js`.
//
//   import { VoiceClient } from "/voice/client/1/t2v-client.js";
//   startButton.onclick = async () => {
//     const call = await VoiceClient.start({ base: "/voice", getToken, language: "ar-SA" });
//     call.on("caption", (c) => show(c.speaker, c.text, c.final, c.cut));
//     call.on("state", (s) => status(s.state));     // listening | thinking | speaking | confirming
//     call.on("notice", (n) => tell(n.kind, n.text)); // busy | error | ended, in the call's language
//     call.on("ended", (e) => done(e.reason));
//     stopButton.onclick = () => call.stop();        // Esc is bound too
//     endButton.onclick = () => call.hangup();
//     talkButton.onpointerdown = () => call.talk(true); // with { pushToTalk: true }
//     talkButton.onpointerup = () => call.talk(false);
//   };
//
// `start` runs inside the click that starts the call, so the page may play the agent's audio. It
// opens the microphone first, with the browser's echo cancellation, and asks `getToken` for a
// join token only once the microphone is open, so a missing, busy or refused microphone spends
// no token. Then it joins (POST <base>/join), offers (POST <base>/offer) and sends its ICE
// candidates (PATCH <base>/offer) only once the offer is answered, the last PATCH an empty
// candidate that marks their end. Every body goes as application/json, the offer secret in the
// body, never in a URL. A PATCH's quiet 409 (the call's ICE completed, or the call ended) is
// ignored. A failure is a `VoiceClientError` with a `code`: the server's (`join_rejected`,
// `protocol_mismatch` with the `notice` its page shows, ...) or the client's own
// (`microphone_missing`, `microphone_busy`, `microphone_refused`, `microphone_failed`,
// `network`, `no_token`).
//
// On the data channel every message is a JSON object with "v": 1 and a type from t2v/1's closed
// list; SmallWebRTC's own `signalling` messages are left alone, and no raw text starting with
// "ping", its keep-alive, is ever sent. Once connected the client sends `client_stats` (the
// selected candidate's type, and for a relay its protocol and the TURN server's port; the time
// to connect; whether echo cancellation applied), again when the first audio plays, and a
// `playback` report as each clause of the agent's reply starts and ends, read from the level of
// the agent's audio. Text from the session is handed to the page as it came: a page shows it
// with `textContent`, never as HTML.
//
// While the caller speaks over a reply, the session lowers the agent's voice (`duck`, to its
// level of the volume the call started at) and brings it back once that overlap is decided
// (`unduck`). The volume also comes back to full on the client's own `stop()`, on a new reply's
// first caption and when the call ends, so no reply plays lowered whatever reaches the client;
// each change is a `volume` event. A clause a stop cut while it played comes again as a caption
// marked `cut`, which the page shows as cut. Push-to-talk, off by default (`pushToTalk: true`, or
// the property during the call), sends the microphone's sound only while the page holds it,
// from `talk(true)` to `talk(false)`: the fallback when the agent's voice comes back through a
// laptop's speakers.
//
// The dev page (`<prefix>/dev`) loads this module alone and holds no script of its own, so any
// Content-Security-Policy the router sends it keeps it working: the module builds that page when
// its root element carries `data-t2v-page="dev"`.

export const PROTOCOL = 1;
export const CLIENT = "t2v-client.js/1.0.0";
// t2v/1's messages by direction (voice/protocol.py): the client sends only the first list's and
// hands the page only the second's.
const CLIENT_MESSAGES = ["hello", "stop", "hangup", "client_stats", "playback"];
const SESSION_MESSAGES = ["hello", "state", "caption", "duck", "unduck", "notice", "ended"];
// SmallWebRTC's own message type on the data channel.
const RESERVED = "signalling";
// The 409s a PATCH gets once the call has moved on, which the client ignores.
const QUIET = ["not_offered", "ice_completed", "call_ended"];
const JSON_TYPE = "application/json";
const MAX_CANDIDATES = 64; // in one PATCH, as the server takes them
const CANDIDATE_TYPES = ["host", "srflx", "prflx", "relay"];
const RELAY_PROTOCOLS = ["udp", "tcp", "tls"];
const MAX_MS = 86_400_000; // the longest duration a report holds
const HANGUP_GRACE_MS = 3000; // after a hangup, how long the session has to say the call ended
// The playback watch: how often the agent's audio level is read, the level that counts as sound
// (RMS, about -40 dBFS), how long a quiet stretch ends a clause, and the most captions queued.
const PLAYBACK_TICK_MS = 50;
const PLAYBACK_LEVEL = 0.01;
const PLAYBACK_QUIET_MS = 300;
const MAX_PENDING = 64;
// getUserMedia's errors by name, as the client's codes.
const MICROPHONE = {
  NotFoundError: "microphone_missing",
  OverconstrainedError: "microphone_missing",
  NotReadableError: "microphone_busy",
  AbortError: "microphone_busy",
  NotAllowedError: "microphone_refused",
  SecurityError: "microphone_refused",
};
const MICROPHONE_MESSAGES = {
  microphone_missing: "No microphone was found.",
  microphone_busy: "Another program is using the microphone.",
  microphone_refused: "The browser refused this page the microphone.",
  microphone_failed: "The microphone could not be opened.",
};

export class VoiceClientError extends Error {
  constructor(code, message, details = {}) {
    super(message, details.cause === undefined ? undefined : { cause: details.cause });
    this.name = "VoiceClientError";
    this.code = code;
    this.status = details.status ?? null;
    this.notice = details.notice ?? null;
    this.reference = details.reference ?? null;
  }
}

export class VoiceClient {
  callId = null;
  languages = [];
  #options;
  #base;
  #listeners = new Map();
  #audio;
  #context = null;
  #stream = null;
  #track = null;
  #pc = null;
  #channel = null;
  #secret = null;
  #mid = () => "0";
  #answered = false;
  #queue = [];
  #draining = null;
  #endQueued = false;
  #startedAt = 0;
  #connectedAt = null;
  #firstAudioMs = null;
  #statsRound = 0;
  #playback = null;
  #onKey = null;
  #hangupTimer = null;
  #closed = false;
  // The agent's playback: the audio element's volume at the start (full), the level of it now,
  // and the newest reply captioned.
  #full = 1;
  #level = 1;
  #reply = -1;
  // Push-to-talk: whether it is on, and whether the page holds the microphone open.
  #pushToTalk = false;
  #held = false;

  // Starts a call; see the module's notes. `options`: `base`, the router's address ("/voice");
  // `token` or `getToken`, an async function giving one; `language`, the caller's pick (a t2v/1
  // tag); `on`, listeners by event name; `audio`, an audio element to play the agent in;
  // `escape: false` to leave Esc unbound; `pushToTalk: true` to start with push-to-talk on.
  static async start(options) {
    const call = new VoiceClient(options);
    try {
      await call.#begin();
    } catch (error) {
      call.#finish("failed", true);
      throw error;
    }
    return call;
  }

  constructor(options) {
    if (!options || typeof options.base !== "string") {
      throw new TypeError('VoiceClient needs { base }: the router\'s address, such as "/voice".');
    }
    if (typeof options.token !== "string" && typeof options.getToken !== "function") {
      throw new TypeError("VoiceClient needs a join token, or a getToken function.");
    }
    this.#options = options;
    const base = options.base.endsWith("/") ? options.base : `${options.base}/`;
    this.#base = new URL(base, globalThis.location?.href);
    for (const [name, listener] of Object.entries(options.on ?? {})) this.on(name, listener);
    // Made inside the click that starts the call, before any await: the page may play audio.
    this.#audio = options.audio ?? new Audio();
    this.#audio.autoplay = true;
    this.#full = this.#audio.volume;
    this.#pushToTalk = options.pushToTalk === true;
    if (typeof globalThis.AudioContext === "function") {
      this.#context = new AudioContext();
      this.#context.resume().catch(() => {});
    }
  }

  // Whether the call has ended (its `ended` event came, or it never started).
  get closed() {
    return this.#closed;
  }

  // Listen to an event: hello, state, caption, duck, unduck, volume, notice, ended, connection
  // or error. Returns a function that removes the listener.
  on(name, listener) {
    if (!this.#listeners.has(name)) this.#listeners.set(name, new Set());
    this.#listeners.get(name).add(listener);
    return () => this.#listeners.get(name)?.delete(listener);
  }

  // The Stop button or Esc: the agent drops what it was saying and listens again, at full volume.
  stop() {
    this.#playback?.dropped();
    this.#volume(1);
    return this.#send("stop");
  }

  // Whether push-to-talk is on: then the microphone sends sound only while the page holds it.
  get pushToTalk() {
    return this.#pushToTalk;
  }

  set pushToTalk(on) {
    this.#pushToTalk = on === true;
    this.#held = false;
    this.#microphone();
  }

  // Push-to-talk's hold: `talk(true)` as the page's key or button goes down, `talk(false)` as it
  // comes up. With push-to-talk off the microphone stays on whatever the page holds.
  talk(held) {
    this.#held = held === true;
    this.#microphone();
  }

  // End the call: the session says so (`ended`), or the call closes after a grace period.
  hangup() {
    if (this.#closed) return;
    if (!this.#send("hangup")) {
      this.#finish("hangup");
      return;
    }
    this.#hangupTimer ??= setTimeout(() => this.#finish("hangup"), HANGUP_GRACE_MS);
  }

  async #begin() {
    this.#stream = await openMicrophone();
    [this.#track] = this.#stream.getAudioTracks();
    this.#track?.addEventListener("ended", () => this.hangup());
    this.#microphone();
    const token =
      typeof this.#options.token === "string" ? this.#options.token : await this.#options.getToken();
    if (typeof token !== "string" || token === "") {
      throw new VoiceClientError("no_token", "No join token was given.");
    }
    this.#alive();
    const join = { token, protocol: PROTOCOL };
    if (this.#options.language) join.language = this.#options.language;
    const joined = await this.#request("POST", "join", join);
    this.callId = joined.call_id;
    this.#secret = joined.offer_secret;
    this.#alive();
    this.#startedAt = performance.now();
    const pc = new RTCPeerConnection({
      iceServers: (joined.ice_servers ?? []).map(iceServer),
      bundlePolicy: "max-bundle",
    });
    this.#pc = pc;
    // The audio before the data channel, so the first bundled m-line, mid "0", is the audio's:
    // the server takes candidates on that one alone.
    const transceiver = pc.addTransceiver(this.#track, {
      direction: "sendrecv",
      streams: [this.#stream],
    });
    this.#mid = () => transceiver.mid ?? "0";
    this.#channel = pc.createDataChannel("t2v", { ordered: true });
    this.#channel.addEventListener("open", () => {
      this.#send("hello", { client: CLIENT });
      this.#sendStats();
    });
    this.#channel.addEventListener("message", (event) => this.#receive(event.data));
    // The session closes the channel as the call ends, its `ended` message sent before.
    this.#channel.addEventListener("close", () => {
      this.#finish(this.#hangupTimer === null ? "server" : "hangup");
    });
    pc.addEventListener("icecandidate", (event) => this.#candidate(event.candidate));
    pc.addEventListener("track", (event) => this.#play(event));
    pc.addEventListener("connectionstatechange", () => this.#connection(pc.connectionState));
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    const answer = await this.#request("POST", "offer", {
      call_id: this.callId,
      sdp: offer.sdp,
      type: "offer",
      offer_secret: this.#secret,
    });
    this.#alive();
    await pc.setRemoteDescription({ type: "answer", sdp: answer.sdp });
    this.#answered = true;
    this.#drain();
    if (this.#options.escape !== false) {
      this.#onKey = (event) => {
        if (event.key === "Escape" && !event.repeat) this.stop();
      };
      globalThis.addEventListener("keydown", this.#onKey);
    }
  }

  // Throws once the call has ended while it was starting (its microphone gone, say), so no
  // peer is built for it.
  #alive() {
    if (this.#closed) throw new VoiceClientError("ended", "The call ended as it started.");
  }

  async #request(method, path, body) {
    let response;
    try {
      response = await fetch(new URL(path, this.#base), {
        method,
        headers: { "content-type": JSON_TYPE },
        body: JSON.stringify(body),
        cache: "no-store",
      });
    } catch (error) {
      throw new VoiceClientError("network", "The voice server could not be reached.", { cause: error });
    }
    if (response.ok) return response.status === 204 ? null : response.json();
    const refusal = await response.json().catch(() => ({}));
    const text = (value) => (typeof value === "string" ? value : null);
    throw new VoiceClientError(
      text(refusal.code) ?? "http_error",
      text(refusal.message) ?? `The voice server answered ${response.status}.`,
      { status: response.status, notice: text(refusal.notice), reference: text(refusal.reference) },
    );
  }

  #candidate(candidate) {
    if (this.#endQueued || this.#closed) return;
    if (candidate === null || candidate.candidate === "") {
      this.#endQueued = true;
      this.#queue.push({ candidate: "", sdp_mid: this.#mid(), sdp_mline_index: 0 });
    } else if (candidate.sdpMid === this.#mid()) {
      this.#queue.push({
        candidate: candidate.candidate,
        sdp_mid: candidate.sdpMid,
        sdp_mline_index: candidate.sdpMLineIndex ?? 0,
      });
    }
    this.#drain();
  }

  // Sends the queued candidates, in order and at most MAX_CANDIDATES a PATCH, once the offer is
  // answered; one PATCH at a time, so the end of candidates goes last.
  #drain() {
    if (!this.#answered || this.#draining) return;
    this.#draining = (async () => {
      while (this.#queue.length && !this.#closed) {
        await this.#patch(this.#queue.splice(0, MAX_CANDIDATES));
      }
      this.#draining = null;
    })();
  }

  async #patch(candidates) {
    try {
      await this.#request("PATCH", "offer", {
        call_id: this.callId,
        candidates,
        offer_secret: this.#secret,
      });
    } catch (error) {
      if (error.status === 409 && QUIET.includes(error.code)) return;
      this.#emit("error", error);
    }
  }

  #connection(state) {
    this.#emit("connection", { state });
    if (state === "connected" && this.#connectedAt === null) {
      this.#connectedAt = performance.now();
      this.#sendStats();
    } else if (state === "failed") {
      this.#finish("transport");
    }
  }

  #play(event) {
    const stream = event.streams[0] ?? new MediaStream([event.track]);
    this.#audio.srcObject = stream;
    this.#audio.play?.()?.catch?.(() => {});
    if (this.#context && !this.#playback) {
      this.#playback = new PlaybackWatch(this.#context, stream, {
        report: (clause, moment) => this.#send("playback", { ...clause, event: moment }),
        heard: () => this.#firstAudio(),
      });
    }
  }

  #firstAudio() {
    if (this.#firstAudioMs !== null || this.#connectedAt === null) return;
    this.#firstAudioMs = milliseconds(performance.now() - this.#connectedAt);
    this.#sendStats();
  }

  // Sends `client_stats` once connected with the channel open, and again once the first audio
  // played.
  async #sendStats() {
    const round = this.#firstAudioMs === null ? 1 : 2;
    if (this.#statsRound >= round || this.#connectedAt === null) return;
    if (this.#channel?.readyState !== "open") return;
    this.#statsRound = round;
    const echo = this.#track?.getSettings?.().echoCancellation;
    this.#send("client_stats", {
      ...(await selectedCandidate(this.#pc)),
      connect_ms: milliseconds(this.#connectedAt - this.#startedAt),
      echo_cancellation: typeof echo === "boolean" ? echo : null,
      first_audio_ms: this.#firstAudioMs,
    });
  }

  #receive(data) {
    if (typeof data !== "string") return;
    let message;
    try {
      message = JSON.parse(data);
    } catch {
      return;
    }
    if (!message || typeof message !== "object" || Array.isArray(message)) return;
    if (message.type === RESERVED || message.v !== PROTOCOL) return;
    if (!SESSION_MESSAGES.includes(message.type)) return;
    if (message.type === "hello") {
      this.languages = Array.isArray(message.languages) ? message.languages : [];
    } else if (message.type === "duck") {
      const level = message.level;
      if (typeof level !== "number" || !(level >= 0 && level <= 1)) return;
      this.#volume(level);
    } else if (message.type === "unduck") {
      this.#volume(1);
    } else if (message.type === "caption" && message.speaker === "agent") {
      message.cut = message.cut === true;
      this.#agentCaption(message);
    } else if (message.type === "ended") {
      this.#finish(message.reason);
      return;
    }
    this.#emit(message.type, message);
  }

  // A clause marked `cut` was cut by a stop as it played: its reply's playback is over. Any
  // other is the clause the session has begun to send, and a new reply's first brings the
  // volume back to full.
  #agentCaption(caption) {
    if (caption.cut) {
      this.#playback?.dropped();
      return;
    }
    if (Number.isInteger(caption.reply_id) && caption.reply_id > this.#reply) {
      this.#reply = caption.reply_id;
      this.#volume(1);
    }
    this.#playback?.captioned(caption);
  }

  // The agent's playback at `level` of the full volume, the page told by a `volume` event.
  #volume(level) {
    if (level === this.#level) return;
    this.#level = level;
    this.#audio.volume = this.#full * level;
    this.#emit("volume", { level });
  }

  // The microphone's track sends sound unless push-to-talk is on and the page does not hold it;
  // a track turned off sends silence, and the call goes on.
  #microphone() {
    if (this.#track) this.#track.enabled = !this.#pushToTalk || this.#held;
  }

  #send(type, fields = {}) {
    if (!CLIENT_MESSAGES.includes(type) || this.#channel?.readyState !== "open") return false;
    this.#channel.send(JSON.stringify({ v: PROTOCOL, type, ...fields }));
    return true;
  }

  #emit(name, value) {
    for (const listener of this.#listeners.get(name) ?? []) {
      try {
        listener(value);
      } catch (error) {
        console.error("t2v-client: a listener failed", error);
      }
    }
  }

  #finish(reason, quiet = false) {
    if (this.#closed) return;
    this.#closed = true;
    clearTimeout(this.#hangupTimer);
    this.#playback?.close();
    if (this.#onKey) globalThis.removeEventListener("keydown", this.#onKey);
    for (const track of this.#stream?.getTracks() ?? []) track.stop();
    for (const closing of [this.#channel, this.#pc]) {
      try {
        closing?.close();
      } catch {
        // closed already
      }
    }
    this.#context?.close().catch(() => {});
    if (this.#audio) this.#audio.srcObject = null;
    this.#volume(1); // the page's own element, if it gave one, is left as it came
    if (!quiet) this.#emit("ended", { reason: typeof reason === "string" ? reason : "server" });
  }
}

async function openMicrophone() {
  if (typeof globalThis.navigator?.mediaDevices?.getUserMedia !== "function") {
    throw new VoiceClientError(
      "microphone_failed",
      "This page cannot open a microphone: it needs https, or this machine's own address.",
    );
  }
  try {
    return await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
    });
  } catch (error) {
    const code = MICROPHONE[error?.name] ?? "microphone_failed";
    throw new VoiceClientError(code, MICROPHONE_MESSAGES[code], { cause: error });
  }
}

function iceServer(server) {
  const urls = Array.isArray(server.urls) ? [...server.urls] : [];
  if (typeof server.username === "string" && typeof server.credential === "string") {
    return { urls, username: server.username, credential: server.credential };
  }
  return { urls };
}

function milliseconds(value) {
  return Math.min(MAX_MS, Math.max(0, Math.round(value * 10) / 10));
}

// The selected candidate pair's local candidate: its type, and for a relay its protocol and the
// TURN server's port.
async function selectedCandidate(pc) {
  let report;
  try {
    report = await pc.getStats();
  } catch {
    return {};
  }
  let pair = null;
  report.forEach((entry) => {
    if (entry.type === "transport" && entry.selectedCandidatePairId) {
      pair = report.get(entry.selectedCandidatePairId) ?? pair;
    }
  });
  if (!pair) {
    report.forEach((entry) => {
      if (entry.type === "candidate-pair" && entry.state === "succeeded" && (entry.selected || entry.nominated)) {
        pair = entry;
      }
    });
  }
  const local = pair ? report.get(pair.localCandidateId) : undefined;
  const type = CANDIDATE_TYPES.includes(local?.candidateType) ? local.candidateType : null;
  if (type !== "relay") return { candidate_type: type };
  const port = Number(/^turns?:[^?]*:(\d{1,5})(\?|$)/.exec(local.url ?? "")?.[1]);
  return {
    candidate_type: type,
    relay_protocol: RELAY_PROTOCOLS.includes(local.relayProtocol) ? local.relayProtocol : null,
    turn_port: port >= 1 && port <= 65535 ? port : null,
  };
}

// When each clause of the agent's reply plays, read from the level of the agent's audio: a
// caption names the clause the session has begun to send, which the browser plays a jitter
// buffer later. A clause starts at the first sound after its caption came (back to back, once
// the delay the reply's first clause showed has passed) and ends when the next starts or after
// PLAYBACK_QUIET_MS of quiet.
class PlaybackWatch {
  #analyser;
  #source;
  #samples;
  #timer;
  #pending = [];
  #playing = null;
  #lastSound = 0;
  #lag = 0;
  #hooks;

  constructor(context, stream, hooks) {
    this.#hooks = hooks;
    this.#source = context.createMediaStreamSource(stream);
    this.#analyser = context.createAnalyser();
    this.#analyser.fftSize = 512;
    this.#source.connect(this.#analyser);
    this.#samples = new Float32Array(this.#analyser.fftSize);
    this.#timer = setInterval(() => this.#tick(), PLAYBACK_TICK_MS);
  }

  captioned(caption) {
    if (this.#pending.length >= MAX_PENDING) return;
    if (!Number.isInteger(caption.reply_id) || !Number.isInteger(caption.clause)) return;
    this.#pending.push({ reply_id: caption.reply_id, clause: caption.clause, at: performance.now() });
  }

  dropped() {
    this.#end();
    this.#pending.length = 0;
  }

  close() {
    clearInterval(this.#timer);
    this.#source.disconnect();
  }

  #tick() {
    this.#analyser.getFloatTimeDomainData(this.#samples);
    let sum = 0;
    for (const sample of this.#samples) sum += sample * sample;
    const now = performance.now();
    if (Math.sqrt(sum / this.#samples.length) > PLAYBACK_LEVEL) {
      this.#lastSound = now;
      this.#hooks.heard();
      const next = this.#pending[0];
      if (next && (this.#playing === null || now >= next.at + this.#lag)) {
        if (this.#playing === null) this.#lag = now - next.at;
        this.#end();
        this.#playing = this.#pending.shift();
        this.#hooks.report(clauseOf(this.#playing), "started");
      }
    } else if (this.#playing && now - this.#lastSound >= PLAYBACK_QUIET_MS) {
      this.#end();
    }
  }

  #end() {
    if (this.#playing === null) return;
    this.#hooks.report(clauseOf(this.#playing), "ended");
    this.#playing = null;
  }
}

function clauseOf(pending) {
  return { reply_id: pending.reply_id, clause: pending.clause };
}

// The dev page (dev.html): a token (any, for the dev caller), a language, Start, Stop and Hang
// up, push-to-talk (a switch, and a button held to talk), the call's state, the agent's volume
// (lowered while the caller speaks over a reply), its captions (a clause a stop cut marked so)
// and its notices. Every text is set with textContent.
function devPage(page) {
  const $ = (id) => page.getElementById(id);
  const captions = new Map();
  let call = null;
  const talkable = () => {
    $("talk").disabled = $("stop").disabled || !$("push-to-talk").checked;
  };
  const running = (on) => {
    $("start").disabled = on;
    $("stop").disabled = !on;
    $("hangup").disabled = !on;
    talkable();
  };
  const talk = (held) => {
    $("talk").setAttribute("aria-pressed", String(held));
    call?.talk(held);
  };
  const line = (list, text) => {
    const item = page.createElement("li");
    item.textContent = text;
    $(list).append(item);
    return item;
  };
  const caption = (c) => {
    const key = c.speaker === "agent" ? `agent ${c.reply_id}` : `caller ${c.turn_id}`;
    if (!captions.has(key)) captions.set(key, { item: line("captions", ""), parts: [] });
    const shown = captions.get(key);
    shown.parts[c.speaker === "agent" ? c.clause : 0] = c.cut ? `${c.text} [cut]` : c.text;
    shown.item.textContent = `${c.speaker}: ${shown.parts.filter(Boolean).join(" ")}`;
  };
  const volume = (v) => ($("volume").textContent = `${Math.round(v.level * 100)}%`);
  $("start").addEventListener("click", async () => {
    running(true);
    captions.clear();
    $("captions").replaceChildren();
    $("notices").replaceChildren();
    $("status").textContent = "Starting.";
    volume({ level: 1 });
    try {
      call = await VoiceClient.start({
        base: ".",
        token: $("token").value || "dev",
        language: $("language").value || undefined,
        pushToTalk: $("push-to-talk").checked,
        on: {
          hello: (h) => ($("status").textContent = `Connected: call ${h.call_id}.`),
          state: (s) => ($("state").textContent = s.state),
          caption,
          volume,
          notice: (n) => line("notices", `${n.kind}: ${n.text}`),
          connection: (c) => ($("connection").textContent = c.state),
          error: (e) => line("notices", `${e.code}: ${e.message}`),
          ended: (e) => {
            $("status").textContent = `Ended: ${e.reason}.`;
            running(false);
            talk(false);
            call = null;
          },
        },
      });
      call.pushToTalk = $("push-to-talk").checked; // switched while the call started
      $("status").textContent = `Joined call ${call.callId}.`;
    } catch (error) {
      $("status").textContent = `${error.code ?? "error"}: ${error.notice ?? error.message}`;
      running(false);
    }
  });
  $("stop").addEventListener("click", () => call?.stop());
  $("hangup").addEventListener("click", () => call?.hangup());
  $("push-to-talk").addEventListener("change", () => {
    if (call) call.pushToTalk = $("push-to-talk").checked;
    talk(false);
    talkable();
  });
  // Held with the pointer: captured, so the hold ends wherever the button comes up.
  $("talk").addEventListener("pointerdown", (event) => {
    if ($("talk").disabled) return;
    $("talk").setPointerCapture?.(event.pointerId);
    talk(true);
  });
  for (const name of ["pointerup", "pointercancel", "lostpointercapture"]) {
    $("talk").addEventListener(name, () => talk(false));
  }
}

if (globalThis.document?.documentElement?.dataset?.t2vPage === "dev") devPage(globalThis.document);
