// The test console's script (api/dev_console.py, D-083): it reads the runtime's events from
// GET dev/feed (long-polling: each request answers once a record is new, or after 10 s), keeps
// them by call and by turn, and shows the chosen call: what was heard, the time of each step,
// each tool call's arguments and result, interruptions, the read-back, the yes rule's decision,
// the action's write, the models' usage and the connection. It also starts a call of its own
// through the library's client, heard by the speech-to-text provider, model and language mode
// its pickers name (GET dev/stt lists what this process can use; the call's choice goes as
// POST dev/stt before its offer), remembered in this browser. Every text is set with
// textContent, never as HTML: the events hold what callers said and what tools returned.

import { VoiceClient } from "../client/1/t2v-client.js";

const $ = (id) => document.getElementById(id);
const FEED_RETRY_MS = 2000;
const MAX_LOG_ROWS = 400;
// Where this browser remembers the speech-to-text pickers.
const STT_KEY = "t2v.dev-console.stt";

// ---------------------------------------------------------------------------------------------
// Elements, made with text only.

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = String(value);
    else if (key === "style") node.style.cssText = value;
    else if (key.includes("-")) node.setAttribute(key, String(value));
    else node[key] = value;
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

const ms = (value) => (value === null || value === undefined ? "–" : `${Math.round(value)} ms`);
const seconds = (value) => (value === null || value === undefined ? "–" : `${(value / 1000).toFixed(2)} s`);
const badge = (text, kind = "") => el("span", { class: `badge ${kind}`.trim(), text });

// JSON text as it was sent, laid out when it parses; the text itself when it does not.
function pretty(text) {
  if (!text) return "";
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}

