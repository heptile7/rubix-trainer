// The timer state machine of TimerScreenBase, with inspection and hold to start:
//
//   idle -> [inspecting] -> [holding -> ready] -> running -> (saved, next dealt) idle
//
// Keys:  press(at) / release(at) for Space down / up (at = event.timeStamp, the
// moment the key moved).  Button:  toggle(at) - instant, never holds.
//   idle        press arms; release starts inspection (if on). Without
//               inspection: press holds (hold on) or starts at once (hold off).
//   inspecting  press holds (or starts at once with hold off).
//   holding     the timer turns red; after holdMs it turns green (ready).
//               Release when ready starts the clock; earlier goes back.
//   running     press stops (at keydown, so the time is exact): the attempt is
//               saved (onStop), the next scramble dealt and the clock reset to
//               0.00 at once (onNext); the time is in the previous-solve card.
//               That key's release is swallowed.
// WCA inspection (Full Solve): starting after 15 s is +2, after 17 s a DNF,
// which ends the attempt at once. Practice inspection has no penalties.
// The display is redrawn once per frame, only when its text changes.

import { fmt } from "./util.js";

const WCA = 15;

export class Timer {
  /**
   * label: element showing the time; button: Start/Stop/Next button.
   * onStop(seconds, penalty) records the attempt; onNext() deals the next one.
   * options() -> {inspection: seconds (0 = off), wca: bool, holdMs: 0 = off, voice: bool},
   * read at the start of each attempt so setting changes apply at once.
   */
  constructor(label, button, { onStop, onNext, options = () => ({}) }) {
    this.label = label;
    this.button = button;
    this.onStop = onStop;
    this.onNext = onNext;
    this.options = options;
    this.state = "idle";
    this._start = 0;          // running: when the clock started
    this._inspStart = 0;      // inspecting: when inspection started
    this._holdStart = 0;      // holding: when Space went down
    this._holdFrom = "idle";  // holding: the state to go back to on an early release
    this._armed = false;      // idle + inspection: Space is down, release starts inspection
    this._swallow = false;    // ignore the next release (it belongs to a stop / next)
    this._penalty = null;
    this._warned = 0;
    this._opts = {};
    this._frame = 0;
    this._shown = "";
    this._tick = this._tick.bind(this);
  }

  // ---- inputs ---------------------------------------------------------------
  press(at = performance.now()) {
    this._swallow = false;    // a new press: any release we were waiting for is past
    if (this.state === "running") { this._stop(at); this._swallow = true; return; }
    if (this.state === "holding") return;
    if (this.state === "idle") this._opts = this.options();
    const { inspection = 0, holdMs = 0 } = this._opts;
    if (this.state === "idle" && inspection) { this._armed = true; return; }
    if (holdMs) this._hold(at);
    else this._run(at);
  }

  release(at = performance.now()) {
    if (this._swallow) { this._swallow = false; return; }
    if (this._armed) { this._armed = false; if (this.state === "idle") this._inspect(at); return; }
    if (this.state !== "holding") return;
    if (at - this._holdStart >= this._opts.holdMs) this._run(at);
    else this._back();
  }

  /** The Start button: no holding. */
  toggle(at = performance.now()) {
    this._swallow = this._armed = false;
    if (this.state === "idle") {
      this._opts = this.options();
      if (this._opts.inspection) this._inspect(at);
      else this._run(at);
    } else if (this.state === "inspecting" || this.state === "holding") this._run(at);
    else if (this.state === "running") this._stop(at);
  }

  // ---- states -----------------------------------------------------------------
  _set(state, cls, buttonText) {
    this.state = state;
    this.label.className = `timer ${cls}`.trim();
    if (buttonText) this.button.textContent = buttonText;
  }

  _inspect(at) {
    this._inspStart = at;
    this._warned = 0;
    this._set("inspecting", "inspecting", "Start  [space]");
    this._loop();
  }

  _hold(at) {
    this._holdFrom = this.state;
    this._holdStart = at;
    this._set("holding", "holding");
    this._loop();
  }

  _back() {
    if (this._holdFrom === "inspecting") this._set("inspecting", "inspecting");
    else { this._set("idle", ""); this._show("0.00"); }
  }

  _run(at) {
    this._penalty = null;
    if (this._opts.inspection && this._opts.wca && (this.state === "inspecting" || this._holdFrom === "inspecting")) {
      const used = (at - this._inspStart) / 1000;
      if (used > WCA + 2) { this._dnf(); return; }
      if (used > WCA) this._penalty = "+2";
    }
    this._start = at;
    this._holdFrom = "idle";
    this._set("running", "running", "Stop  [space]");
    this._loop();
  }

  _stop(at) {
    cancelAnimationFrame(this._frame);
    const seconds = Math.max(0, (at - this._start) / 1000);
    this.state = "idle";
    this.onStop(seconds, this._penalty);
    this._advance();
  }

  /** After a save: deal the next scramble now; the clock goes back to 0.00. */
  _advance() {
    this.onNext();                    // timer.reset(): 0.00, idle; then the next scramble
  }

  /** Inspection ran past 17 s: the attempt is a DNF. */
  _dnf() {
    cancelAnimationFrame(this._frame);
    this.state = "idle";
    this.onStop(0, "dnf");
    this._advance();
  }

  // ---- display ------------------------------------------------------------------
  _loop() {
    cancelAnimationFrame(this._frame);
    this._frame = requestAnimationFrame(this._tick);
  }

  _tick() {
    const now = performance.now();
    if (this.state === "running") {
      this._show(fmt((now - this._start) / 1000));
    } else if (this.state === "holding") {
      const ready = now - this._holdStart >= this._opts.holdMs;
      this.label.className = `timer ${ready ? "ready" : "holding"}`;
      if (this._holdFrom === "idle") this._show("0.00");
      else this._inspectionText(now);
    } else if (this.state === "inspecting") {
      if (this._inspectionText(now)) return;
    } else return;
    this._frame = requestAnimationFrame(this._tick);
  }

  /** Countdown text; true when inspection ended the attempt (DNF). */
  _inspectionText(now) {
    const used = (now - this._inspStart) / 1000;
    const { inspection, wca, voice } = this._opts;
    if (wca) {
      if (voice && used >= 8 && this._warned < 8) { this._warned = 8; say("Eight seconds"); }
      if (voice && used >= 12 && this._warned < 12) { this._warned = 12; say("Twelve seconds"); }
      if (used > WCA + 2) {
        if (this.state === "inspecting") { this._dnf(); return true; }
        this._show("DNF");
        return false;
      }
      if (used > WCA) { this._show("+2"); return false; }
    }
    this._show(String(Math.max(0, Math.ceil(inspection - used))));
    return false;
  }

  _show(text) {
    if (text !== this._shown) this.label.textContent = this._shown = text;
  }

  /** Back to idle (switching screens, a new case) without recording anything. */
  reset() {
    cancelAnimationFrame(this._frame);
    this._armed = this._swallow = false;
    this._holdFrom = "idle";
    this._set("idle", "", "Start  [space]");
    this._show("0.00");
  }
}

function say(text) {
  try {
    if (window.speechSynthesis) speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  } catch { /* no voice */ }
}
