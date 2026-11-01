"use strict";
// The recorder's page (`poe record`), served by ole5_voice/evals/recorder.py under the
// session's token. Every address here is relative, so each request carries the token, and the
// page loads nothing from another address. Text from the script, the replies and the files is
// set as text, never as HTML.
//
// The same file is the page's script and its audio worklet: in the worklet's own scope it only
// hands each block of the microphone's samples, already at 16 kHz, to the page.

if (typeof registerProcessor === "function") {
  registerProcessor(
    "capture",
    class extends AudioWorkletProcessor {
      process(inputs) {
        const samples = inputs[0] && inputs[0][0];
        if (samples) this.port.postMessage(samples.slice());
        return true;
      }
    },
  );
} else {
  recorderPage();
}

function recorderPage() {
  const RATE = 16000;
  // MediaStreamTrack names the method that ends a track after a word the golden set holds as a
  // reference, and no page text holds a reference whole (plan 002's rule), so it is looked up
  // by its parts.
  const END = ["st", "op"].join("");
  const endTrack = (track) => track[END]();
  const $ = (id) => document.getElementById(id);
  const page = { data: null, line: 0, tab: "record", recording: null, take: null, playing: null };

  function el(tag, text, props = {}) {
    const node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = text;
    return Object.assign(node, props);
  }

  function notice(text, kind = "") {
    $("notice").textContent = text;
    $("notice").className = kind;
  }

  function fail(error) {
    const blocked = error && error.name === "NotAllowedError";
    const told = "The page may not use a microphone: allow one for this address in Chrome, then reload.";
    notice(blocked ? told : error.message || String(error), "bad");
    if (page.data) render();
  }

  async function api(path, body) {
    const options =
      body === undefined
        ? {}
        : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
    const response = await fetch(path, options);
    const answer = await response.json().catch(() => ({}));
    if (response.status >= 300) throw new Error(answer.error || `${response.status} ${response.statusText}`);
    return answer;
  }

  async function load() {
    page.data = await api("api/state");
    render();
  }

  // ---------------------------------------------------------------- devices

  async function listDevices() {
    // The browser gives the devices' labels only once the page may use a microphone.
    const probe = await navigator.mediaDevices.getUserMedia({ audio: true });
    probe.getTracks().forEach(endTrack);
    const devices = await navigator.mediaDevices.enumerateDevices();
    fill($("microphone"), devices.filter((d) => d.kind === "audioinput"));
    fill($("output"), devices.filter((d) => d.kind === "audiooutput"));
  }

  function fill(select, devices) {
    const options = devices.map((d, i) => el("option", d.label || `device ${i + 1}`, { value: d.deviceId }));
    select.replaceChildren(...options);
  }

  const selectedLabel = (select) => (select.selectedOptions[0] ? select.selectedOptions[0].textContent : "");

  async function audioOf(url) {
    const audio = new Audio(url);
    const sink = $("output").value;
    if (sink && audio.setSinkId) await audio.setSinkId(sink);
    return audio;
  }

  async function play(urls) {
    if (page.playing) page.playing.pause();
    for (const url of urls) {
      const audio = await audioOf(url);
      page.playing = audio;
      await new Promise((done, failed) => {
        audio.onended = done;
        audio.onerror = () => failed(new Error("The audio did not play."));
        audio.play().catch(failed);
      });
    }
  }

  function trackSettings(s) {
    const flag = (v) => (typeof v === "boolean" ? v : typeof v === "string" ? v !== "none" : null);
    const count = (v) => (Number.isInteger(v) ? v : null);
    return {
      echo_cancellation: flag(s.echoCancellation),
      noise_suppression: flag(s.noiseSuppression),
      auto_gain_control: flag(s.autoGainControl),
      sample_rate: count(s.sampleRate),
      channel_count: count(s.channelCount),
    };
  }

  function showTrack(settings) {
    const t = trackSettings(settings);
    const named = [
      ["echo cancellation", t.echo_cancellation],
      ["noise suppression", t.noise_suppression],
      ["gain control", t.auto_gain_control],
    ];
    const off = named.filter(([, on]) => on !== true).map(([name]) => name);
    $("track").textContent =
      `Microphone track: ${named.map(([name, on]) => `${name} ${on === true ? "on" : "off"}`).join(", ")}; ` +
      `${t.sample_rate || "?"} Hz in, recorded at ${RATE} Hz mono.`;
    if (off.length) notice(`The browser has ${off.join(", ")} off for this microphone; the take's sidecar says so.`, "bad");
  }

  // ---------------------------------------------------------------- recording

  const line = () => page.data.lines[page.line];
  const takesOf = (id) => page.data.takes.filter((t) => t.line === id);
  const msOf = (take) => Math.floor((take.pcm.length * 1000) / RATE);

  async function record() {
    const l = line();
    const microphone = $("microphone").value;
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        deviceId: microphone ? { exact: microphone } : undefined,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    });
    const context = new AudioContext({ sampleRate: RATE });
    try {
      if (context.sampleRate !== RATE) throw new Error(`The browser records at ${context.sampleRate} Hz here, not ${RATE} Hz.`);
      await context.audioWorklet.addModule("recorder.js");
    } catch (error) {
      stream.getTracks().forEach(endTrack);
      await context.close();
      throw error;
    }
    const capture = new AudioWorkletNode(context, "capture", {
      channelCount: 1,
      channelCountMode: "explicit",
      channelInterpretation: "speakers",
    });
    const chunks = [];
    capture.port.onmessage = (event) => chunks.push(event.data);
    context.createMediaStreamSource(stream).connect(capture);
    capture.connect(new GainNode(context, { gain: 0 })).connect(context.destination);
    const track = stream.getAudioTracks()[0];
    const recording = { stream, context, chunks, settings: track.getSettings(), microphone: track.label };
    page.recording = recording;
    if (l.reply) {
      recording.reply = await audioOf(`reply/${encodeURIComponent(l.reply)}`);
      if (!l.say.length) recording.reply.onended = () => setTimeout(() => finish().catch(fail), 500);
      recording.reply.play().catch(fail);
    }
    if (l.seconds) recording.timer = setTimeout(() => finish().catch(fail), l.seconds * 1000);
    $("status").textContent = "Recording.";
    $("status").className = "live";
    render();
  }

  async function finish() {
    const r = page.recording;
    if (!r) return;
    page.recording = null;
    clearTimeout(r.timer);
    if (r.reply) r.reply.pause();
    r.stream.getTracks().forEach(endTrack);
    await r.context.close();
    const pcm = toPcm16(r.chunks);
    $("status").className = "";
    if (!pcm.length) {
      $("status").textContent = "Nothing was recorded: record the line again.";
      render();
      return;
    }
    page.take = {
      line: line().id,
      pcm,
      wav: wavFile(pcm),
      settings: r.settings,
      microphone: r.microphone,
      output: selectedLabel($("output")),
      marks: [],
    };
    $("status").textContent = `Recorded ${(pcm.length / RATE).toFixed(1)} s: play it, then keep or discard it.`;
    showTrack(r.settings);
    render();
  }

  function toPcm16(chunks) {
    const pcm = new Int16Array(chunks.reduce((n, chunk) => n + chunk.length, 0));
    let at = 0;
    for (const chunk of chunks) {
      for (const sample of chunk) {
        const v = Math.max(-1, Math.min(1, sample));
        pcm[at++] = Math.round(v < 0 ? v * 0x8000 : v * 0x7fff);
      }
    }
    return pcm;
  }

  function wavFile(pcm) {
    // A 44-byte header for 16 kHz mono 16-bit PCM, then the samples, little-endian.
    const view = new DataView(new ArrayBuffer(44 + pcm.length * 2));
    const text = (at, s) => [...s].forEach((c, i) => view.setUint8(at + i, c.charCodeAt(0)));
    text(0, "RIFF");
    view.setUint32(4, 36 + pcm.length * 2, true);
    text(8, "WAVE");
    text(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, RATE, true);
    view.setUint32(28, RATE * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    text(36, "data");
    view.setUint32(40, pcm.length * 2, true);
    pcm.forEach((sample, i) => view.setInt16(44 + i * 2, sample, true));
    return new Uint8Array(view.buffer);
  }

  function base64(bytes) {
    let text = "";
    for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return btoa(text);
  }

  async function save(status) {
    const t = page.take;
    try {
      const saved = await api("api/take", {
        line: t.line,
        microphone: t.microphone,
        output: t.output,
        track: trackSettings(t.settings),
        turn_ends_ms: [...t.marks].sort((a, b) => a - b),
        status,
        audio: base64(t.wav),
      });
      notice(`Saved ${saved.take} as ${saved.status}.`, "good");
    } catch (error) {
      if (status === "discarded") page.take = null; // a take the server refuses is let go
      throw error;
    }
    page.take = null;
    $("status").textContent = "";
    await load();
  }

  function mark(event) {
    const t = page.take;
    if (!t) return;
    const canvas = $("wave");
    const box = canvas.getBoundingClientRect();
    const x = ((event.clientX - box.left) / box.width) * canvas.width;
    const ms = Math.min(msOf(t), Math.max(0, Math.round((x / canvas.width) * msOf(t))));
    const near = t.marks.findIndex((m) => Math.abs((m / msOf(t)) * canvas.width - x) < 8);
    if (near >= 0) t.marks.splice(near, 1);
    else if (!t.marks.includes(ms)) t.marks.push(ms);
    render();
  }

  function drawWave() {
    const t = page.take;
    const canvas = $("wave");
    const g = canvas.getContext("2d");
    const { width, height } = canvas;
    const style = getComputedStyle(document.body);
    g.clearRect(0, 0, width, height);
    g.fillStyle = style.color;
    for (let x = 0; x < width; x++) {
      let low = 0;
      let high = 0;
      const last = Math.floor(((x + 1) * t.pcm.length) / width);
      for (let i = Math.floor((x * t.pcm.length) / width); i < last; i++) {
        low = Math.min(low, t.pcm[i]);
        high = Math.max(high, t.pcm[i]);
      }
      const top = height / 2 - (high / 32768) * (height / 2);
      g.fillRect(x, top, 1, Math.max(1, ((high - low) / 32768) * (height / 2)));
    }
    g.fillStyle = style.getPropertyValue("--live") || "red";
    for (const ms of t.marks) g.fillRect(Math.round((ms / msOf(t)) * width) - 1, 0, 3, height);
    const sorted = [...t.marks].sort((a, b) => a - b);
    $("marks").textContent = sorted.length
      ? `Turn ends: ${sorted.map((ms) => `${(ms / 1000).toFixed(2)} s`).join(", ")}.`
      : "No turn end is marked yet.";
  }

  function cueOf(l) {
    const parts = l.cue ? [l.cue] : [];
    if (l.reply) {
      const reply = page.data.replies.find((r) => r.id === l.reply);
      const about = reply && reply.topic ? ` (${reply.topic})` : "";
      parts.push(
        l.say.length
          ? `The agent's reply${about} plays while you speak.`
          : `Say nothing while the agent's reply${about} plays: the take ends with it.`,
      );
    }
    if (l.seconds) parts.push(`The take lasts ${l.seconds} s.`);
    if (!parts.length && !l.say.length) parts.push("Say nothing.");
    return parts.join(" ");
  }

  function renderRecord() {
    const d = page.data;
    const busy = Boolean(page.recording || page.take);
    $("lines").replaceChildren(
      ...d.lines.map((l, i) => {
        const kept = takesOf(l.id).filter((t) => t.status === "kept").length;
        const item = el("li");
        item.append(
          el("button", `${l.id} · ${l.kind}${kept ? ` · ${kept} kept` : ""}`, {
            type: "button",
            disabled: busy,
            className: `${i === page.line ? "current" : ""} ${kept ? "done" : ""}`,
            onclick: () => {
              page.line = i;
              render();
            },
          }),
        );
        return item;
      }),
    );
    const l = line();
    const terms = l.terms.length ? `terms: ${l.terms.join(", ")}` : "";
    $("line-title").textContent = `${l.id} (${page.line + 1} of ${d.lines.length})`;
    $("line-meta").textContent = [l.kind, l.language, terms].filter(Boolean).join(" · ");
    $("say").replaceChildren(...l.say.map((clause) => el("li", clause, { dir: "auto" })));
    $("cue").textContent = cueOf(l);
    const several = l.say.length > 1;
    $("rec").disabled = !d.consent || busy;
    $("finish").disabled = !page.recording;
    $("play").disabled = !page.take;
    $("keep").disabled = !page.take || (several && !page.take.marks.length);
    $("discard").disabled = !page.take;
    $("next").disabled = busy || page.line + 1 >= d.lines.length;
    $("ends").hidden = !(page.take && several);
    if (page.take && several) drawWave();
    $("takes").replaceChildren(
      ...takesOf(l.id).map((t) => {
        const item = el("li", `${t.take} · ${t.status} · ${t.seconds.toFixed(1)} s `);
        const url = `take/${encodeURIComponent(t.take)}`;
        item.append(el("button", "Play", { type: "button", onclick: () => play([url]).catch(fail) }));
        return item;
      }),
    );
  }

  // ---------------------------------------------------------------- review

  const latest = (e) => e.reviews.reduce((a, b) => (b.review_pass > a.review_pass ? b : a));
  const segments = (e) => Array.from({ length: e.segments }, (_, n) => `variant/${encodeURIComponent(e.id)}/${n}`);

  async function check(e, verdict, text) {
    if (verdict === "typed" && !text.trim()) throw new Error("Type what it says first.");
    await api("api/review", { id: e.id, verdict, text: text.trim() });
    const said = verdict === "confirmed" ? "confirmed" : "typed: it comes back in the next pass";
    notice(`${e.id}: ${said}.`, "good");
    await load();
  }

  function entryItem(e) {
    const item = el("li");
    const typed = el("input", null, { type: "text", dir: "auto", placeholder: "What it says, if not this" });
    item.append(
      el("p", e.reference || "(no speech: nothing is said in it)", { className: "reference", dir: "auto" }),
      el("p", `${e.id} · ${e.of} · ${e.kind} · ${e.language} · its text: ${e.source}`, { className: "muted" }),
      el("button", "Play", { type: "button", onclick: () => play(segments(e)).catch(fail) }),
      el("button", "It says this", {
        type: "button",
        className: "primary",
        onclick: () => check(e, "confirmed", "").catch(fail),
      }),
      typed,
      el("button", "Save what it says", { type: "button", onclick: () => check(e, "typed", typed.value).catch(fail) }),
    );
    return item;
  }

  function renderReview() {
    const d = page.data;
    const due = d.review.filter((e) => e.due);
    const confirmed = d.review.filter((e) => !e.due && e.reviews.length && latest(e).verdict === "confirmed");
    const later = d.review.length - due.length - confirmed.length;
    $("review-summary").textContent =
      `Review pass ${d.review_pass}: ${due.length} to check, ${confirmed.length} confirmed, ` +
      `${later} typed in this pass, which come back for their own check in the next pass ` +
      "(the next run of poe record).";
    $("queue").replaceChildren(...due.map(entryItem));
  }

  // ---------------------------------------------------------------- the page

  function render() {
    const d = page.data;
    $("where").textContent = d.session
      ? `Session ${d.session} on the ${d.device} microphone · review pass ${d.review_pass}`
      : `Review only: no --session and --device were given · review pass ${d.review_pass}`;
    $("consent").hidden = !d.session || Boolean(d.consent);
    $("tab-record").disabled = !d.session;
    if (!d.session) page.tab = "review";
    $("record").hidden = page.tab !== "record";
    $("review").hidden = page.tab !== "review";
    $("tab-record").setAttribute("aria-pressed", String(page.tab === "record"));
    $("tab-review").setAttribute("aria-pressed", String(page.tab === "review"));
    if (page.tab === "record") renderRecord();
    else renderReview();
  }

  async function saveConsent() {
    if (!$("agreed").checked) throw new Error("The consent is saved only once the speaker agrees.");
    const speaker = $("speaker").value.trim();
    const words = $("words").value.trim();
    if (!speaker || !words) throw new Error("Give the speaker's name and their words.");
    await api("api/consent", { speaker, words, agreed: true });
    notice("The consent is saved.", "good");
    await load();
  }

  const run = (action) => () => action().catch(fail);
  $("tab-record").onclick = () => {
    page.tab = "record";
    render();
  };
  $("tab-review").onclick = () => {
    page.tab = "review";
    render();
  };
  $("save-consent").onclick = run(saveConsent);
  $("rec").onclick = run(record);
  $("finish").onclick = run(finish);
  $("play").onclick = run(() => play([URL.createObjectURL(new Blob([page.take.wav], { type: "audio/wav" }))]));
  $("keep").onclick = run(() => save("kept"));
  $("discard").onclick = run(() => save("discarded"));
  $("next").onclick = () => {
    page.line += 1;
    render();
  };
  $("wave").onclick = mark;
  load()
    .then(listDevices)
    .catch(fail);
}
