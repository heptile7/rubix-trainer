// Full Solve: WCA-style scramble, timer, result bar (FullSolveScreen).
// Scrambles are made in the browser, so New Scramble / Next never wait on the server.

import { api } from "./api.js";
import { Timer } from "./timer.js";
import { h, fmt, generateScramble, resultBar } from "./util.js";

const READY = "Press SPACE or Start to begin";

export function fullScreen(store) {
  const scrambleBox = h("div.scramble-box");
  const timerLabel = h("div.timer", { text: "0.00" });
  const statusLine = h("div.status-line", { text: READY });
  const startBtn = h("button.btn.big.primary", { type: "button", text: "Start  [space]" });
  const result = h("div.result-bar");
  let scramble = "";

  const refreshResult = () => { result.textContent = resultBar(store.recent.full.map((r) => r[1])); };

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
      store.recent.full.unshift([null, seconds, ""]);
      refreshResult();
      statusLine.textContent = `Saved  ${fmt(seconds)}  —  press SPACE for next scramble`;
      api.addTime({ mode: "full", seconds, scramble }).then((r) => {
        store.applyTimes("full", null, r);
        refreshResult();
      });
    },
  });
  startBtn.onclick = () => timer.toggle();

  const el = h("section.screen", null,
    h("div.timer-main", null,
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
              refreshResult();
            }
          },
        })),
      result));

  newScramble();
  refreshResult();
  return {
    el,
    timer,
    onHide: () => timer.reset(),
  };
}
