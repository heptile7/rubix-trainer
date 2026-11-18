// The options row under a timer: inspection and hold to start (settings shared
// with the GUI, saved on the server). Hold to start is one setting for every
// screen, so each row repaints when any setting changes.

import { h } from "./util.js";

const HOLD = [[300, "0.3 s"], [550, "0.55 s"], [1000, "1 s"]];
const PRACTICE_SECONDS = [5, 8, 12, 15];

export function timerOptions(store, mode) {
  const check = (title, onchange) => h("input", { type: "checkbox", title, onchange });
  const choose = (pairs, onchange) => {
    const sel = h("select.small-select", { onchange });
    sel.append(...pairs.map(([v, text]) => h("option", { value: v, text })));
    return sel;
  };

  const insp = check("Count down before the solve", () => store.setSetting(`inspection.${mode}`, insp.checked));
  const parts = [h("label.switch", null, insp, mode === "full" ? "Inspection (WCA 15 s)" : "Inspection")];
  let seconds = null, voice = null;
  if (mode === "full") {
    voice = check("Say “eight seconds” and “twelve seconds”", () => store.setSetting("inspection_voice", voice.checked));
    parts.push(h("label.switch", null, voice, "Call 8 / 12 s"));
  } else {
    seconds = choose(PRACTICE_SECONDS.map((n) => [n, `${n} s`]),
      () => { store.setSetting(`inspection_seconds.${mode}`, Number(seconds.value)); seconds.blur(); });
    parts.push(seconds);
  }
  const hold = check("Hold Space until the timer turns green, then release to start",
    () => store.setSetting("hold_to_start", hold.checked));
  const holdMs = choose(HOLD, () => { store.setSetting("hold_ms", Number(holdMs.value)); holdMs.blur(); });
  parts.push(h("span.gap"), h("label.switch", null, hold, "Hold to start"), holdMs);

  function refresh() {
    const s = store.settings;
    insp.checked = s[`inspection.${mode}`];
    if (seconds) { seconds.value = String(s[`inspection_seconds.${mode}`]); seconds.disabled = !insp.checked; }
    if (voice) voice.checked = s.inspection_voice;
    hold.checked = s.hold_to_start;
    holdMs.value = String(s.hold_ms);
    holdMs.disabled = !hold.checked;
  }
  store.onSettings(refresh);
  refresh();
  return { el: h("div.timer-options", null, ...parts), refresh };
}
