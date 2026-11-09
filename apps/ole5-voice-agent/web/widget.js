// Ole5's voice widget (index.html), on the library's reference client, served from the same
// address as the token route (/token) and the library's router (/voice).
//
// The caller picks a language (Arabic first), types the owner's access code, may tick the box
// to keep the call's audio (off by default; no consent screen, D-076) and starts the call. The
// client opens the microphone first, so a missing,
// busy or refused microphone is told before a token is asked for; the token route mints a join
// token carrying that choice, which no later message changes. Stop and Esc cut the
// agent short; End hangs up. A clause a stop cut while it played is shown cut. Push-to-talk, a
// switch the caller may turn on before or during the call, keeps the microphone off except while
// Space or the talk button is held: the fallback when the agent's voice comes back through the
// laptop's speakers. While the agent thinks (its talker or a tool at work) the state line says
// so beside a pulsing dot. A tool's card, when one is sent, sits above the captions, so the
// captions growing below never move it: its title, its steps numbered and the document they come
// from. Each line of it takes the direction of its own first strong character (dir="auto"), so
// an Arabic step reads right to left and an English one left to right in either language; a new
// card replaces the last, and a new call clears it. Every text, the captions, card and notices
// included, is set with textContent.

import { VoiceClient } from "./voice/client/1/t2v-client.js";

// The version the join token carries: the server's privacy.consent_version
// (T2V_PRIVACY__CONSENT_VERSION) is set to it for the owner's recorded calls, and /join refuses
// a token of another, so it does not change.
export const CONSENT_VERSION = "m2-owner-test-1";

const TEXT = {
  ar: {
    title: "المساعد الصوتي لـ Ole5",
    record: "سجّل صوت هذه المكالمة، ويُحفظ على هذا الجهاز لتجربة المساعد.",
    code: "رمز الدخول",
    start: "ابدأ المكالمة",
    stop: "إيقاف",
    end: "أنهِ المكالمة",
    pushToTalk: "التحدث بالضغط (اضغط مطولاً على المسافة أو على الزر)",
    talk: "اضغط مطولاً للتحدث",
    states: { listening: "يسمعك الآن", thinking: "يفكر", speaking: "يتكلم", confirming: "يتأكد" },
    starting: "جارٍ الاتصال",
    you: "أنت",
    agent: "المساعد",
    source: "المصدر:",
    ended: "انتهت المكالمة.",
    lost: "انقطع الاتصال.",
    microphone_missing: "لم يُعثر على ميكروفون. وصّل ميكروفوناً وحاول مرة أخرى.",
    microphone_busy: "تطبيق آخر يستخدم الميكروفون. أغلقه وحاول مرة أخرى.",
    microphone_refused: "المتصفح منع الميكروفون عن هذه الصفحة. اسمح به ثم حاول مرة أخرى.",
    microphone_failed: "تعذّر فتح الميكروفون.",
    wrong_code: "رمز الدخول غير صحيح.",
    slowed: "محاولات كثيرة: حاول مرة أخرى بعد {s} ثانية.",
    daily_limit: "بلغت المكالمات حدّها لهذا اليوم.",
    closed: "أُغلق الدخول بعد محاولات كثيرة غير صحيحة، حتى يُعاد تشغيل الخادم.",
    network: "تعذّر الوصول إلى الخادم.",
    join_rejected: "رُفض الدخول إلى المكالمة. ابدأ مكالمة جديدة.",
    failed: "تعذّر بدء المكالمة. حاول مرة أخرى.",
  },
  en: {
    title: "Ole5 voice assistant",
    record: "Record this call's audio, kept on this laptop to test the agent.",
    code: "Access code",
    start: "Start the call",
    stop: "Stop",
    end: "End the call",
    pushToTalk: "Push to talk (hold Space or the button)",
    talk: "Hold to talk",
    states: { listening: "Listening", thinking: "Thinking", speaking: "Speaking", confirming: "Confirming" },
    starting: "Connecting",
    you: "You",
    agent: "Assistant",
    source: "Source:",
    ended: "The call has ended.",
    lost: "The connection was lost.",
    microphone_missing: "No microphone was found. Connect one and try again.",
    microphone_busy: "Another program is using the microphone. Close it and try again.",
    microphone_refused: "The browser blocked the microphone for this page. Allow it, then try again.",
    microphone_failed: "The microphone could not be opened.",
    wrong_code: "The access code is not right.",
    slowed: "Too many tries: try again in {s} s.",
    daily_limit: "Today's calls have reached their limit.",
    closed: "Too many wrong codes: sign-in is closed until the server restarts.",
    network: "The server could not be reached.",
    join_rejected: "The call could not be joined. Start a new one.",
    failed: "The call could not start. Try again.",
  },
};

