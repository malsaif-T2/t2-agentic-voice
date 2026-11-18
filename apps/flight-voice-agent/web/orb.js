// The orb's life with the call's sound (app.js), decoration alone: nothing here can stop or slow
// a call, so every step is wrapped and a failure leaves the orb as the call's state draws it
// (index.html's data-state, app.css's calm animations). The page gives the library's client its
// own audio element (`begin`, at the click that starts the call, so its context may run); once
// the client has set the agent's stream on it, an AnalyserNode of the page's own AudioContext
// measures that stream, never routed to the speakers (the element plays it already). Once the
// call has started, `listen` opens a second microphone stream for the caller's level alone, with
// the client's constraints so the browser shares the one capture, and `end` stops its tracks.
// Each frame sets the level, 0 to 1, as the orb's `--level` custom property (CSSOM, which the
// page's style-src allows): the agent's while it speaks, the caller's while it listens (none
// while push to talk is not held, `hush`), else falling back to rest. `data-live` says a level is
// measured, so the style's own pulse stands in when none is.

const MICROPHONE = {
  audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
};
// The analyser's window, and how fast the level rises and falls each frame.
const WINDOW = 512;
const RISE = 0.55;
const FALL = 0.9;
// How long the agent's element is watched for its stream before giving up, and how often.
const WATCH_MS = 30_000;
const EVERY_MS = 250;

// The loudness of one window of an analyser, 0 to 1, on a curve close to how it is heard.
function loudness({ analyser, data }, gain) {
  analyser.getByteTimeDomainData(data);
  let sum = 0;
  for (const value of data) sum += ((value - 128) / 128) ** 2;
  const rms = Math.sqrt(sum / data.length);
  return Math.min(1, Math.sqrt(Math.max(0, rms - 0.008) * gain));
}

export class Orb {
  #node;
  #context = null;
  #agent = null;
  #caller = null;
  #microphone = null;
  #frame = 0;
  #poll = 0;
  #level = 0;
  #shown = -1;
  hush = false;

  constructor(node) {
    this.#node = node;
  }

  // The orb's look for the call's state `now` ("" for none).
  set state(now) {
    this.#node.dataset.state = now;
  }

  // At the click that starts a call, before any await: the page's context, and `audio`, the
  // element the client will play the agent on, watched for its stream.
  begin(audio) {
    this.end();
    try {
      if (typeof globalThis.AudioContext !== "function") return;
      if (typeof globalThis.requestAnimationFrame !== "function") return;
      this.#context = new AudioContext();
      const watch = () => this.#attach(audio);
      for (const name of ["loadedmetadata", "playing"]) audio.addEventListener?.(name, watch);
      const since = Date.now();
      this.#poll = setInterval(() => (Date.now() - since > WATCH_MS ? clearInterval(this.#poll) : watch()), EVERY_MS);
      this.#frame = requestAnimationFrame(this.#tick);
    } catch {
      this.end();
    }
  }

  // Once the call has started: the caller's microphone, for its level alone; none on failure.
  async listen() {
    try {
      if (!this.#context || this.#microphone) return;
      const stream = await navigator.mediaDevices.getUserMedia(MICROPHONE);
      if (!this.#context) {
        for (const track of stream.getTracks()) track.stop();
        return;
      }
      this.#microphone = stream;
      this.#caller = this.#analyse(stream);
    } catch {
      // the level meter is decoration: the call goes on without it
    }
  }

  // The call is over: the meter's microphone stopped, the context closed, the orb at rest.
  end() {
    try {
      globalThis.cancelAnimationFrame?.(this.#frame);
      clearInterval(this.#poll);
      for (const track of this.#microphone?.getTracks() ?? []) track.stop();
      this.#context?.close?.().catch?.(() => {});
    } catch {
      // closed already
    }
    this.#context = this.#agent = this.#caller = this.#microphone = null;
    this.#level = 0;
    this.#show(0);
    delete this.#node.dataset.live;
  }

  #attach(audio) {
    try {
      const stream = audio.srcObject;
      if (!this.#context || this.#agent || !stream?.getAudioTracks?.().length) return;
      this.#agent = this.#analyse(stream);
      clearInterval(this.#poll);
      this.#context.resume?.().catch?.(() => {});
      this.#node.dataset.live = "on";
    } catch {
      // no level for the agent: the style's pulse stands in
    }
  }

  #analyse(stream) {
    const analyser = this.#context.createAnalyser();
    analyser.fftSize = WINDOW;
    analyser.smoothingTimeConstant = 0.6;
    this.#context.createMediaStreamSource(stream).connect(analyser);
    return { analyser, data: new Uint8Array(analyser.fftSize) };
  }

  #tick = () => {
    try {
      const now = this.#node.dataset.state;
      const caller = this.hush ? null : this.#caller;
      const source = now === "speaking" ? this.#agent : now === "listening" ? caller : null;
      const target = source ? loudness(source, now === "speaking" ? 5 : 4) : 0;
      this.#level = target > this.#level ? this.#level + (target - this.#level) * RISE : this.#level * FALL;
      this.#show(this.#level);
      this.#frame = requestAnimationFrame(this.#tick);
    } catch {
      this.#show(0);
    }
  };

  #show(level) {
    const shown = Math.round(level * 100) / 100;
    if (shown === this.#shown) return;
    this.#shown = shown;
    try {
      this.#node.style.setProperty("--level", String(shown));
    } catch {
      // a style that cannot be set leaves the orb as its state draws it
    }
  }
}
