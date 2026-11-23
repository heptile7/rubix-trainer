// Sessions and single solves, shared by Full Solve, the OLL / PLL trainers and
// Statistics (the web side of SessionPanel in cube_timer_gui.py):
//   statsBlock      - session vs all-time summary (count, best, mean, std dev,
//                     current and best ao3 ... ao100)
//   solveAction     - +2 / DNF / OK, flag (with a note), note, delete
//   sessionPanel    - "Session N" + New session, the stats and the history list
//   previousSolve   - card beside the clock: the newest attempt's time, case and
//                     scramble, with OK / +2 / DNF / Flag (the timer deals the next
//                     scramble on stop, so this is where a solve is reviewed)
// Every change goes through the store, which repaints listeners via onTimes.

import { h, fmt, fmtSolve } from "./util.js";

export const SUMMARY_ROWS = [
  ["count", "Solves"], ["dnf_rate", "DNF rate"], ["best", "Best"], ["worst", "Worst"], ["mean", "Mean"], ["sd", "Std dev"],
];
export const AVERAGES = [3, 5, 12, 50, 100];
// the side panel's single table (Full Solve, the trainers' History tab)
const COMPACT_ROWS = [
  ["count", "Solves"], ["best", "Best"], ["mean", "Mean"], ["sd", "Std dev"],
  ["ao5", "ao5"], ["ao12", "ao12"], ["ao100", "ao100"],
  ["best_ao5", "Best ao5"], ["best_ao12", "Best ao12"],
];
const SD_TITLE = "Standard deviation of the finished solves: how consistent they are (lower is steadier)";

const statValue = (st, key) =>
  key === "count" ? (st.dnf ? `${st.count}  (${st.dnf} DNF)` : String(st.count))
  : key === "dnf_rate" ? (st.dnf_rate == null ? "—" : `${(st.dnf_rate * 100).toFixed(1)}%`)
  : fmt(st[key]);

/** One line saying how DNFs count in the averages shown. */
export const averageRule = (st) => st && st.skip_dnf
  ? "DNFs are left out of these averages (finished solves only)."
  : "WCA averages: a DNF counts as the slowest time, so two in an ao5 or ao12 make it a DNF.";

/** A table: [label, ...cells] rows under a head row. */
function grid(head, rows, ncols) {
  const heads = head.map((t) => h("th", { text: t }));
  const cells = rows.map(() => Array.from({ length: ncols }, () => h("td.num")));
  const el = h("table.stat-block", null,
    h("thead", null, h("tr", null, h("th"), ...heads)),
    h("tbody", null, ...rows.map(([key, label], i) =>
      h("tr", { "data-key": key, title: key === "sd" ? SD_TITLE : "" }, h("th", { text: label }), ...cells[i]))));
  return { el, heads, cells };
}

/**
 * Session vs all-time stats; update(stats) takes store.stats[mode].
 * compact: one table (session | all time). Otherwise, as on Statistics, a
 * summary table (session | all time) and an averages table: each ao<n> now,
 * the best in the session and the best of all time.
 */
