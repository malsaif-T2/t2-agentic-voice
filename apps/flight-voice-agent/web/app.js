// The flight agent's page (index.html), on the library's reference client, served from the same
// address as the token route (/token), the page's routes (/api/...) and the library's router
// (/voice).
//
// The caller picks the page's language, which is also the call's starting language (Arabic
// first; mid-call the caller switches by voice), types the owner's access code once under
// Options (kept in this page's memory alone, never in storage), may tick the box to keep the
// call's audio (off by default; no consent screen, D-076) and starts the call with the one round
// button, which then ends it. The orb and the state line follow the call's `state` (listening,
// thinking, speaking, waiting for a yes), the orb also its sound (orb.js, decoration alone); the
// cards mirror what the agent said, each in its segment of the trip, outbound, return and review
// (cards.js); the captions sit in "Show conversation". The profile (`GET api/profile`) says
// whether the line books (`bookings`): only then are the traveler's name and tier, "Your trips"
// (bookings.js) and "Start over" shown, the review's status line waiting for the yes, then
// booked; on a line that books nothing (real flights: anyone calls, with no profile) the heading
// asks anyone where to fly, the brand is the assistant and its company, and no booking route is
// ever asked. The lines the caller could say are text, never buttons: the client has no typed
// text into a call. Every text, the captions, cards and notices included, is set with textContent.

import { VoiceClient } from "./voice/client/1/t2v-client.js";
import { Cards } from "./cards.js?v=2026-11-19";
import { Booking } from "./bookings.js?v=2026-11-19";
import { Orb } from "./orb.js?v=2026-11-19";
import { fill, wordsOf } from "./texts.js?v=2026-11-19";

// The version the join token carries: the server's privacy.consent_version, as Ole5's widget
// sends it, since both servers read the same .env.
export const CONSENT_VERSION = "m2-owner-test-1";

const $ = (id) => document.getElementById(id);
const page = { language: "ar-SA", call: null, code: "", profile: {}, captions: new Map(), said: "ready" };
const english = () => page.language === "en";
const words = () => wordsOf(page.language);
const cards = new Cards($("cards"), $("cards-section"), () => words().marks);
const booking = new Booking($, cards, words, () => page.language);
const orb = new Orb($("orb"));

class TokenError extends Error {
  constructor(code, retryAfter = null) {
    super(code);
    this.code = code;
    this.retryAfter = retryAfter;
  }
}

// One of the profile's texts in the page's language ("" when the profile has none).
function named(key) {
  const both = page.profile?.[key];
  const said = both && typeof both === "object" ? both[english() ? "en" : "ar"] : null;
  return typeof said === "string" ? said : "";
}

// The brand on a line that books nothing: the assistant and its company, or its name alone.
function brand() {
  const [persona, company, role] = ["persona", "company", "role"].map(named);
  return persona && company && role ? fill(words().brandFree, { persona, company, role }) : persona;
}

function render() {
  document.documentElement.lang = english() ? "en" : "ar";
  document.documentElement.dir = english() ? "ltr" : "rtl";
  for (const node of document.querySelectorAll("[data-text]")) {
    node.textContent = words()[node.dataset.text];
  }
  for (const button of document.querySelectorAll("button.language")) {
    button.setAttribute("aria-pressed", String(button.dataset.language === page.language));
  }
  // Only a profile that says the line books (the mock's) shows a traveler.
  const books = page.profile?.bookings === true;
  const name = books ? named("first_name") : "";
  const asked = name ? fill(words().heading, { name }) : words().headingNoName;
  $("heading").textContent = books ? asked : words().headingFree;
  $("brand").textContent = books ? named("airline") : brand();
  $("assistant").textContent = books && named("persona")
    ? fill(words().assistant, { persona: named("persona"), airline: named("airline") })
    : "";
  $("traveler").textContent = name ? fill(words().traveler, { name, tier: named("tier") }) : "";
  const lines = page.profile?.lines?.[english() ? "en" : "ar"];
  $("lines").replaceChildren(
    ...(Array.isArray(lines) ? lines : []).filter((l) => typeof l === "string").map((said) => {
      const line = document.createElement("li");
      line.dir = "auto";
      line.textContent = english() ? `“${said}”` : `«${said}»`;
      return line;
    }),
  );
  $("state").textContent = saying(page.said);
  booking.shown = books;
  cards.render();
}

async function profile() {
  try {
    const response = await fetch("api/profile", { cache: "no-store" });
    const body = await response.json();
    if (response.ok && body && typeof body === "object") page.profile = body;
  } catch {
    page.profile = {};
  }
  render();
}

// The one round button: start while no call runs, end while one does.
function running(on) {
  for (const [id, shown] of [["start", !on], ["end", on]]) {
    $(id).disabled = !shown;
    $(id).hidden = !shown;
  }
  $(on ? "end" : "start").focus?.();
  $("code").disabled = on;
  $("record").disabled = on;
  for (const button of document.querySelectorAll("button.language")) button.disabled = on;
  talkable();
}

