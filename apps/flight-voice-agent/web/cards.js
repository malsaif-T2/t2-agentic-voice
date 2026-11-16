// The cards a call shows (app.js): each mirrors what the agent said, and the caller never needs
// one (D-075). The newest first, at most `MOST` kept; a new call clears them. A card is data,
// never instructions: its title and its texts are set with textContent, each in the direction of
// its own first strong character (dir="auto"), so an Arabic text reads right to left and an
// English one left to right in either language. A card shows its option rows when it has them
// (the flights listed, the days, the cabins, the trip: each row's title, detail and value in
// their own parts), and its steps otherwise; a field that is not text is left out. A row's mark
// is one of `MARKS` or none: it is set as the row's `data-mark`, which the page's style maps to a
// look, and shown as a word of the page's own (`texts.js`), never as markup; any other is dropped.

export const MOST = 3;
export const MARKS = ["best", "chosen", "unavailable"];
const PARTS = ["title", "detail", "value"];

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

export class Cards {
  // The cards shown in `list` (an ol), their section `section` hidden while there are none;
  // `marks()` gives the words a row's mark is shown with, in the page's language.
  constructor(list, section, marks = () => ({})) {
    this.list = list;
    this.section = section;
    this.marks = marks;
    this.shown = [];
  }

  // A new card, the newest first; the oldest let go past MOST.
  add(card) {
    if (!card || typeof card !== "object") return;
    const kept = { title: text(card.title), rows: rowsOf(card), steps: stepsOf(card) };
    this.shown = [kept, ...this.shown].slice(0, MOST);
    this.render();
  }

  clear() {
    this.shown = [];
    this.render();
  }

  row(row) {
    const line = document.createElement("li");
    line.className = "row";
    if (row.mark) line.dataset.mark = row.mark;
    line.append(
      ...PARTS.filter((name) => row[name]).map((name) => part("span", `row-${name}`, row[name])),
    );
    const word = row.mark ? text(this.marks()?.[row.mark]) : "";
    if (word) line.append(part("span", "row-mark", word));
    return line;
  }

  step(said) {
    const line = document.createElement("li");
    line.dir = "auto";
    line.textContent = said;
    return line;
  }

  render() {
    const items = this.shown.map((card) => {
      const item = document.createElement("li");
      item.className = "card";
      const title = document.createElement("h3");
      title.dir = "auto";
      title.textContent = card.title;
      const lines = document.createElement("ul");
      if (card.rows.length) {
        lines.className = "rows";
        lines.replaceChildren(...card.rows.map((row) => this.row(row)));
      } else {
        lines.replaceChildren(...card.steps.map((said) => this.step(said)));
      }
      item.append(title, lines);
      return item;
    });
    this.list.replaceChildren(...items);
    this.section.hidden = items.length === 0;
  }
}
