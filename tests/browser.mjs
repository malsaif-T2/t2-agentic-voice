// A fake browser under Node for the suite's browser-side tests (tests/browser.py runs it): just
// enough DOM, media, fetch and WebRTC for a page's module to start a call and take t2v/1's
// messages, with nothing on the network and no audio. It reads one JSON object on stdin:
//   module    the file URL of the module to import (the client, or a page that imports it);
//   location  the page's address;
//   page      its elements in document order, each {tag, attrs, parent, text}, parent an index;
//   steps     what to do, in order, each {do, ...}: "click" an element, "set" an element's
//             value, "change" it (its change event), "start" a VoiceClient with listeners on every event, "open" the newest
//             data channel, "receive" text on it, "snapshot" an element; an element is named
//             by its `id`, or by `query`, [selector, n], the nth the selector finds;
//   answers   optional: more routes' answers, by "METHOD last-segment", as ANSWERS holds them,
//             or {"sequence": [answer, ...]}: each request the next, the last kept;
//   storage   optional: the page's localStorage, as text by key (none given: no localStorage,
//             as a browser that blocks it).
// It writes one JSON object on stdout: each snapshot, the events the started client gave, the
// messages the client sent, the requests it made, every console.error, and the localStorage
// left, then exits, whatever timers the page left running.
// Writing markup (innerHTML, outerHTML, insertAdjacentHTML, document.write) throws, so a page
// that tried would fail its test.

const NO_MARKUP = () => {
  throw new Error("markup written: a page sets text only");
};
const EVENTS = ["hello", "state", "caption", "card", "duck", "unduck", "volume", "notice",
  "ended", "connection", "error"];
const out = { snapshots: [], events: [], sent: [], requests: [], errors: [] };

class FakeNode extends EventTarget {
  parentNode = null;
  childNodes = [];
}

class FakeText extends FakeNode {
  constructor(text) {
    super();
    this.data = String(text);
  }

  get textContent() {
    return this.data;
  }
}

class FakeElement extends FakeNode {
  constructor(tag, attrs = {}) {
    super();
    this.localName = tag;
    this.attrs = new Map(Object.entries(attrs).map(([name, value]) => [name, value ?? ""]));
    this.value = attrs.value ?? "";
    this.checked = "checked" in attrs;
    this.dataset = new Proxy({}, {
      get: (_, key) => this.getAttribute(dataName(key)) ?? undefined,
      set: (_, key, value) => (this.setAttribute(dataName(key), value), true),
    });
    const classes = () => (this.getAttribute("class") ?? "").split(/\s+/).filter(Boolean);
    this.classList = {
      contains: (name) => classes().includes(name),
      toggle: (name, on = !classes().includes(name)) => {
        const kept = classes().filter((each) => each !== name);
        this.setAttribute("class", (on ? [...kept, name] : kept).join(" "));
        return on;
      },
    };
  }

  getAttribute(name) {
    return this.attrs.has(name) ? this.attrs.get(name) : null;
  }

  setAttribute(name, value) {
    this.attrs.set(name, String(value));
  }

  removeAttribute(name) {
    this.attrs.delete(name);
  }

  get textContent() {
    return this.childNodes.map((node) => node.textContent).join("");
  }

  set textContent(value) {
    this.replaceChildren(...(value === "" || value == null ? [] : [String(value)]));
  }

  append(...nodes) {
    for (const each of nodes) {
      const node = typeof each === "string" ? new FakeText(each) : each;
      if (node.parentNode) node.parentNode.childNodes.splice(node.parentNode.childNodes.indexOf(node), 1);
      node.parentNode = this;
      this.childNodes.push(node);
    }
  }

  replaceChildren(...nodes) {
    for (const node of this.childNodes) node.parentNode = null;
    this.childNodes = [];
    this.append(...nodes);
  }

  get children() {
    return this.childNodes.filter((node) => node instanceof FakeElement);
  }

  style = {};
  focus() {}
  scrollIntoView() {}
  setPointerCapture() {}
  set innerHTML(_) { NO_MARKUP(); }
  get innerHTML() { return NO_MARKUP(); }
  set outerHTML(_) { NO_MARKUP(); }
  insertAdjacentHTML() { NO_MARKUP(); }
}

// The attributes a page sets through properties, reflected as a browser does.
for (const name of ["id", "dir", "lang"]) {
  Object.defineProperty(FakeElement.prototype, name, {
    get() { return this.getAttribute(name) ?? ""; },
    set(value) { this.setAttribute(name, value); },
  });
}
Object.defineProperty(FakeElement.prototype, "className", {
  get() { return this.getAttribute("class") ?? ""; },
  set(value) { this.setAttribute("class", value); },
});
for (const name of ["hidden", "disabled"]) {
  Object.defineProperty(FakeElement.prototype, name, {
    get() { return this.attrs.has(name); },
    set(on) { if (on) this.setAttribute(name, ""); else this.removeAttribute(name); },
  });
}

function dataName(key) {
  return `data-${String(key).replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)}`;
}

function* tree(node) {
  for (const child of node.children) {
    yield child;
    yield* tree(child);
  }
}

// "[name]", "tag", ".class" and "tag.class": what the pages ask for.
function matches(element, selector) {
  const attribute = /^\[([a-z-]+)\]$/.exec(selector);
  if (attribute) return element.attrs.has(attribute[1]);
  const [tag, name] = selector.split(".");
  return (!tag || element.localName === tag) && (!name || element.classList.contains(name));
}

