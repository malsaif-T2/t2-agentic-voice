// The call's speech-to-text, model and voice under Options (app.js; the owner's request of
// 2026-11-22): three menus filled from the server's own (`GET voice/choices`, the library's
// call choices, which list only what the server holds a key for), each set before a call and
// sent with it (the client's `choice`, by the offers' ids, between its join and its offer).
// Each menu starts on the server's own (marked "(default)"; "Server's own" first where no
// offer is), so a call with nothing changed sends nothing. A server that offers no choice (the
// route's 404, or anything but the menu) leaves them hidden, and none is ever sent. The choice
// lives in the selects alone, never in storage, a cookie or the address; every label is set
// with textContent.

// The groups: the menu's list, its default's key, the select's id, the choice's key.
const GROUPS = [
  { list: "stt", key: "stt", id: "choice-stt" },
  { list: "models", key: "model", id: "choice-model" },
  { list: "voices", key: "voice", id: "choice-voice" },
];

// The offers of a menu's list that name an id, as text.
function offers(list) {
  return (Array.isArray(list) ? list : []).filter(
    (offer) => offer && typeof offer === "object" && typeof offer.id === "string" && offer.id !== "",
  );
}

export class Choices {
  #menu = null;

  // `$` finds an element by id; `words` gives the page's texts in its language.
  constructor($, words) {
    this.$ = $;
    this.words = words;
  }

  // The server's menu, or none when it offers no choice (the module's comment).
  async load() {
    let menu = null;
    try {
      const response = await fetch("voice/choices", { cache: "no-store" });
      const body = response.ok ? await response.json() : null;
      if (body && typeof body === "object") {
        const given = body.default && typeof body.default === "object" ? body.default : {};
        menu = { default: {} };
        for (const group of GROUPS) {
          menu[group.key] = offers(body[group.list]);
          const id = given[group.key];
          menu.default[group.key] = menu[group.key].some((o) => o.id === id) ? id : null;
        }
      }
    } catch {
      menu = null;
    }
    this.#menu = menu;
    this.render();
  }

  // Each menu in the page's language, its value kept (the language switch), else the default.
  render() {
    const menu = this.#menu;
    const shown = menu !== null && GROUPS.some((group) => menu[group.key].length > 0);
    this.$("choices").hidden = !shown;
    if (!shown) return;
    const words = this.words();
    for (const group of GROUPS) {
      const select = this.$(group.id);
      const listed = menu[group.key];
      const fallback = menu.default[group.key];
      this.$(`${group.id}-field`).hidden = listed.length === 0;
      const kept = select.value;
      const options = [];
      if (fallback === null) options.push(this.#option("", words.choiceServer));
      for (const offer of listed) {
        const names = words.choiceNames ?? {};
        const name = Object.hasOwn(names, offer.id) ? names[offer.id] : offer.id;
        const label = offer.id === fallback ? `${name} ${words.choiceDefault}` : name;
        options.push(this.#option(offer.id, label));
      }
      select.replaceChildren(...options);
      const values = options.map((option) => option.value);
      select.value = values.includes(kept) && kept !== "" ? kept : fallback ?? "";
    }
  }

  // The menus usable (`on`) or not, as while a call runs.
  able(on) {
    for (const group of GROUPS) this.$(group.id).disabled = !on;
  }

  // The call's choice: each group whose value is neither the server's own nor the default, or
  // null when none is (so the call sends no choice).
  picked() {
    const menu = this.#menu;
    if (menu === null) return null;
    const choice = {};
    for (const group of GROUPS) {
      const value = this.$(group.id).value;
      const offered = menu[group.key].some((offer) => offer.id === value);
      if (offered && value !== menu.default[group.key]) choice[group.key] = value;
    }
    return Object.keys(choice).length > 0 ? choice : null;
  }

  #option(value, label) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    return option;
  }
}
