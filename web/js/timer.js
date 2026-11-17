// idle -> running -> stopped -> (next) idle: the state machine of
// TimerScreenBase. Times come from performance.now() (event.timeStamp when a
// key started or stopped it, which is when the key was actually pressed);
// the display is redrawn once per frame, only when the hundredths change.

import { fmt } from "./util.js";

export class Timer {
  /**
   * label: element showing the time; button: Start/Stop/Next button.
   * onStop(seconds) records the attempt; onNext() deals the next scramble.
   */
  constructor(label, button, { onStop, onNext }) {
    this.label = label;
    this.button = button;
    this.onStop = onStop;
    this.onNext = onNext;
    this.state = "idle";
    this._start = 0;
    this._frame = 0;
    this._shown = "";
    this._tick = this._tick.bind(this);
  }

  toggle(at = performance.now()) {
    if (this.state === "idle") this._run(at);
    else if (this.state === "running") this._stop(at);
    else this.onNext();
  }

  _run(at) {
    this._start = at;
    this.state = "running";
    this.button.textContent = "Stop  [space]";
    this.label.className = "timer running";
    this._frame = requestAnimationFrame(this._tick);
  }

  _stop(at) {
    cancelAnimationFrame(this._frame);
    const seconds = Math.max(0, (at - this._start) / 1000);
    this.state = "stopped";
    this.button.textContent = "Next  [space]";
    this.label.className = "timer stopped";
    this._show(fmt(seconds));
    this.onStop(seconds);
  }

  _tick() {
    if (this.state !== "running") return;
    this._show(fmt((performance.now() - this._start) / 1000));
    this._frame = requestAnimationFrame(this._tick);
  }

  _show(text) {
    if (text !== this._shown) this.label.textContent = this._shown = text;
  }

  /** Back to idle (switching screens, a new case) without recording anything. */
  reset() {
    cancelAnimationFrame(this._frame);
    this.state = "idle";
    this.button.textContent = "Start  [space]";
    this.label.className = "timer";
    this._show("0.00");
  }
}