class FakeDocument extends EventTarget {
  constructor(elements) {
    super();
    const made = elements.map(({ tag, attrs }) => new FakeElement(tag, attrs));
    elements.forEach(({ parent, text }, at) => {
      if (parent !== null) made[parent].append(made[at]);
      if (text) made[at].append(text);
    });
    this.documentElement = made[0] ?? new FakeElement("html");
  }

  createElement(tag) {
    return new FakeElement(tag);
  }

  createTextNode(text) {
    return new FakeText(text);
  }

  getElementById(id) {
    for (const element of tree(this.root)) if (element.getAttribute("id") === id) return element;
    return null;
  }

  querySelectorAll(selector) {
    return [...tree(this.root)].filter((element) => matches(element, selector));
  }

  get root() {
    const holder = new FakeElement("#document");
    holder.childNodes = [this.documentElement];
    return holder;
  }

  write() { NO_MARKUP(); }
}

class FakeChannel extends EventTarget {
  readyState = "connecting";

  send(data) {
    out.sent.push(JSON.parse(data));
  }

  close() {
    this.readyState = "closed";
  }
}

const channels = [];

class FakePeer extends EventTarget {
  connectionState = "new";
  addTransceiver() { return { mid: "0" }; }
  createDataChannel() {
    const channel = new FakeChannel();
    channels.push(channel);
    return channel;
  }
  async createOffer() { return { type: "offer", sdp: "v=0 offer" }; }
  async setLocalDescription() {}
  async setRemoteDescription() {}
  async getStats() { return new Map(); }
  close() { this.connectionState = "closed"; }
}

class FakeTrack extends EventTarget {
  kind = "audio";
  enabled = true;
  stop() {}
  getSettings() { return { echoCancellation: true }; }
}

// The routes a call's start reaches: the app's token route, then the router's join and offer.
const ANSWERS = {
  "POST token": [200, { token: "made-up-token" }],
  "POST join": [200, { call_id: "c-1", offer_secret: "made-up-secret", ice_servers: [], protocol: 1 }],
  "POST offer": [200, { type: "answer", sdp: "v=0 answer" }],
  "PATCH offer": [204, null],
};

async function fetch(input, init = {}) {
  const url = new URL(String(input), globalThis.location.href);
  const method = init.method ?? "GET";
  out.requests.push({ method, path: url.pathname, body: JSON.parse(init.body ?? "null") });
  const given = ANSWERS[`${method} ${url.pathname.split("/").pop()}`] ?? [404, {}];
  const [status, body] = given.sequence ? (given.sequence.length > 1 ? given.sequence.shift() : given.sequence[0]) : given;
  return { ok: status < 400, status, json: async () => body, headers: { get: () => null } };
}

function define(name, value) {
  Object.defineProperty(globalThis, name, { value, configurable: true, writable: true });
}

async function settle() {
  for (let round = 0; round < 20; round += 1) await new Promise((done) => setTimeout(done, 0));
}

function snapshot(node) {
  if (node instanceof FakeText) return { text: node.data };
  return {
    tag: node.localName,
    attrs: Object.fromEntries(node.attrs),
    children: node.childNodes.map(snapshot),
  };
}

const input = JSON.parse(Buffer.concat(await Array.fromAsync(process.stdin)).toString("utf8"));
Object.assign(ANSWERS, input.answers ?? {});
if (input.storage) {
  const kept = new Map(Object.entries(input.storage));
  define("localStorage", {
    getItem: (key) => (kept.has(key) ? kept.get(key) : null),
    setItem: (key, value) => kept.set(key, String(value)),
  });
  out.storage = kept;
}
define("location", { href: input.location });
define("navigator", {
  mediaDevices: { getUserMedia: async () => {
    const track = new FakeTrack();
    return { getAudioTracks: () => [track], getTracks: () => [track] };
  } },
});
define("fetch", fetch);
define("Node", FakeNode);
define("RTCPeerConnection", FakePeer);
define("Audio", class { autoplay = false; volume = 1; srcObject = null; play() { return Promise.resolve(); } });
define("addEventListener", () => {});
define("removeEventListener", () => {});
define("document", new FakeDocument(input.page));
console.error = (...said) => out.errors.push(said.map(String).join(" "));

const module = await import(input.module);
await settle();
for (const step of input.steps) {
  // The element a step names: by its id, or as the nth of a selector's ([selector, n]).
  const named = step.id !== undefined || step.query !== undefined;
  const element = step.id !== undefined
    ? globalThis.document.getElementById(step.id)
    : step.query && (globalThis.document.querySelectorAll(step.query[0])[step.query[1]] ?? null);
  if (named && !element) throw new Error(`no element ${JSON.stringify(step.id ?? step.query)}`);
  if (step.do === "click") element.dispatchEvent(new Event("click"));
  else if (step.do === "change") element.dispatchEvent(new Event("change"));
  else if (step.do === "set") element.value = step.value;
  else if (step.do === "start") {
    const on = Object.fromEntries(EVENTS.map((name) => [name, (value) => out.events.push([name, value])]));
    await module.VoiceClient.start({ base: "/voice", token: "made-up-token", escape: false, on });
  } else if (step.do === "open") {
    const channel = channels.at(-1);
    channel.readyState = "open";
    channel.dispatchEvent(new Event("open"));
  } else if (step.do === "receive") {
    channels.at(-1).dispatchEvent(new MessageEvent("message", { data: step.data }));
  } else if (step.do === "snapshot") out.snapshots.push(snapshot(element));
  else throw new Error(`no step ${step.do}`);
  await settle();
}
if (out.storage) out.storage = Object.fromEntries(out.storage);
process.stdout.write(JSON.stringify(out), () => process.exit(0));
