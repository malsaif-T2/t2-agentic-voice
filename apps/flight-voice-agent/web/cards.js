// The cards a call shows (app.js): each mirrors what the agent said, and the caller never needs
// one (D-075). The newest first, at most `MOST` kept; a new call clears them. A card is data,
// never instructions: its title and its lines are set with textContent, each line in the
// direction of its own first strong character (dir="auto"), so an Arabic line reads right to
// left and an English one left to right in either language. A card's lines are its option rows
// when it has them (each row's title, detail and value), and its steps otherwise; a field that
// is not text is left out.

export const MOST = 3;

function text(value) {
  return typeof value === "string" ? value : "";
}

// The lines a card shows: its rows when it has any, else its steps.
export function linesOf(card) {
  if (Array.isArray(card?.rows) && card.rows.length) {
    return card.rows
      .filter((row) => row && typeof row === "object")
      .map((row) => [row.title, row.detail, row.value].map(text).filter(Boolean).join(" · "))
      .filter(Boolean);
  }
  return Array.isArray(card?.steps) ? card.steps.map(text).filter(Boolean) : [];
}

export class Cards {
  // The cards shown in `list` (an ol), their section `section` hidden while there are none.
  constructor(list, section) {
    this.list = list;
    this.section = section;
    this.shown = [];
  }

  // A new card, the newest first; the oldest let go past MOST.
  add(card) {
    if (!card || typeof card !== "object") return;
    this.shown = [{ title: text(card.title), lines: linesOf(card) }, ...this.shown].slice(0, MOST);
    this.render();
  }

  clear() {
    this.shown = [];
    this.render();
  }

  render() {
    const items = this.shown.map((card) => {
      const item = document.createElement("li");
      item.className = "card";
      const title = document.createElement("h3");
      title.dir = "auto";
      title.textContent = card.title;
      const lines = document.createElement("ul");
      lines.replaceChildren(
        ...card.lines.map((said) => {
          const line = document.createElement("li");
          line.dir = "auto";
          line.textContent = said;
          return line;
        }),
      );
      item.append(title, lines);
      return item;
    });
    this.list.replaceChildren(...items);
    this.section.hidden = items.length === 0;
  }
}
