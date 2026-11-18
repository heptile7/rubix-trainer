// Sessions and single solves, shared by Full Solve, the OLL / PLL trainers and
// Statistics (the web side of SessionPanel in cube_timer_gui.py):
//   statsBlock      - session vs all-time summary (count, best, mean, ao5 ...)
//   solveAction     - +2 / DNF / OK, flag (with a note), note, delete
//   sessionPanel    - "Session N" + New session, the stats and the history list
//   lastSolveBar    - OK / +2 / DNF / Flag for the newest attempt, under the timer
// Every change goes through the store, which repaints listeners via onTimes.

import { h, fmt, fmtSolve } from "./util.js";

export const STAT_ROWS = [
  ["count", "Solves"], ["best", "Best"], ["worst", "Worst"], ["mean", "Mean"],
  ["ao5", "ao5"], ["ao12", "ao12"], ["ao50", "ao50"], ["ao100", "ao100"],
  ["best_ao5", "Best ao5"], ["best_ao12", "Best ao12"],
];

const statValue = (st, key) =>
  key === "count" ? (st.dnf ? `${st.count}  (${st.dnf} DNF)` : String(st.count)) : fmt(st[key]);

/** Two-column table: this session and all time. update(stats) takes store.stats[mode]. */
export function statsBlock({ compact = false } = {}) {
  const rows = compact ? STAT_ROWS.filter(([k]) => !["worst", "ao50"].includes(k)) : STAT_ROWS;
  const sessionHead = h("th", { text: "Session" });
  const cells = rows.map(() => [h("td.num"), h("td.num")]);
  const el = h("table.stat-block", null,
    h("thead", null, h("tr", null, h("th"), sessionHead, h("th", { text: "All time" }))),
    h("tbody", null, ...rows.map(([, label], i) => h("tr", null, h("th", { text: label }), ...cells[i]))));
  function update(stats) {
    sessionHead.textContent = `Session ${stats.session_no}`;
    rows.forEach(([key], i) => {
      cells[i][0].textContent = statValue(stats.session, key);
      cells[i][1].textContent = statValue(stats.all, key);
    });
  }
  return { el, update };
}

/** Apply one action to a saved solve. Resolves when the store has the server's answer. */
export async function solveAction(store, mode, solve, action) {
  if (!solve || solve.id == null) return;
  switch (action) {
    case "ok":  return store.setPenalty(mode, solve.id, null);
    case "+2":  return store.setPenalty(mode, solve.id, solve.penalty === "+2" ? null : "+2");
    case "dnf": return store.setPenalty(mode, solve.id, solve.penalty === "dnf" ? null : "dnf");
    case "flag": {
      if (solve.flagged) return store.setFlag(mode, solve.id, false);
      const note = prompt("Flag this solve. Note (optional):", "");
      if (note === null) return;
      return store.setFlag(mode, solve.id, true, note);
    }
    case "note": {
      const note = prompt("Note for this solve:", solve.note || "");
      if (note === null) return;
      return store.setFlag(mode, solve.id, true, note);
    }
    case "delete": {
      const what = `${fmtSolve(solve)}${solve.case ? ` (${solve.case})` : ""}`;
      if (!confirm(`Delete the solve ${what}? It is removed from every statistic.`)) return;
      return store.deleteSolve(mode, solve.id);
    }
  }
}

/** Small action buttons for a solve; data-act names the action. */
export function actionButtons(solve, { labels = true } = {}) {
  const b = (act, text, title, on = false) =>
    h(`button.btn.small${on ? ".on" : ""}`, { type: "button", text, title, "data-act": act });
  return [
    b("ok", "OK", "No penalty", !solve.penalty),
    b("+2", "+2", "Plus two seconds", solve.penalty === "+2"),
    b("dnf", "DNF", "Did not finish", solve.penalty === "dnf"),
    b("flag", solve.flagged ? "⚑ Unflag" : "⚑ Flag", solve.flagged ? "Remove the flag and its note" : "Flag for later, with a note", solve.flagged),
    labels && solve.flagged ? b("note", "Note…", "Edit the note") : null,
    b("delete", "✕", "Delete this solve"),
  ].filter(Boolean);
}

