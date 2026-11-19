// The caller's microphone on the flight page (for app.js): push to talk (the box under Options,
// the hold button and the Space key) and the round mute button beside the end-call button, both
// through the library client's own switch, its track on only while push to talk is off or held
// (t2v-client.js). Muted, the page sets `call.pushToTalk = true` and never holds it, so the call
// hears silence and goes on; unmuted, push to talk is the box's again, released. Space stays push
// to talk's: the mute button takes Enter or Space only as any button does, by its click. The orb
// shows no caller level while the caller is not heard (`hush`); the buttons work only while a
// call runs, and a new call starts unmuted. Its names come from texts.js, set as attributes.

export class Microphone {
  muted = false;

  // `$` finds an element by id; `orb` is the page's Orb; `words` gives the page's texts; `call`
  // gives the running client (null for none); `changed` redraws the state line on a mute.
  constructor($, orb, words, call, changed) {
    Object.assign(this, { $, orb, words, call, changed });
    $("mute").addEventListener("click", () => {
      if (!$("mute").disabled) this.mute(!this.muted);
    });
    $("push-to-talk").addEventListener("change", () => this.apply());
    $("talk").addEventListener("pointerdown", (event) => {
      if ($("talk").disabled) return;
      $("talk").setPointerCapture?.(event.pointerId);
      this.talk(true);
    });
    for (const name of ["pointerup", "pointercancel", "lostpointercapture"]) {
      $("talk").addEventListener(name, () => this.talk(false));
    }
    document.addEventListener("keydown", (event) => this.space(event));
    document.addEventListener("keyup", (event) => this.space(event));
    globalThis.addEventListener("blur", () => this.talk(false));
  }

  get pushToTalk() {
    return this.$("push-to-talk").checked;
  }

  // Push to talk held (`held`) or released; never held while muted.
  talk(held) {
    const on = held === true && !this.muted;
    this.$("talk").setAttribute("aria-pressed", String(on));
    this.orb.hush = (this.muted || this.pushToTalk) && !on;
    this.call()?.talk(on);
  }

  // The buttons that work only during a call: the mute button shown with the end-call button,
  // both working once the call has joined, the hold button only with push to talk, unmuted.
  able() {
    const off = this.$("end").disabled || !this.call();
    this.$("mute").hidden = this.$("end").hidden;
    this.$("mute").disabled = off;
    this.$("talk").disabled = off || !this.pushToTalk || this.muted;
  }

  // The client's switch as the box and the mute button say, push to talk released.
  apply() {
    const call = this.call();
    if (call) call.pushToTalk = this.muted || this.pushToTalk;
    this.talk(false);
    this.able();
  }

  mute(on) {
    this.muted = on === true;
    this.render();
    this.apply();
    this.changed();
  }

  // Unmuted, as a call starts or ends.
  reset() {
    this.muted = false;
    this.render();
  }

  render() {
    const said = this.muted ? this.words().unmute : this.words().mute;
    this.$("mute").setAttribute("aria-pressed", String(this.muted));
    this.$("mute").setAttribute("aria-label", said);
    this.$("mute").setAttribute("title", said);
  }

  space(event) {
    if (event.code !== "Space" || !this.call() || !this.pushToTalk) return;
    event.preventDefault();
    if (event.type === "keyup") this.talk(false);
    else if (!event.repeat) this.talk(true);
  }
}