function median(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

// ---------------------------------------------------------------------------------------------
// What the feed has said, by call.

const view = {
  setup: null,
  calls: new Map(),
  chosen: null,
  open: new Set(), // the <details> left open, by key, kept across a redraw
  feed: null,
  after: 0,
  own: null, // this page's call
};

function callOf(id) {
  if (!view.calls.has(id)) {
    view.calls.set(id, {
      id,
      records: [],
      startedAt: null,
      endedAt: null,
      report: null,
      turns: new Map(),
      replies: [], // the agent's replies that answer no turn: the greeting, an outcome, a notice
      tools: new Map(),
      record: [], // the call's record of completed actions
      failures: [],
      usage: [],
    });
  }
  return view.calls.get(id);
}

function turnOf(call, id, at) {
  if (!call.turns.has(id)) {
    call.turns.set(id, {
      id,
      firstAt: at,
      heard: null,
      heardBy: null, // the provider and model that heard the turn
      times: null,
      usage: null,
      tools: [],
      said: [],
      interruptions: [],
      guard: [],
      failures: [],
      readBack: null,
      answer: null,
      writes: [],
    });
  }
  return call.turns.get(id);
}

function apply(record) {
  const event = record.event;
  const call = callOf(record.call_id);
  const at = Date.parse(event.at);
  call.records.push(record);
  call.startedAt ??= at;
  const turn = event.turn_id === null || event.turn_id === undefined ? null : turnOf(call, event.turn_id, at);
  switch (record.type) {
    case "CallStarted":
      call.startedAt = Math.min(call.startedAt, at);
      break;
    case "CallEnded":
      call.endedAt = at;
      call.report = event.report;
      call.usage = event.report.usage;
      break;
    case "UserTurnEnded":
      turn.heard = event.heard;
      turn.heardBy = record.heard_by ?? turn.heardBy;
      break;
    case "TurnMetrics":
      turn.heardBy = record.heard_by ?? turn.heardBy;
      turn.times = event;
      turn.usage = event.usage;
      if (!call.report) call.usage = event.usage;
      break;
    case "ToolStarted":
      call.tools.set(event.tool_call_id, { ...event, done: false, startedAt: at });
      turn.tools.push(event.tool_call_id);
      break;
    case "ToolFinished": {
      const known = call.tools.get(event.tool_call_id);
      call.tools.set(event.tool_call_id, { ...known, ...event, done: true });
      if (!known) turn.tools.push(event.tool_call_id);
      break;
    }
    case "AgentSpeechEnded": {
      const said = { at, text: event.text, played: event.played_fraction };
      if (turn) turn.said.push(said);
      else call.replies.push(said);
      break;
    }
    case "Interrupted":
      (turn ? turn.interruptions : call.failures).push({ at, kind: event.kind, reason: event.reason, interrupted: true });
      break;
    case "ConfirmationRequested":
      turn.readBack = { at, action: event.action, draft: event.draft };
      break;
    case "ConfirmationAnswered":
      turn.answer = { at, action: event.action, decision: event.decision, by: event.by };
      break;
    case "ActionCompleted":
    case "ActionUnconfirmed": {
      const write = {
        at,
        action: event.action,
        request_id: event.request_id,
        kind: record.type === "ActionCompleted" ? "done" : event.kind,
        result: event.result ?? "",
      };
      if (turn) turn.writes.push(write);
      if (write.kind === "done") call.record.push(write);
      break;
    }
    case "GuardBlocked":
      turn.guard.push({ at, reason: event.reason });
      break;
    case "ProviderFailed":
      (turn ? turn.failures : call.failures).push({ at, text: `provider failed: ${event.kind}${event.retryable ? " (retryable)" : ""}` });
      break;
    case "TransportFailed":
      call.failures.push({ at, text: `connection failed at ${event.stage}` });
      break;
  }
  return call;
}

// ---------------------------------------------------------------------------------------------
// The feed: long-polled, started over when the runtime restarted (a new feed name).

async function poll() {
  for (;;) {
    let body;
    try {
      const first = view.feed === null ? "&wait=0" : ""; // the first answers at once
      const response = await fetch(`feed?after=${view.after}${first}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      body = await response.json();
    } catch (error) {
      $("feed-state").textContent = `Feed: ${error.message}; trying again.`;
      await new Promise((done) => setTimeout(done, FEED_RETRY_MS));
      continue;
    }
    if (view.feed !== null && body.feed !== view.feed) {
      view.calls.clear();
      view.chosen = null;
      view.after = 0;
    }
    view.feed = body.feed;
    const touched = new Set();
    for (const record of body.records) {
      if (record.seq <= view.after) continue;
      view.after = record.seq;
      const call = apply(record);
      touched.add(call.id);
      if (record.type === "CallStarted" && $("follow").checked) view.chosen = call.id;
    }
    if (view.chosen === null && view.calls.size) view.chosen = [...view.calls.keys()].at(-1);
    $("feed-state").textContent = `Feed: live, ${view.calls.size} call${view.calls.size === 1 ? "" : "s"} kept.`;
    if (touched.size || !body.records.length) drawCalls();
    if (touched.has(view.chosen)) drawChosen();
  }
}

// ---------------------------------------------------------------------------------------------
// The setup: what the agent runs with.

async function loadSetup() {
  try {
    const response = await fetch("setup", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    view.setup = await response.json();
  } catch (error) {
    $("setup-chips").replaceChildren(badge(`setup: ${error.message}`, "bad"));
    return;
  }
  const s = view.setup;
  $("setup-chips").replaceChildren(
    el("span", { class: "chip strong", text: s.agent }),
    el("span", { class: "chip", text: `${s.mode} · env ${s.env}` }),
  );
  const pairs = (object) =>
    el("dl", { class: "pairs" }, Object.entries(object).flatMap(([key, value]) => [
      el("dt", { text: key }),
      el("dd", { text: typeof value === "object" && value !== null ? JSON.stringify(value) : String(value) }),
    ]));
  const agent = {
    agent: s.agent,
    version: s.version ?? "–",
    mode: s.mode,
    languages: s.languages.join(", "),
    tools: s.tools.join(", ") || "none",
    actions: s.actions.join(", ") || "none",
    "ask on uncertain overlaps": s.ask_on_uncertain_overlaps,
    "ask on unlisted answers": s.ask_on_unlisted_answers,
    ...s.library,
  };
  $("setup-body").replaceChildren(
    el("section", {}, el("h3", { text: "Agent" }), pairs(agent)),
    ...Object.entries(s.settings).map(([group, values]) => el("section", {}, el("h3", { text: group }), pairs(values))),
  );
}

// ---------------------------------------------------------------------------------------------
// The calls list.

function drawCalls() {
  const items = [...view.calls.values()].reverse().map((call) => {
    const live = call.report === null;
    const turns = call.turns.size;
    const started = call.startedAt ? new Date(call.startedAt).toLocaleTimeString() : "–";
    const button = el(
      "button",
      { type: "button", class: `call${call.id === view.chosen ? " chosen" : ""}`, "aria-current": call.id === view.chosen ? "true" : undefined },
      el("span", { class: "call-id", text: call.id.slice(0, 10) }),
      live ? badge("live", "live") : badge(call.report.ended_by),
      el("span", { class: "muted small", text: `${started} · ${turns} turn${turns === 1 ? "" : "s"}${view.own?.callId === call.id ? " · this page" : ""}` }),
    );
    button.addEventListener("click", () => {
      view.chosen = call.id;
      $("follow").checked = false;
      drawCalls();
      drawChosen();
    });
    return el("li", {}, button);
  });
  $("calls").replaceChildren(...items);
}

// ---------------------------------------------------------------------------------------------
// The chosen call: its turns, its summary and its events.

function details(key, summary, ...body) {
  const box = el("details", { class: "more" }, el("summary", {}, summary), ...body);
  box.open = view.open.has(key);
  box.addEventListener("toggle", () => (box.open ? view.open.add(key) : view.open.delete(key)));
  return box;
}

const json = (text) => el("pre", { class: "json", dir: "ltr", text: pretty(text) || "(empty)" });

// The bars of a turn's times, each from the end of the caller's speech.
function bars(times, scale) {
  const stop = view.setup?.settings.turns.vad_stop_ms ?? 0;
  const transcript = times.stt_ms === null ? null : stop + times.stt_ms;
  const rows = [
    ["Smart Turn: complete", times.turn_complete_ms, "k-complete"],
    ["End of turn", times.end_of_turn_ms, "k-eot"],
    ["Transcript (Whisper)", transcript, "k-stt"],
    ["Model's first token", times.llm_first_token_ms, "k-token"],
    ["Progress line", times.progress_ms, "k-progress"],
    ["First audio (TTFA)", times.ttfa_ms, "k-audio"],
    ["Played in the browser", times.played_ms, "k-played"],
  ].filter(([, value]) => value !== null && value !== undefined);
  return el(
    "div",
    { class: "bars" },
    rows.map(([label, value, key]) =>
      el(
        "div",
        { class: "bar-row" },
        el("span", { class: "bar-label small", text: label }),
        el("span", { class: "bar-track" }, el("span", { class: `bar ${key}`, style: `width:${Math.min(100, (100 * value) / scale)}%` })),
        el("span", { class: "bar-value small", text: ms(value) }),
      ),
    ),
  );
}

function steps(times) {
  const tools = times._tools;
  return el(
    "div",
    { class: "steps" },
    [
      ["End of turn", times.end_of_turn_ms],
      ["Whisper", times.stt_ms],
      ["First token", times.llm_first_token_ms],
      ["Orpheus first audio", times.tts_first_audio_ms],
      ["Tools", tools || null],
      ["TTFA", times.ttfa_ms],
    ].map(([label, value]) => el("div", { class: `step${label === "TTFA" ? " key" : ""}` }, el("span", { class: "muted small", text: label }), el("strong", { text: ms(value) }))),
  );
}

function usageDelta(turn, previous) {
  if (!turn.usage) return null;
  const before = new Map((previous ?? []).map((u) => [u.model, u]));
  const parts = turn.usage
    .map((u) => {
      const was = before.get(u.model) ?? {};
      const requests = u.requests - (was.requests ?? 0);
      const tokens = u.input_tokens + u.output_tokens - (was.input_tokens ?? 0) - (was.output_tokens ?? 0);
      if (!requests) return null;
      return `${u.model}: ${requests} request${requests === 1 ? "" : "s"}${tokens ? `, ${tokens} tokens` : ""}`;
    })
    .filter(Boolean);
  return parts.length ? el("p", { class: "muted small", text: `This turn used ${parts.join(" · ")}` }) : null;
}

function turnCard(call, turn, scale, previousUsage) {
  const key = `${call.id}/${turn.id}`;
  const times = turn.times;
  const tools = turn.tools.map((id) => call.tools.get(id)).filter(Boolean);
  const flags = [];
  for (const cut of turn.interruptions) flags.push(badge(`interrupted: ${cut.kind}${cut.reason ? ` (${cut.reason})` : ""}`, "warn"));
  if (turn.heard === null && call.report) flags.push(badge("nothing heard", "warn"));
  if (times && times.ttfa_ms === null && turn.heard) flags.push(badge("no audio", "warn"));
  const offset = call.startedAt ? `+${((turn.firstAt - call.startedAt) / 1000).toFixed(1)} s` : "";
  const head = el(
    "header",
    { class: "turn-head" },
    el("span", { class: "turn-no", text: `Turn ${turn.id}` }),
    el("span", { class: "muted small", text: offset }),
    flags,
  );
  const heard = el("p", { class: "heard", dir: "auto" }, el("span", { class: "who", text: "Heard" }), turn.heard === null ? el("span", { class: "muted", text: "(no transcript yet)" }) : turn.heard || el("span", { class: "muted", text: "(nothing)" }));
  const parts = [head, heard];
  if (turn.heardBy) {
    const by = `${turn.heardBy.provider} · ${turn.heardBy.model}`;
    parts.push(el("p", { class: "muted small heard-by", text: `Heard by ${by} · request ${ms(times?.stt_ms)}` }));
  }
  if (times) {
    const toolMs = tools.reduce((sum, t) => sum + (t.ms ?? 0), 0);
    parts.push(steps({ ...times, _tools: toolMs }), bars(times, scale));
  } else {
    parts.push(el("p", { class: "muted small", text: "Times come once the turn has settled." }));
  }
  for (const tool of tools) {
    const state = !tool.done ? badge("running") : tool.ok ? badge("ok", "good") : badge(`failed${tool.failure ? `: ${tool.failure}` : ""}`, "bad");
    parts.push(
      el(
        "div",
        { class: "item tool" },
        el("div", { class: "item-head" }, el("span", { class: "kind", text: "Tool" }), el("code", { text: tool.tool }), state, el("span", { class: "muted small", text: tool.done ? ms(tool.ms) : "" })),
        details(`${key}/tool/${tool.tool_call_id}/args`, "Arguments the model wrote", json(tool.arguments)),
        tool.done ? details(`${key}/tool/${tool.tool_call_id}/result`, "What it returned", json(tool.result)) : null,
      ),
    );
  }
  if (turn.readBack) {
    parts.push(
      el(
        "div",
        { class: "item action" },
        el("div", { class: "item-head" }, el("span", { class: "kind", text: "Read-back" }), el("code", { text: turn.readBack.action }), badge("asked for a yes", "info")),
        details(`${key}/draft`, "The draft read back", json(turn.readBack.draft)),
      ),
    );
  }
  if (turn.answer) {
    const good = turn.answer.decision === "yes";
    parts.push(
      el(
        "div",
        { class: "item action" },
        el("div", { class: "item-head" }, el("span", { class: "kind", text: "Yes rule" }), el("code", { text: turn.answer.action }), badge(turn.answer.decision, good ? "good" : "warn"), badge(`by ${turn.answer.by}`, turn.answer.by === "model" ? "info" : "")),
      ),
    );
  }
  for (const write of turn.writes) {
    const after = turn.answer ? write.at - turn.answer.at : null;
    parts.push(
      el(
        "div",
        { class: "item action" },
        el("div", { class: "item-head" }, el("span", { class: "kind", text: "Write" }), el("code", { text: write.action }), badge(write.kind, write.kind === "done" ? "good" : "bad"), el("span", { class: "muted small", text: after === null ? "" : `${seconds(after)} after the yes` })),
        el("p", { class: "muted small mono", text: `request ${write.request_id}` }),
        write.result ? details(`${key}/write/${write.request_id}`, "The write's result", json(write.result)) : null,
      ),
    );
  }
  for (const said of turn.said) {
    const played = Math.round(said.played * 100);
    parts.push(
      el(
        "div",
        { class: "item said" },
        el("div", { class: "item-head" }, el("span", { class: "kind", text: "Said" }), badge(`${played}% played`, played < 100 ? "warn" : "")),
        el("p", { dir: "auto", text: said.text || "(nothing)" }),
      ),
    );
  }
  for (const block of turn.guard) parts.push(el("p", { class: "note bad" }, badge("guard blocked"), ` ${block.reason}: a fixed phrase was said instead`));
  for (const failure of turn.failures) parts.push(el("p", { class: "note bad", text: failure.text }));
  const usage = usageDelta(turn, previousUsage);
  if (usage) parts.push(usage);
  return el("li", { class: "turn" }, parts);
}

function replyCard(call, reply) {
  const offset = call.startedAt ? `+${((reply.at - call.startedAt) / 1000).toFixed(1)} s` : "";
  return el(
    "li",
    { class: "turn agent-only" },
    el("header", { class: "turn-head" }, el("span", { class: "turn-no", text: "Agent" }), el("span", { class: "muted small", text: `${offset} · answers no turn (the greeting, an outcome, a notice)` }), badge(`${Math.round(reply.played * 100)}% played`)),
    el("p", { dir: "auto", text: reply.text || "(nothing)" }),
  );
}

function drawChosen() {
  const call = view.calls.get(view.chosen);
  $("no-turns").hidden = Boolean(call);
  $("export").disabled = !call;
  if (!call) {
    $("turns").replaceChildren();
    $("summary").replaceChildren();
    return;
  }
  $("turns-title").textContent = `Turns · call ${call.id.slice(0, 10)}`;
  const turns = [...call.turns.values()].sort((a, b) => a.id - b.id);
  const ttfas = turns.map((t) => t.times?.ttfa_ms).filter((v) => typeof v === "number");
  const longest = Math.max(1500, ...turns.flatMap((t) => (t.times ? [t.times.ttfa_ms, t.times.played_ms, t.times.end_of_turn_ms, t.times.llm_first_token_ms] : [])).filter((v) => typeof v === "number"));
  const items = [];
  let usage = null;
  for (const turn of turns) {
    items.push({ at: turn.firstAt, node: turnCard(call, turn, longest, usage) });
    usage = turn.usage ?? usage;
  }
  for (const reply of call.replies) items.push({ at: reply.at, node: replyCard(call, reply) });
  items.sort((a, b) => a.at - b.at);
  $("turns").replaceChildren(...items.map((item) => item.node));
  drawSummary(call, turns, ttfas);
  drawLog(call);
}

function drawSummary(call, turns, ttfas) {
  const report = call.report;
  const duration = report ? (Date.parse(report.ended_at) - Date.parse(report.started_at)) : call.startedAt ? Date.now() - call.startedAt : null;
  const metric = (label, value, hint) => el("div", { class: "metric" }, el("span", { class: "muted small", text: label }), el("strong", { text: value }), hint ? el("span", { class: "muted small", text: hint }) : null);
  const eots = turns.map((t) => t.times?.end_of_turn_ms).filter((v) => typeof v === "number");
  const tokens = turns.map((t) => t.times?.llm_first_token_ms).filter((v) => typeof v === "number");
  const cuts = turns.reduce((sum, t) => sum + t.interruptions.length, 0);
  const toolCalls = [...call.tools.values()];
  const sections = [
    el(
      "div",
      { class: "metrics" },
      metric("TTFA median", ms(median(ttfas)), ttfas.length ? `worst ${ms(Math.max(...ttfas))}` : "no turn yet"),
      metric("End of turn median", ms(median(eots))),
      metric("First token median", ms(median(tokens))),
      metric("Turns", String(turns.length), `${cuts} interruption${cuts === 1 ? "" : "s"}`),
      metric("Tool calls", String(toolCalls.length), `${toolCalls.filter((t) => t.done && !t.ok).length} failed`),
      metric("Duration", duration === null ? "–" : seconds(duration), report ? `ended: ${report.ended_by}` : "live"),
    ),
  ];
  sections.push(el("h3", { text: "Model usage" }, el("span", { class: "muted small", text: report ? " the call's total" : " so far" })));
  sections.push(usageTable(call.usage));
  sections.push(el("h3", { text: "Record of actions" }));
  sections.push(
    call.record.length
      ? el("ul", { class: "record" }, call.record.map((w) => el("li", {}, el("code", { text: w.action }), " ", el("span", { class: "mono small", dir: "ltr", text: compact(w.result) }))))
      : el("p", { class: "muted small", text: "No completed action." }),
  );
  if (report?.client) {
    const c = report.client;
    sections.push(el("h3", { text: "Connection" }));
    sections.push(
      el("dl", { class: "pairs" }, [
        ["candidate", c.candidate_type ?? "–"],
        ["relay", c.relay_protocol ? `${c.relay_protocol} :${c.turn_port}` : "–"],
        ["connect", ms(c.connect_ms)],
        ["first audio played", ms(c.first_audio_ms)],
        ["echo cancellation", c.echo_cancellation === null ? "–" : String(c.echo_cancellation)],
      ].flatMap(([k, v]) => [el("dt", { text: k }), el("dd", { text: v })])),
    );
  }
  if (call.failures.length) {
    sections.push(el("h3", { text: "Call problems" }));
    sections.push(el("ul", {}, call.failures.map((f) => el("li", { class: "small", text: f.text ?? `interrupted: ${f.kind}` }))));
  }
  sections.push(el("p", { class: "muted small mono", dir: "ltr", text: `call ${call.id}${report?.consent_version ? ` · consent ${report.consent_version}` : ""}` }));
  $("summary").replaceChildren(...sections);
}

function compact(text) {
  try {
    return JSON.stringify(JSON.parse(text));
  } catch {
    return text || "";
  }
}

function usageTable(usage) {
  if (!usage?.length) return el("p", { class: "muted small", text: "No request yet." });
  const head = el("tr", {}, ["Model", "Req.", "Used"].map((h) => el("th", { scope: "col", text: h })));
  // What each model used, by its kind: tokens for a chat model, audio for speech-to-text,
  // characters (and phrases played from the cache) for a voice.
  const used = (u) =>
    [
      u.input_tokens || u.output_tokens ? `${u.input_tokens} in / ${u.output_tokens} out tokens${u.cached_tokens ? `, ${u.cached_tokens} cached` : ""}` : null,
      u.audio_sent_s ? `${u.audio_sent_s.toFixed(1)} s audio, ${u.billed_s.toFixed(0)} s billed` : null,
      u.characters ? `${u.characters} characters` : null,
      u.cache_hits ? `${u.cache_hits} from the phrase cache` : null,
    ].filter(Boolean).join(" · ") || "–";
  const rows = usage.map((u) =>
    el("tr", {}, el("td", { class: "mono model", text: u.model }), el("td", { text: String(u.requests) }), el("td", { class: "small", text: used(u) })),
  );
  const headroom = usage.filter((u) => u.remaining_requests !== null || u.remaining_tokens !== null).map((u) => `${u.model}: ${u.remaining_requests ?? "–"} requests, ${u.remaining_tokens ?? "–"} tokens left`);
  return el("div", {}, el("table", { class: "usage" }, el("thead", {}, head), el("tbody", {}, rows)), headroom.length ? el("p", { class: "muted small", text: `Headroom: ${headroom.join(" · ")}` }) : null);
}

// What one record says, short, for the event log.
function gist(record) {
  const e = record.event;
  switch (record.type) {
    case "UserTurnEnded": return e.heard ? `heard: ${e.heard}` : "heard nothing";
    case "TurnMetrics": return `ttfa ${ms(e.ttfa_ms)} · eot ${ms(e.end_of_turn_ms)} · stt ${ms(e.stt_ms)} · token ${ms(e.llm_first_token_ms)}`;
    case "ToolStarted": return `${e.tool} ${compact(e.arguments)}`;
    case "ToolFinished": return `${e.tool} ${e.ok ? "ok" : `failed ${e.failure ?? ""}`} in ${ms(e.ms)}`;
    case "AgentSpeechEnded": return `${Math.round(e.played_fraction * 100)}% played: ${e.text}`;
    case "Interrupted": return `${e.kind}${e.reason ? ` (${e.reason})` : ""}`;
    case "ConfirmationRequested": return `${e.action} read back`;
    case "ConfirmationAnswered": return `${e.action}: ${e.decision} by ${e.by}`;
    case "ActionCompleted": return `${e.action} done ${compact(e.result)}`;
    case "ActionUnconfirmed": return `${e.action} ${e.kind}`;
    case "GuardBlocked": return e.reason;
    case "ProviderFailed": return `${e.kind}${e.retryable ? " (retryable)" : ""}`;
    case "TransportFailed": return e.stage;
    case "CallEnded": return `ended: ${e.report.ended_by}`;
    default: return "";
  }
}

function drawLog(call) {
  const kinds = [...new Set(call.records.map((r) => r.type))].sort();
  const filter = $("log-filter");
  const wanted = filter.value;
  filter.replaceChildren(el("option", { value: "", text: "every event" }), ...kinds.map((k) => el("option", { value: k, text: k })));
  filter.value = kinds.includes(wanted) ? wanted : "";
  const shown = call.records.filter((r) => !filter.value || r.type === filter.value).slice(-MAX_LOG_ROWS);
  $("log-count").textContent = `${call.records.length} events`;
  $("log").replaceChildren(
    ...shown.map((r) => {
      const at = call.startedAt ? `+${((Date.parse(r.event.at) - call.startedAt) / 1000).toFixed(2)} s` : r.event.at;
      return el("tr", {}, el("td", { class: "mono small", text: at }), el("td", {}, el("code", { text: r.type })), el("td", { text: r.event.turn_id ?? "–" }), el("td", { class: "small", dir: "auto", text: gist(r) }));
    }),
  );
}

function exportCall() {
  const call = view.calls.get(view.chosen);
  if (!call) return;
  const body = JSON.stringify({ setup: view.setup, call_id: call.id, records: call.records }, null, 2);
  const link = el("a", { href: URL.createObjectURL(new Blob([body], { type: "application/json" })), download: `t2v-call-${call.id}.json` });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

// ---------------------------------------------------------------------------------------------
// This page's call, through the library's client.

const captions = new Map();

function running(on) {
  $("start").disabled = on;
  $("stop").disabled = !on;
  $("hangup").disabled = !on;
  $("talk").disabled = !on || !$("push-to-talk").checked;
}

function talk(held) {
  $("talk").setAttribute("aria-pressed", String(held));
  view.own?.talk(held);
}

function caption(c) {
  const key = c.speaker === "agent" ? `agent ${c.reply_id}` : `caller ${c.turn_id}`;
  if (!captions.has(key)) {
    const item = el("li", { class: `caption ${c.speaker}` }, el("span", { class: "who", text: c.speaker === "agent" ? "Agent" : "Caller" }), el("span", { class: "words" }));
    captions.set(key, { item, parts: [] });
    $("captions").append(item);
    item.scrollIntoView({ block: "nearest" });
  }
  const shown = captions.get(key);
  shown.parts[c.speaker === "agent" ? c.clause : 0] = c.cut ? `${c.text} …[cut]` : c.text;
  shown.item.querySelector(".words").textContent = shown.parts.filter(Boolean).join(" ");
}

function card(c) {
  if (!c) {
    $("card").hidden = true;
    return;
  }
  $("card").replaceChildren(
    el("h3", { dir: "auto", text: c.title }),
    el("ol", {}, c.steps.map((step) => el("li", { dir: "auto", text: step }))),
    c.source ? el("p", { class: "muted small", text: `Source: ${c.source}` }) : null,
  );
  $("card").hidden = false;
}

function state(name) {
  $("state").dataset.state = name;
  $("state").textContent = name;
}

// The token this page's call joins with, and where it came from: the field's, as typed; with
// the field empty, one the console makes for the app's dev caller (POST dev/token), the box
// saying whether the call's audio may be kept; and `dev` when it makes none (no dev caller
// declared, or no join key that signs: a plain 404), which `t2v dev`'s identity takes.
async function joinToken() {
  const typed = $("token").value;
  if (typed) return { token: typed, from: "the token typed" };
  try {
    const response = await fetch("token", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ record_audio: $("keep-audio").checked }),
      cache: "no-store",
    });
    const body = response.ok ? await response.json() : null;
    if (typeof body?.token === "string" && body.token) return { token: body.token, from: "a token for the app's dev caller" };
  } catch {
    // none made: joined as dev
  }
  return { token: "dev", from: "dev (no token made: no dev caller, or no join key that signs)" };
}

// ---------------------------------------------------------------------------------------------
// The speech-to-text pickers: what this process can use (GET dev/stt), the settings' own choice
// first, the last one picked remembered in this browser alone.

const stt = { menu: null };

function remembered() {
  try {
    return JSON.parse(localStorage.getItem(STT_KEY) ?? "null");
  } catch {
    return null;
  }
}

function remember(choice) {
  try {
    localStorage.setItem(STT_KEY, JSON.stringify(choice));
  } catch {
    // no storage here (a private window, blocked site data): the pickers still work
  }
}

function options(select, values, chosen) {
  select.replaceChildren(...values.map((value) => el("option", { value, text: value })));
  select.value = values.includes(chosen) ? chosen : values[0];
}

function models() {
  const option = stt.menu.providers.find((p) => p.provider === $("stt-provider").value);
  options($("stt-model"), option ? option.models : [], $("stt-model").value);
}

function pickedChoice() {
  if (!stt.menu) return null;
  return { provider: $("stt-provider").value, model: $("stt-model").value, live_language: $("stt-language").value };
}

async function loadStt() {
  try {
    const response = await fetch("stt", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    stt.menu = await response.json();
  } catch (error) {
    $("stt-note").textContent = `Speech-to-text choices unavailable (${error.message}): calls use the settings' own.`;
    return;
  }
  const menu = stt.menu;
  const kept = remembered() ?? {};
  const pick = (value, allowed, fallback) => (allowed.includes(value) ? value : fallback);
  const providers = menu.providers.map((p) => p.provider);
  options($("stt-provider"), providers, pick(kept.provider, providers, menu.default.provider));
  const option = menu.providers.find((p) => p.provider === $("stt-provider").value);
  options($("stt-model"), option.models, pick(kept.model, option.models, option.models[0]));
  options($("stt-language"), menu.live_languages, pick(kept.live_language, menu.live_languages, menu.default.live_language));
  for (const id of ["stt-provider", "stt-model", "stt-language"]) $(id).disabled = false;
  const d = menu.default;
  $("stt-note").textContent = `The settings' own: ${d.provider} · ${d.model} · ${d.live_language}. Only providers with a key set are listed.`;
}

$("stt-provider").addEventListener("change", () => {
  models();
  remember(pickedChoice());
});
for (const id of ["stt-model", "stt-language"]) $(id).addEventListener("change", () => remember(pickedChoice()));

async function start() {
  running(true);
  captions.clear();
  $("captions").replaceChildren();
  card(null);
  $("live").hidden = false;
  $("status").textContent = "Starting: allow the microphone.";
  try {
    // As the widget does: the client asks for the token once the microphone is open, inside
    // the click's start, so a slow microphone prompt never outlives the token.
    view.own = await VoiceClient.start({
      base: "..",
      getToken: async () => {
        const joining = await joinToken();
        $("status").textContent = `Joining with ${joining.from}.`;
        return joining.token;
      },
      language: $("language").value || undefined,
      sttChoice: pickedChoice() ?? undefined,
      pushToTalk: $("push-to-talk").checked,
      on: {
        hello: (h) => {
          $("status").textContent = `Connected: call ${h.call_id}.`;
          view.chosen = h.call_id;
          drawCalls();
          drawChosen();
        },
        state: (s) => state(s.state),
        caption,
        card,
        volume: (v) => ($("volume").textContent = `${Math.round(v.level * 100)}%`),
        notice: (n) => ($("status").textContent = `Notice (${n.kind}): ${n.text}`),
        connection: (c) => ($("connection").textContent = c.state),
        error: (e) => ($("status").textContent = `${e.code}: ${e.message}`),
        ended: (e) => {
          $("status").textContent = `Ended: ${e.reason}.`;
          state("idle");
          running(false);
          talk(false);
          view.own = null;
        },
      },
    });
    view.own.pushToTalk = $("push-to-talk").checked;
    running(true);
    $("status").textContent = `Joined call ${view.own.callId}.`;
  } catch (error) {
    $("status").textContent = `${error.code ?? "error"}: ${error.notice ?? error.message}`;
    running(false);
  }
}

$("start").addEventListener("click", start);
$("stop").addEventListener("click", () => view.own?.stop());
$("hangup").addEventListener("click", () => view.own?.hangup());
$("push-to-talk").addEventListener("change", () => {
  if (view.own) view.own.pushToTalk = $("push-to-talk").checked;
  talk(false);
  running(Boolean(view.own));
});
$("talk").addEventListener("pointerdown", (event) => {
  if ($("talk").disabled) return;
  $("talk").setPointerCapture?.(event.pointerId);
  talk(true);
});
for (const name of ["pointerup", "pointercancel", "lostpointercapture"]) $("talk").addEventListener(name, () => talk(false));
$("export").addEventListener("click", exportCall);
$("log-filter").addEventListener("change", () => drawLog(view.calls.get(view.chosen)));
$("follow").addEventListener("change", () => {
  if ($("follow").checked && view.calls.size) {
    view.chosen = [...view.calls.keys()].at(-1);
    drawCalls();
    drawChosen();
  }
});
// A live call's duration ticks while nothing else changes.
setInterval(() => {
  const call = view.calls.get(view.chosen);
  if (call && !call.report) drawSummary(call, [...call.turns.values()], [...call.turns.values()].map((t) => t.times?.ttfa_ms).filter((v) => typeof v === "number"));
}, 1000);

loadSetup().then(() => drawChosen());
loadStt();
poll();