export function statsBlock({ compact = false, extra = null } = {}) {
  if (compact) {
    const t = grid(["Session", "All time"], COMPACT_ROWS, 2);
    return {
      el: t.el,
      update(stats) {
        t.heads[0].textContent = stats.session_name || `Session ${stats.session_no}`;
        t.heads[0].title = "The selected session";
        COMPACT_ROWS.forEach(([key], i) => {
          t.cells[i][0].textContent = statValue(stats.session, key);
          t.cells[i][1].textContent = statValue(stats.all, key);
        });
      },
    };
  }
  const sum = grid(["Session", "All time"], SUMMARY_ROWS, 2);
  const avgRows = AVERAGES.map((n) => [`ao${n}`, `ao${n}`]);
  const avg = grid(["Current", "Session best", "All-time best"], avgRows, 3);
  avg.heads[0].title = "The average of your latest n solves in the session";
  avgRows[0] && (avg.el.querySelector("tbody th").title = "ao3 is the mean of 3 (nothing trimmed)");
  const rule = h("p.avg-rule");
  const el = h("div.stat-blocks", null, sum.el, h("div.avg-col", null, avg.el, rule, ...(extra ? [extra] : [])));
  return {
    el,
    update(stats) {
      sum.heads[0].textContent = stats.session_name || `Session ${stats.session_no}`;
      sum.heads[0].title = "The selected session";
      rule.textContent = averageRule(stats.session);
      SUMMARY_ROWS.forEach(([key], i) => {
        sum.cells[i][0].textContent = statValue(stats.session, key);
        sum.cells[i][1].textContent = statValue(stats.all, key);
      });
      AVERAGES.forEach((n, i) => {
        const [now, sbest, abest] = avg.cells[i];
        now.textContent = fmt(stats.session[`ao${n}`]);
        sbest.textContent = fmt(stats.session[`best_ao${n}`]);
        abest.textContent = fmt(stats.all[`best_ao${n}`]);
        // the session holds the all-time best (worth saying only if there are older solves)
        const pb = stats.all.count > stats.session.count && stats.all[`best_ao${n}`] != null
          && stats.session[`best_ao${n}`] === stats.all[`best_ao${n}`];
        sbest.classList.toggle("pb", pb);
        abest.classList.toggle("pb", pb);
      });
    },
  };
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
 * Session picker: a select of the mode's named sessions plus New / Rename /
 * Delete. Picking one selects it on the server (new attempts go into it).
 * onChange runs before each change (e.g. to close an open action bar).
 */
export function sessionPicker(store, mode, { title, onChange = () => {} }) {
  const select = h("select.session-select", { title: "Session: new solves go into the selected one" });
  select.onchange = () => { onChange(); select.blur(); store.selectSession(mode, Number(select.value)); };
  const small = (text, tip, onclick) => h("button.btn.small", { type: "button", text, title: tip, onclick });
  const el = h("div.session-picker", null, select,
    small("New…", "Start a new session (e.g. one per cube)", async () => {
      const st = store.stats[mode];
      const name = prompt(`Name for the new ${title} session (e.g. the cube you use):`, `Session ${Math.max(...st.sessions.map((s) => s.n)) + 1}`);
      if (name === null) return;
      onChange();
      await store.newSession(mode, name);
    }),
    small("Rename…", "Rename this session", async () => {
      const st = store.stats[mode];
      const name = prompt("New name for this session:", st.session_name);
      if (name === null || !name.trim()) return;
      await store.renameSession(mode, st.session_no, name);
    }),
    small("Delete…", "Delete this session and its solves", async () => {
      const st = store.stats[mode];
      if (st.sessions.length < 2) { alert("This is the only session, so it can't be deleted."); return; }
      const n = st.session.count;
      if (!confirm(`Delete the session “${st.session_name}”` +
                   (n ? ` and its ${n} solve(s)? They are removed from every statistic.` : "?"))) return;
      onChange();
      await store.deleteSession(mode, st.session_no);
    }));

  let shownKey = "";
  function refresh() {
    const st = store.stats[mode];
    const key = JSON.stringify([st.session_no, st.sessions]);
    if (key === shownKey) return;
    shownKey = key;
    select.replaceChildren(...st.sessions.map((s) =>
      h("option", { value: s.n, text: `${s.name}  (${s.count})`, selected: s.n === st.session_no })));
  }
  return { el, refresh };
}

/**
 * The selected session: its picker, stats, and the history.
 * Clicking a solve opens its action bar (one delegated listener for the list).
 */
export function sessionPanel(store, mode, { title, showCase = false }) {
  const picker = sessionPicker(store, mode, { title, onChange: () => { openId = null; } });
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
    picker.refresh();
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
    picker.el, stats.el, hint, h("div.scroll", null, list));
  return { el, refresh };
}

/** "Last solve: OK +2 DNF ⚑" for the newest attempt in the session. */
export function previousSolve(store, mode, { showCase = false } = {}) {
  const time = h("div.prev-time");
  const caseEl = h("div.prev-case");
  const scramble = h("div.prev-scramble");
  const acts = h("div.prev-acts");
  const el = h("div.prev-solve", { hidden: true, title: "The previous solve" },
    h("div.caption", { text: "PREVIOUS SOLVE" }), time, showCase ? caseEl : null, scramble, acts);
  acts.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-act]");
    if (btn) solveAction(store, mode, store.recent[mode][0], btn.dataset.act);
  });
  function refresh() {
    const s = store.recent[mode][0];
    el.hidden = !s;
    if (!s) return;
    time.textContent = fmtSolve(s) + (s.flagged ? "  ⚑" : "");
    time.className = "prev-time" + (s.penalty === "dnf" ? " dnf" : "");
    caseEl.textContent = s.case || "";
    scramble.textContent = s.scramble || "(no scramble stored)";
    const buttons = actionButtons(s, { labels: false }).filter((b) => b.dataset.act !== "delete");
    if (s.id == null) buttons.forEach((b) => { b.disabled = true; });   // until the server has saved it
    acts.replaceChildren(...buttons);
  }
  return { el, refresh };
}

/** OK / +2 / DNF / Flag in one row (kept for other layouts; the timers use previousSolve). */
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
