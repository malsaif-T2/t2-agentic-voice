// Ole5's voice widget (index.html), on the library's reference client, served from the same
// address as the token route (/token) and the library's router (/voice).
//
// The caller picks a language (Arabic first), reads the consent screen (version
// CONSENT_VERSION, with a one-line box to record the call's audio) and agrees; then types the
// owner's access code and starts the call. The client opens the microphone first, so a missing,
// busy or refused microphone is told before a token is asked for; the token route mints a join
// token carrying the consent chosen here, which no later message changes. Stop and Esc cut the
// agent short; End hangs up. A clause a stop cut while it played is shown cut. Push-to-talk, a
// switch the caller may turn on before or during the call, keeps the microphone off except while
// Space or the talk button is held: the fallback when the agent's voice comes back through the
// laptop's speakers. Every text, the captions and notices included, is set with textContent.

import { VoiceClient } from "./voice/client/1/t2v-client.js";

// The consent text's version: the server's privacy.consent_version (T2V_PRIVACY__CONSENT_VERSION)
// is set to it for the owner's recorded calls, and /join refuses a token of another.
export const CONSENT_VERSION = "m2-owner-test-1";

const TEXT = {
  ar: {
    title: "المساعد الصوتي لـ Ole5",
    consentTitle: "قبل أن تبدأ",
    consentBody:
      "هذه مكالمة تجريبية مع المساعد الصوتي من T2، يعيد عليك ما يسمعه منك. يُرسل صوتك إلى Groq لتحويله إلى نص، ويُنطق الرد بصوت من Groq.",
    consentVersion: `نسخة الموافقة: ${CONSENT_VERSION}`,
    record: "سجّل صوت هذه المكالمة، ويُحفظ على هذا الجهاز لتجربة المساعد.",
    agree: "أوافق",
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
    consentTitle: "Before you start",
    consentBody:
      "This is a test call with T2's voice agent, which says back what it hears from you. Your voice is sent to Groq to be turned into text, and the reply is spoken in a voice from Groq.",
    consentVersion: `Consent version: ${CONSENT_VERSION}`,
    record: "Record this call's audio, kept on this laptop to test the agent.",
    agree: "I agree",
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
  for (const button of document.querySelectorAll("button.language")) button.disabled = on;
  talkable();
}

// Push-to-talk's button: usable while a call runs with the switch on.
function talkable() {
  $("talk").disabled = $("end").disabled || !$("push-to-talk").checked;
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

function state(text) {
  $("state").textContent = text;
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

// A join token from the app's token route, for the owner's access code, carrying the consent
// chosen on the consent screen.
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
  running(true);
  state(words().starting);
  try {
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
    call.pushToTalk = $("push-to-talk").checked; // switched while the call started
    page.call = call.closed ? null : call;
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
$("agree").addEventListener("click", () => {
  $("consent").hidden = true;
  $("call").hidden = false;
  $("code").focus();
});
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
document.addEventListener("keydown", space);
document.addEventListener("keyup", space);
globalThis.addEventListener("blur", () => talk(false)); // a key let go in another window
render();