/** Classes for a solve's time: plus2 / dnf colour it. */
export const timeClass = (solve) => (solve.penalty === "dnf" ? "dnf" : solve.penalty === "+2" ? "plus2" : "");

/**
 * The current session: header with New session, stats, and the history.
 * Clicking a solve opens its action bar (one delegated listener for the list).
 */
export function sessionPanel(store, mode, { title, showCase = false }) {
  const head = h("span.session-title");
  const newBtn = h("button.btn.small", {
    type: "button", text: "New session", title: "Start a new session: session stats and history begin again",
    onclick: async () => {
      const n = store.stats[mode].session.count;
      if (n && !confirm(`Start a new ${title} session?\nThe ${n} solve(s) of this session stay in the all-time statistics.`)) return;
      openId = null;
      await store.newSession(mode);
    },
  });
  const stats = statsBlock({ compact: true });
  const list = h("ul.history.solves");
  const hint = h("div.hint", { text: "Click a solve: +2 / DNF / flag / delete" });
  let openId = null;

  list.addEventListener("click", (e) => {
    // a solve's row has data-id; its open action bar has data-for
    const li = e.target.closest("li[data-id], li[data-for]");
    if (!li) return;
    const id = li.dataset.id || li.dataset.for;
    const solve = store.recent[mode].find((s) => String(s.id) === id);
    if (!solve) return;
    const btn = e.target.closest("button[data-act]");
    if (btn) { solveAction(store, mode, solve, btn.dataset.act); return; }
    if (li.dataset.for) return;
    openId = openId === solve.id ? null : solve.id;
    refresh();
  });

  function refresh() {
    const st = store.stats[mode];
    head.textContent = `Session ${st.session_no}`;
    stats.update(st);
    const rows = store.recent[mode];
    const total = st.session.count;
    if (!rows.length) {
      list.replaceChildren(h("li.empty", { text: "No solves in this session yet." }));
      return;
    }
    list.replaceChildren(...rows.flatMap((s, i) => {
      const li = h(`li${s.id === openId ? ".open" : ""}`, s.id == null ? null : { "data-id": s.id },
        h("span.n", { text: String(Math.max(total, rows.length) - i) }),
        h("span.case", { text: showCase ? s.case || "?" : s.ts.slice(5, 16) }),
        h("span.flag", { text: s.flagged ? "⚑" : "", title: s.note || (s.flagged ? "Flagged" : "") }),
        h(`span.time${timeClass(s) ? "." + timeClass(s) : ""}`, { text: fmtSolve(s) }));
      if (s.id !== openId || s.id == null) return [li];
      const bar = h("li.actions", { "data-for": s.id }, ...actionButtons(s));
      const note = s.note ? h("li.note", { text: `⚑ ${s.note}` }) : null;
      return note ? [li, note, bar] : [li, bar];
    }));
  }

  const el = h("div.session-panel", null,
    h("div.session-head", null, head, newBtn),
    stats.el, hint, h("div.scroll", null, list));
  return { el, refresh };
}

/** "Last solve: OK +2 DNF ⚑" for the newest attempt in the session. */
export function lastSolveBar(store, mode) {
  const el = h("div.last-solve");
  el.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-act]");
    if (btn) solveAction(store, mode, store.recent[mode][0], btn.dataset.act);
  });
  function refresh() {
    const s = store.recent[mode][0];
    if (!s) { el.replaceChildren(); return; }
    const buttons = actionButtons(s, { labels: false }).filter((b) => b.dataset.act !== "delete");
    if (s.id == null) buttons.forEach((b) => { b.disabled = true; });
    el.replaceChildren(h("span.label", { text: `Last solve ${fmtSolve(s)}:` }), ...buttons);
  }
  return { el, refresh };
}
