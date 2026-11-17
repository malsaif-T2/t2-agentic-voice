// The flight agent's page (index.html), on the library's reference client, served from the same
// address as the token route (/token), the page's routes (/api/...) and the library's router
// (/voice).
//
// The caller picks the page's language, which is also the call's starting language (Arabic
// first; mid-call the caller switches by voice), types the owner's access code once under
// Options (kept in this page's memory alone, never in storage), may tick the box to keep the
// call's audio (off by default; no consent screen, D-076) and starts the call. The orb and the
// state line follow the call's `state` (listening, thinking, speaking, waiting for a yes); the
// cards mirror what the agent said, each in its segment of the trip, outbound, return and
// review (cards.js), the review's status line waiting for the yes, then booked; the captions sit
// in "Show conversation"; "Your trips" lists the bookings (bookings.js). The lines the caller could say
// are text, never buttons: the client has no typed text into a call. Every text, the captions,
// cards and notices included, is set with textContent.

import { VoiceClient } from "./voice/client/1/t2v-client.js";
import { Cards, complete, rowsOf } from "./cards.js";
import { Made, Trips, startOver } from "./bookings.js";
import { fill, wordsOf } from "./texts.js";

// The version the join token carries: the server's privacy.consent_version, as Ole5's widget
// sends it, since both servers read the same .env.
export const CONSENT_VERSION = "m2-owner-test-1";

const $ = (id) => document.getElementById(id);
const page = { language: "ar-SA", call: null, code: "", profile: {}, captions: new Map() };
const english = () => page.language === "en";
const words = () => wordsOf(page.language);
const cards = new Cards($("cards"), $("cards-section"), () => words().marks);
const trips = new Trips($("trips-list"), $("trips-filter"), $("trips-note"));
const made = new Made(trips);

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

function render() {
  document.documentElement.lang = english() ? "en" : "ar";
  document.documentElement.dir = english() ? "ltr" : "rtl";
  for (const node of document.querySelectorAll("[data-text]")) {
    node.textContent = words()[node.dataset.text];
  }
  for (const button of document.querySelectorAll("button.language")) {
    button.setAttribute("aria-pressed", String(button.dataset.language === page.language));
  }
  const name = named("first_name");
  $("heading").textContent = name ? fill(words().heading, { name }) : words().headingNoName;
  $("airline").textContent = named("airline");
  $("assistant").textContent = named("persona")
    ? fill(words().assistant, { persona: named("persona"), airline: named("airline") })
    : "";
  $("traveler").textContent = name ? fill(words().traveler, { name, tier: named("tier") }) : "";
  const lines = page.profile?.lines?.[english() ? "en" : "ar"];
  $("lines").replaceChildren(
    ...(Array.isArray(lines) ? lines : []).filter((l) => typeof l === "string").map((said) => {
      const line = document.createElement("li");
      line.dir = "auto";
      line.textContent = `“${said}”`;
      return line;
    }),
  );
  trips.render(page.language, words());
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

function running(on) {
  $("start").disabled = on;
  $("end").disabled = !on;
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
  page.call?.talk(held);
}

function space(event) {
  if (event.code !== "Space" || !page.call || !$("push-to-talk").checked) return;
  event.preventDefault();
  if (event.type === "keyup") talk(false);
  else if (!event.repeat) talk(true);
}

// The state line and the orb: the agent's state, none once the call is over.
function state(text, now = "") {
  $("state").textContent = text;
  $("state").dataset.state = now;
  $("orb").dataset.state = now;
}

// The review segment's status: waiting for the yes from when the whole trip is shown for review
// (or a read-back is asked) while the call goes on, then booked with its reference once the
// booking this call made is found (bookings.js's `Made`); the state `now`, "" once it ended.
async function reviewed(now) {
  const ref = await made.seen(now);
  const waiting = made.asked && now ? words().waiting : "";
  cards.setStatus(ref ? fill(words().bookedRef, { ref }) : waiting);
}

// A card, in its segment (cards.js): a leg's card lists a new leg, so the last booking is
// forgotten; the whole trip's review card waits for the yes.
function carded(card) {
  cards.add(card);
  if (card?.slot === "outbound" || card?.slot === "return") made.forget();
  if (card?.slot === "review" && complete(rowsOf(card)) && !made.reference) {
    made.ask();
    cards.setStatus(words().waiting);
  }
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

async function showTrips() {
  trips.render(page.language, words());
}

function ended(e) {
  page.call = null;
  talk(false);
  running(false);
  state(words().ended);
  if (e.reason === "transport") message(words().lost);
  trips.load().then(() => reviewed("")).then(showTrips);
}

async function start() {
  if (page.call) return;
  page.code = $("code").value.trim() || page.code;
  if (!page.code) {
    $("options").setAttribute("open", "");
    message(words().needCode);
    return;
  }
  message("");
  page.captions.clear();
  $("captions").replaceChildren();
  cards.clear();
  running(true);
  state(words().starting);
  await made.start();
  try {
    const call = await VoiceClient.start({
      base: "voice",
      language: page.language,
      getToken: token,
      pushToTalk: $("push-to-talk").checked,
      on: {
        state: (s) => {
          state(words().states[s.state] ?? "", s.state);
          reviewed(s.state);
        },
        caption,
        card: carded,
        notice: (n) => message(n.text),
        ended,
      },
    });
    call.pushToTalk = $("push-to-talk").checked;
    page.call = call.closed ? null : call;
    talkable();
  } catch (error) {
    running(false);
    state("");
    message(messageFor(error));
  }
}

function openTrips(open) {
  $("trips").hidden = !open;
  $("trips-toggle").setAttribute("aria-expanded", String(open));
  return trips.watch(open, showTrips);
}

for (const button of document.querySelectorAll("button.language")) {
  button.addEventListener("click", () => {
    page.language = button.dataset.language;
    render();
  });
}
$("trips-toggle").addEventListener("click", () => openTrips($("trips").hidden));
for (const name of ["input", "change"]) $("trips-filter").addEventListener(name, showTrips);
$("start-over").addEventListener("click", () => {
  $("reset-ask").hidden = false;
});
$("reset-no").addEventListener("click", () => {
  $("reset-ask").hidden = true;
});
$("reset-yes").addEventListener("click", async () => {
  $("reset-ask").hidden = true;
  if (await startOver()) {
    cards.clear();
    await trips.load();
    await showTrips();
  }
});
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