function talkable() {
  $("talk").disabled = $("end").disabled || !page.call || !$("push-to-talk").checked;
}

function talk(held) {
  $("talk").setAttribute("aria-pressed", String(held));
  orb.hush = $("push-to-talk").checked && !held;
  page.call?.talk(held);
}

function space(event) {
  if (event.code !== "Space" || !page.call || !$("push-to-talk").checked) return;
  event.preventDefault();
  if (event.type === "keyup") talk(false);
  else if (!event.repeat) talk(true);
}

// The text of `key` among the page's words ("states.listening" names a nested one).
function saying(key) {
  const said = key.split(".").reduce((at, part) => at?.[part], words());
  return typeof said === "string" ? said : "";
}

// The state line (its text by `key`) and the orb: the agent's state `now`, none once over.
function state(key, now = "") {
  page.said = key;
  $("state").textContent = saying(key);
  $("state").dataset.state = now;
  orb.state = now;
}

function message(text) {
  $("message").textContent = text;
}

function messageFor(error) {
  if (typeof error?.notice === "string") return error.notice;
  const said = words()[error?.code];
  if (error?.code === "slowed") return fill(said, { s: error.retryAfter ?? 1 });
  return typeof said === "string" ? said : words().failed;
}

// A join token from the app's token route, for the access code, carrying the box's choice.
async function token() {
  let response;
  try {
    response = await fetch("token", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        code: page.code,
        consent: { version: CONSENT_VERSION, record_audio: $("record").checked },
      }),
      cache: "no-store",
    });
  } catch {
    throw new TokenError("network");
  }
  const body = await response.json().catch(() => ({}));
  if (response.ok && typeof body.token === "string") return body.token;
  const retryAfter = Number(response.headers.get("retry-after")) || null;
  throw new TokenError(typeof body.code === "string" ? body.code : "failed", retryAfter);
}

function caption(c) {
  const agent = c.speaker === "agent";
  const key = agent ? `agent ${c.reply_id}` : `caller ${c.turn_id}`;
  if (!page.captions.has(key)) {
    const item = document.createElement("li");
    item.className = agent ? "agent" : "caller";
    item.dir = "auto";
    const who = document.createElement("span");
    who.className = "who";
    who.textContent = agent ? named("persona") || words().agent : words().you;
    const said = document.createElement("span");
    item.append(who, said);
    $("captions").append(item);
    page.captions.set(key, { said, parts: [] });
  }
  const shown = page.captions.get(key);
  const index = agent ? c.clause : 0;
  if (!shown.parts[index]) {
    shown.parts[index] = document.createElement("span");
    const parts = shown.parts.filter(Boolean);
    shown.said.replaceChildren(...parts.flatMap((part, at) => (at ? [" ", part] : [part])));
  }
  shown.parts[index].textContent = c.text;
  shown.parts[index].classList.toggle("cut", c.cut === true);
}

function ended(e) {
  page.call = null;
  orb.end();
  talk(false);
  running(false);
  state("ended");
  if (e.reason === "transport") message(words().lost);
  booking.ended();
}

async function start() {
  if (page.call) return;
  page.code = $("code").value.trim() || page.code;
  if (!page.code) {
    $("options").setAttribute("open", "");
    message(words().needCode);
    return;
  }
  const audio = new Audio(); // made in the click, before any await: the page may play it
  orb.begin(audio);
  message("");
  page.captions.clear();
  $("captions").replaceChildren();
  cards.clear();
  running(true);
  state("starting", "connecting");
  await booking.started();
  try {
    const call = await VoiceClient.start({
      base: "voice",
      language: page.language,
      getToken: token,
      audio,
      pushToTalk: $("push-to-talk").checked,
      on: {
        state: (s) => {
          state(`states.${s.state}`, s.state);
          booking.reviewed(s.state);
        },
        caption,
        card: (card) => {
          cards.add(card);
          booking.carded(card);
        },
        notice: (n) => message(n.text),
        ended,
      },
    });
    call.pushToTalk = $("push-to-talk").checked;
    page.call = call.closed ? null : call;
    if (page.call) orb.listen();
    talkable();
  } catch (error) {
    orb.end();
    running(false);
    state("ready");
    message(messageFor(error));
  }
}

for (const button of document.querySelectorAll("button.language")) {
  button.addEventListener("click", () => {
    page.language = button.dataset.language;
    render();
  });
}
$("start").addEventListener("click", start);
$("end").addEventListener("click", () => page.call?.hangup());
$("push-to-talk").addEventListener("change", () => {
  if (page.call) page.call.pushToTalk = $("push-to-talk").checked;
  talk(false);
  talkable();
});
$("talk").addEventListener("pointerdown", (event) => {
  if ($("talk").disabled) return;
  $("talk").setPointerCapture?.(event.pointerId);
  talk(true);
});
for (const name of ["pointerup", "pointercancel", "lostpointercapture"]) {
  $("talk").addEventListener(name, () => talk(false));
}
document.addEventListener("keydown", space);
document.addEventListener("keyup", space);
globalThis.addEventListener("blur", () => talk(false));
render();
profile();
