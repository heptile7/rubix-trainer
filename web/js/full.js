// Full Solve: WCA-style scramble, timer, result bar (FullSolveScreen), and on
// the right the current session: its stats and history (solves.js).
// Scrambles are made in the browser, so New Scramble / Next never wait on the server.

import { api } from "./api.js";
import { Timer } from "./timer.js";
import { h, fmt, eff, generateScramble, resultBar } from "./util.js";
import { sessionPanel, lastSolveBar } from "./solves.js";

const READY = "Press SPACE or Start to begin";

export function fullScreen(store) {
  const scrambleBox = h("div.scramble-box");
  const timerLabel = h("div.timer", { text: "0.00" });
  const statusLine = h("div.status-line", { text: READY });
  const startBtn = h("button.btn.big.primary", { type: "button", text: "Start  [space]" });
  const result = h("div.result-bar");
  const session = sessionPanel(store, "full", { title: "Full Solve" });
  const last = lastSolveBar(store, "full");
  let scramble = "";

  function refreshTimes() {
    result.textContent = resultBar(store.recent.full.map(eff));
    session.refresh();
    last.refresh();
  }

  function newScramble() {
    timer.reset();
    scramble = generateScramble();
    scrambleBox.textContent = scramble;
    statusLine.textContent = READY;
  }

  const timer = new Timer(timerLabel, startBtn, {
    onNext: newScramble,
    onStop(seconds) {
      // show it at once; the server's answer replaces the local guess
      store.recent.full.unshift({ id: null, case: null, seconds, penalty: null, flagged: false, note: null, ts: "" });
      refreshTimes();
      statusLine.textContent = `Saved  ${fmt(seconds)}  —  press SPACE for next scramble`;
      api.addTime({ mode: "full", seconds, scramble }).then((r) => store.applyTimes("full", null, r));
    },
  });
  startBtn.onclick = () => timer.toggle();
  store.onTimes((m) => m === "full" && refreshTimes());

  const main = h("div.timer-main", null,
    h("h1", { text: "Full Solve", style: "margin:6px 0 4px" }),
    scrambleBox,
    timerLabel,
    statusLine,
    h("div.row", null,
      startBtn,
      h("button.btn.big", { type: "button", text: "New Scramble", onclick: newScramble }),
      h("button.btn.big.danger", {
        type: "button", text: "Delete Last",
        onclick: async () => {
          const r = await api.deleteLast("full");
          if (r && r.deleted) {
            store.applyTimes("full", null, r);
            statusLine.textContent = "Last time deleted.";
          }
        },
      })),
    last.el,
    result);

  const el = h("section.screen", null,
    h("div.trainer", null, main, h("div.side", null, session.el)));

  newScramble();
  refreshTimes();
  return {
    el,
    timer,
    onShow: refreshTimes,
    onHide: () => timer.reset(),
  };
}
