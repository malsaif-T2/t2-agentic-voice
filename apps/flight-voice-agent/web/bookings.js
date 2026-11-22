// "Your trips" (app.js): the traveler's bookings from the app's own route (`GET api/bookings`,
// answered on this machine alone), newest first as the route gives them: each one's route, its
// kind and dates, travelers and cabin, total and reference, shown as text. The filter by
// reference runs on the page, with no request. The list loads when the panel opens, again
// every `EVERY_MS` while it is open, when a call starts and ends, and after a read-back while
// the booking it may have made is not found (`Made`); "Start over" asks first, then
// `POST api/demo/reset` puts the bookings back to the seed. All of it is the page's only on a
// line that books (the profile's `bookings`, `Booking.shown`): on one that books nothing none of
// it is shown, and no route of it is ever asked.

import { linksOf, waitsForYes } from "./cards.js?v=2026-11-22";
import { fill } from "./texts.js?v=2026-11-22";

export const EVERY_MS = 10_000;

function amount(value) {
  return Number.isFinite(value) ? value.toLocaleString("en-US") : "";
}

function name(names, language) {
  if (!names || typeof names !== "object") return "";
  const said = language === "en" ? names.en : names.ar;
  return typeof said === "string" ? said : "";
}

function party(travelers, words) {
  const n = Number(travelers) || 1;
  return n === 1 ? words.oneTraveler : fill(words.travelers, { n });
}

// The lines of one booking, each a text, in the page's `language` with its `words`.
export function bookingLines(booking, language, words) {
  const dates = booking.return_date ? `${booking.depart} – ${booking.return_date}` : booking.depart;
  const kind = booking.return_date ? words.roundTrip : words.oneWay;
  const route = fill(words.route, {
    from: name(booking.from, language),
    to: name(booking.to, language),
  });
  return [
    route,
    `${kind} · ${String(dates ?? "")}`,
    `${party(booking.travelers, words)} · ${words.cabins[booking.cabin] ?? ""}`,
    `${fill(words.total, { amount: amount(booking.total_sar) })} · ${fill(words.reference, { ref: String(booking.reference ?? "") })}`,
    booking.flown ? words.flown : words.booked,
  ];
}

export class Trips {
  // The list `list` (a ul), the filter `filter` (an input) and the line `note` that says when
  // none matches or the list could not load.
  constructor(list, filter, note) {
    this.list = list;
    this.filter = filter;
    this.note = note;
    this.bookings = [];
    this.failed = false;
    this.timer = null;
  }

  async load() {
    try {
      const response = await fetch("api/bookings", { cache: "no-store" });
      const body = await response.json();
      if (!response.ok || !Array.isArray(body?.bookings)) throw new Error("not loaded");
      this.bookings = body.bookings.filter((each) => each && typeof each === "object");
      this.failed = false;
    } catch {
      this.failed = true;
    }
  }

  // Load while the panel is open: now, and every EVERY_MS; stopped when it closes.
  watch(open, show) {
    clearInterval(this.timer);
    this.timer = null;
    if (!open) return;
    const again = async () => {
      await this.load();
      show();
    };
    this.timer = setInterval(again, EVERY_MS);
    return again();
  }

  // The bookings shown, each as its lines, those whose reference holds the filter's digits.
  render(language, words) {
    const wanted = String(this.filter.value ?? "").replace(/\D/g, "");
    const kept = this.bookings.filter((b) => !wanted || String(b.reference ?? "").includes(wanted));
    this.list.replaceChildren(
      ...kept.map((booking) => {
        const item = document.createElement("li");
        item.className = booking.flown ? "trip flown" : "trip";
        item.append(
          ...bookingLines(booking, language, words).map((said) => {
            const line = document.createElement("span");
            line.dir = "auto";
            line.textContent = said;
            return line;
          }),
        );
        return item;
      }),
    );
    const none = this.failed ? words.tripsFailed : kept.length ? "" : words.noTrips;
    this.note.textContent = none;
  }
}

// The references of the bookings loaded, as text.
export function referencesOf(trips) {
  return new Set(trips.bookings.map((b) => String(b.reference ?? "")).filter(Boolean));
}

