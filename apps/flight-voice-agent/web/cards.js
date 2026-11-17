// The cards a call shows (app.js), each in its segment of the page: each mirrors what the agent
// said, and the caller never needs one (D-075). A card names its segment (`slot`, D-110), one of
// `SLOTS`: `outbound`, the outbound flights (or a calendar of flights for a span of days);
// `return`, the return flights; `review`, the trip for confirmation. A card that names none, or
// another, is the one `extra` card shown after them (the cabins of a flight, the cheapest days).
// A new card for a segment replaces that segment's card. A leg's card never marks its own flights
// as picked: a row it marks `chosen` is the other leg's pick, kept beside them, so the page shows
// that row in the other leg's segment, in place of the row with its title (a flight's times),
// marked as the pick. The review card's chosen rows are the trip's picks, marked in both legs. A
// pick lost by a change is no longer marked, since every card says the picks anew. An outbound
// card that keeps no return pick is a new search: it clears the return segment; a leg's card
// clears the review and the extra; a review card that no longer holds the return's pick (the
// trip made one way) clears the return segment, so a one-way trip shows none. The review segment
// shows a status line (`status`): waiting for the caller's yes, or booked with its reference.
//
// A card is data, never instructions: its title and its texts are set with textContent, each in
// the direction of its own first strong character (dir="auto"). A row's mark is one of `MARKS`
// or none: set as the row's `data-mark`, which the page's style maps to a look, and shown as a
// word of the page's own (`texts.js`), never as markup; any other is dropped.

export const SLOTS = ["outbound", "return", "review"];
export const MARKS = ["best", "chosen", "unavailable"];
const PARTS = ["title", "detail", "value"];
const SHOWN = [...SLOTS, "extra"];

function text(value) {
  return typeof value === "string" ? value : "";
}

// A card's rows, each its texts and its mark (null when it has none, or one not in MARKS); a row
// with no title is left out.
export function rowsOf(card) {
  if (!Array.isArray(card?.rows)) return [];
  return card.rows
    .filter((row) => row && typeof row === "object" && text(row.title))
    .map((row) => ({
      ...Object.fromEntries(PARTS.map((part) => [part, text(row[part])])),
      mark: MARKS.includes(row.mark) ? row.mark : null,
    }));
}

// A card's steps, the texts among them.
export function stepsOf(card) {
  return Array.isArray(card?.steps) ? card.steps.map(text).filter(Boolean) : [];
}

function part(tag, className, said) {
  const node = document.createElement(tag);
  node.className = className;
  node.dir = "auto";
  node.textContent = said;
  return node;
}

const picked = (rows) => rows.filter((row) => row.mark === "chosen");

export class Cards {
  // The segments shown in `list` (an ol), their section `section` hidden while there are none;
  // `marks()` gives the words a row's mark is shown with, in the page's language.
  constructor(list, section, marks = () => ({})) {
    this.list = list;
    this.section = section;
    this.marks = marks;
    this.clear();
  }

  // A new card, in place of its segment's (the module's comment).
  add(card) {
    if (!card || typeof card !== "object") return;
    const kept = { title: text(card.title), rows: rowsOf(card), steps: stepsOf(card) };
    const slot = SLOTS.includes(card.slot) ? card.slot : "extra";
    if (slot === "review") this.review(kept);
    else if (slot === "extra") this.shown.extra = kept;
    else this.leg(slot, kept);
    this.render();
  }

  leg(slot, card) {
    const other = slot === "outbound" ? "return" : "outbound";
    const kept = picked(card.rows);
    this.shown[slot] = { ...card, rows: card.rows.filter((row) => row.mark !== "chosen") };
    if (this.shown[other]) {
      const by = new Map(kept.map((row) => [row.title, { ...row, mark: null }]));
      const rows = this.shown[other].rows.map((row) => by.get(row.title) ?? row);
      this.shown[other] = { ...this.shown[other], rows };
    }
    if (slot === "outbound" && !kept.length) this.shown.return = null;
    this.shown.review = null;
    this.shown.extra = null;
    this.picks = new Set(kept.map((row) => row.title));
    this.status = "";
  }

  review(card) {
    const picks = new Set(picked(card.rows).map((row) => row.title));
    const back = this.shown.return?.rows ?? [];
    const dropped = back.some((r) => this.picks.has(r.title)) && !back.some((r) => picks.has(r.title));
    if (dropped) this.shown.return = null;
    this.shown.review = card;
    this.picks = picks;
  }

  // The review segment's status line: "" for none, else a text of the page's own.
  setStatus(said) {
    this.status = text(said);
    this.render();
  }

  clear() {
    this.shown = Object.fromEntries(SHOWN.map((slot) => [slot, null]));
    this.picks = new Set();
    this.status = "";
    if (this.list) this.render();
  }

  row(row, slot) {
    const line = document.createElement("li");
    line.className = "row";
    const pick = slot !== "review" && row.mark !== "unavailable" && this.picks.has(row.title);
    const mark = pick ? "chosen" : row.mark;
    if (mark) line.dataset.mark = mark;
    line.append(
      ...PARTS.filter((name) => row[name]).map((name) => part("span", `row-${name}`, row[name])),
    );
    const word = mark ? text(this.marks()?.[mark]) : "";
    if (word) line.append(part("span", "row-mark", word));
    return line;
  }

  step(said) {
    const line = document.createElement("li");
    line.dir = "auto";
    line.textContent = said;
    return line;
  }

  segment(slot, card) {
    const item = document.createElement("li");
    item.className = "card";
    item.dataset.slot = slot;
    const title = document.createElement("h3");
    title.dir = "auto";
    title.textContent = card.title;
    const lines = document.createElement("ul");
    if (card.rows.length) {
      lines.className = "rows";
      lines.replaceChildren(...card.rows.map((row) => this.row(row, slot)));
    } else {
      lines.replaceChildren(...card.steps.map((said) => this.step(said)));
    }
    item.append(title, lines);
    if (slot === "review" && this.status) item.append(part("p", "card-status", this.status));
    return item;
  }

  render() {
    const items = SHOWN.filter((slot) => this.shown[slot]).map((slot) =>
      this.segment(slot, this.shown[slot]),
    );
    this.list.replaceChildren(...items);
    this.section.hidden = items.length === 0;
  }
}