const page = { language: "ar-SA", call: null, captions: new Map() };
const $ = (id) => document.getElementById(id);
const words = () => TEXT[page.language === "en" ? "en" : "ar"];

class TokenError extends Error {
  constructor(code, retryAfter = null) {
    super(code);
    this.code = code;
    this.retryAfter = retryAfter;
  }
}

function render() {
  const english = page.language === "en";
  document.documentElement.lang = english ? "en" : "ar";
  document.documentElement.dir = english ? "ltr" : "rtl";
  for (const node of document.querySelectorAll("[data-text]")) {
    node.textContent = words()[node.dataset.text];
  }
  for (const button of document.querySelectorAll("button.language")) {
    button.setAttribute("aria-pressed", String(button.dataset.language === page.language));
  }
}

function running(on) {
  $("start").disabled = on;
  $("stop").disabled = !on;
  $("end").disabled = !on;
  $("code").disabled = on;
  $("record").disabled = on;
  for (const button of document.querySelectorAll("button.language")) button.disabled = on;
  talkable();
}

// Push-to-talk's button: usable once the call exists, with the switch on; held while the call is
// still starting, it would show held and reach no call.
function talkable() {
  $("talk").disabled = $("end").disabled || !page.call || !$("push-to-talk").checked;
}

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

// The state line: its text, and the agent's state for widget.css (none once the call is over).
function state(text, now = "") {
  $("state").textContent = text;
  $("state").dataset.state = now;
}

function message(text) {
  $("message").textContent = text;
}

function messageFor(error) {
  if (typeof error?.notice === "string") return error.notice;
  const said = words()[error?.code];
  if (error?.code === "slowed") return said.replace("{s}", String(error.retryAfter ?? 1));
  return typeof said === "string" ? said : words().failed;
}

// A join token from the app's token route, for the owner's access code, carrying whether the
// box to keep the call's audio is ticked.
async function token() {
  let response;
  try {
    response = await fetch("token", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        code: $("code").value,
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
    who.textContent = agent ? words().agent : words().you;
    const said = document.createElement("span");
    item.append(who, said);
    $("captions").append(item);
    page.captions.set(key, { said, parts: [] });
  }
  // Each clause in its own span, so a clause a stop cut is styled cut (widget.css).
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

function ended(e) {
  page.call = null;
  talk(false);
  running(false);
  state(words().ended);
  if (e.reason === "transport") message(words().lost);
}

async function start() {
  if (page.call) return;
  message("");
  page.captions.clear();
  $("captions").replaceChildren();
  card(null);
  running(true);
  state(words().starting);
  try {
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
    call.pushToTalk = $("push-to-talk").checked; // switched while the call started
    page.call = call.closed ? null : call;
    talkable();
  } catch (error) {
    running(false);
    state("");
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
$("stop").addEventListener("click", () => page.call?.stop());
$("end").addEventListener("click", () => page.call?.hangup());
$("push-to-talk").addEventListener("change", () => {
  if (page.call) page.call.pushToTalk = $("push-to-talk").checked;
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
$("code").focus();
document.addEventListener("keydown", space);
document.addEventListener("keyup", space);
globalThis.addEventListener("blur", () => talk(false)); // a key let go in another window
render();