// The booking a call made (app.js), found from the page's own "Your trips" route: the
// references loaded at the call's start (`start`); once the whole trip was shown for review
// (`ask`) or a read-back was asked (the state `confirming`), the list loaded again at each state
// after it until a booking not among them is there, its reference then kept (`seen`). A new leg
// listed after it (`forget`) makes every booking loaded a known one, so the next trip of the
// call looks for its own. When the list did not load at the start, no booking is ever taken for
// this call's, so a past one is never shown as made.
export class Made {
  constructor(trips) {
    this.trips = trips;
    this.known = null;
    this.asked = false;
    this.reference = "";
  }

  async start() {
    await this.trips.load();
    const known = this.trips.failed ? null : referencesOf(this.trips);
    Object.assign(this, { known, asked: false, reference: "" });
  }

  // The whole trip is shown for review: its booking is looked for from now on.
  ask() {
    this.asked = true;
  }

  // A new leg is listed: the bookings loaded are known ones, and none is looked for yet.
  forget() {
    if (this.known) for (const ref of referencesOf(this.trips)) this.known.add(ref);
    Object.assign(this, { asked: false, reference: "" });
  }

  // The reference of the booking this call made, "" while there is none, the state `now`.
  async seen(now) {
    if (now === "confirming") this.asked = true;
    if (this.known && !this.reference && this.asked && now !== "confirming") {
      await this.trips.load();
      this.reference = [...referencesOf(this.trips)].find((ref) => !this.known.has(ref)) ?? "";
    }
    return this.reference;
  }
}

// The page's part of the bookings (app.js): "Your trips" and its panel, "Start over" and its
// question, the traveler's line, and the review's status, waiting for the yes, then booked with
// its reference once found (`Made`). Each does nothing while the line books nothing (`shown`).
export class Booking {
  // The page's element by id `$`, its `cards`, its words and language now (`words()`,
  // `language()`).
  constructor($, cards, words, language) {
    Object.assign(this, { $, cards, words, language, on: false });
    this.trips = new Trips($("trips-list"), $("trips-filter"), $("trips-note"));
    this.made = new Made(this.trips);
    $("trips-toggle").addEventListener("click", () => this.open(this.on && $("trips").hidden));
    for (const name of ["input", "change"]) $("trips-filter").addEventListener(name, () => this.show());
    $("start-over").addEventListener("click", () => {
      $("reset-ask").hidden = !this.on;
    });
    $("reset-no").addEventListener("click", () => {
      $("reset-ask").hidden = true;
    });
    $("reset-yes").addEventListener("click", async () => {
      $("reset-ask").hidden = true;
      if (this.on && (await startOver())) {
        cards.clear();
        await this.trips.load();
        this.show();
      }
    });
  }

  // Whether the line books: what belongs to a traveler shown, or hidden and the panel closed.
  set shown(on) {
    this.on = on;
    for (const id of ["trips-toggle", "start-over", "traveler"]) this.$(id).hidden = !on;
    if (!on && !this.$("trips").hidden) this.open(false);
    if (!on) this.$("reset-ask").hidden = true;
    this.show();
  }

  show() {
    if (this.on) this.trips.render(this.language(), this.words());
  }

  open(open) {
    this.$("trips").hidden = !open;
    this.$("trips-toggle").setAttribute("aria-expanded", String(open));
    return this.trips.watch(open && this.on, () => this.show());
  }

  // A call starts: the bookings it may make are looked for from those listed now.
  async started() {
    if (this.on) await this.made.start();
  }

  // The review's status at the call's state `now` ("" once ended).
  async reviewed(now) {
    if (!this.on) return;
    const ref = await this.made.seen(now);
    const waiting = this.made.asked && now ? this.words().waiting : "";
    this.cards.setStatus(ref ? fill(this.words().bookedRef, { ref }) : waiting);
  }

  // A card shown (cards.js): a new leg forgets the last booking; the trip's review waits for the
  // yes, unless it carries booking links (D-126): those are booked on the airline's site.
  carded(card) {
    if (!this.on) return;
    if (card?.slot === "outbound" || card?.slot === "return" || linksOf(card).length) {
      this.made.forget();
    }
    if (waitsForYes(card) && !this.made.reference) {
      this.made.ask();
      this.cards.setStatus(this.words().waiting);
    }
  }

  // The call has ended: the list loaded again, and the booking it made shown.
  ended() {
    if (this.on) this.trips.load().then(() => this.reviewed("")).then(() => this.show());
  }
}

// The bookings put back to the seed, once the page has asked (app.js): true when they were.
export async function startOver() {
  try {
    const response = await fetch("api/demo/reset", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "{}",
      cache: "no-store",
    });
    return response.ok;
  } catch {
    return false;
  }
}
