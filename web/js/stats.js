// Statistics (StatsScreen): for Full Solve, OLL and PLL, the session and
// all-time summary, then every solve with its ao5 / ao12 and actions
// (+2 / DNF / flag / delete), filtered by session or all time and by flag.
// OLL / PLL also have the per-case progress table.
// Fetched when the screen or a filter changes; tables are built as one HTML string.

import { api } from "./api.js";
import { h, fmt, fmtSolve } from "./util.js";
import { statsBlock, solveAction, timeClass } from "./solves.js";

const LIMIT = 200;      // rows listed at most (the stats cover every solve)

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const td = (v, cls = "") => `<td${cls ? ` class="${cls}"` : ""}>${esc(v)}</td>`;

function solveTable(mode, rows, best) {
  if (!rows.length) return '<p class="muted">No solves here yet.</p>';
  const caseCol = mode !== "full";
  let html = '<table class="stats solves-table"><thead><tr><th>#</th>' + (caseCol ? "<th>Case</th>" : "") +
    "<th>Time</th><th>ao5</th><th>ao12</th><th>Flag / note</th><th>Date</th><th></th></tr></thead><tbody>";
  for (const r of rows) {
    const cls = ["num", timeClass(r), r.time === best ? "best" : ""].filter(Boolean).join(" ");
    const btn = (act, text, title, on) =>
      `<button type="button" class="btn small${on ? " on" : ""}" data-act="${act}" title="${title}">${text}</button>`;
    html += `<tr data-id="${r.id}">` + td(r.n) + (caseCol ? td(r.case) : "") +
      td(fmtSolve(r), cls) + td(fmt(r.ao5), "num") + td(fmt(r.ao12), "num") +
      `<td class="note">${r.flagged ? `⚑ ${esc(r.note || "")}` : ""}</td>` + td(r.ts, "ts") +
      '<td class="acts">' +
      btn("+2", "+2", "Plus two seconds", r.penalty === "+2") +
      btn("dnf", "DNF", "Did not finish", r.penalty === "dnf") +
      btn("flag", "⚑", r.flagged ? "Unflag" : "Flag, with a note", r.flagged) +
      (r.flagged ? btn("note", "✎", "Edit the note") : "") +
      btn("delete", "✕", "Delete this solve") + "</td></tr>";
  }
  return html + "</tbody></table>";
}

function caseTable(cases, summary) {
  let html = '<table class="stats"><thead><tr><th>Case</th><th>Group</th><th>Algorithm</th><th>N</th><th>Best</th><th>Avg</th></tr></thead><tbody>';
  for (const c of cases) {
    const row = summary[c.name];
    html += "<tr>" + td(c.name) + td(c.group) + `<td class="alg" title="${esc(c.alg)}">${esc(c.alg)}</td>` +
            td(row ? row[0] : "—", "num") + td(row ? fmt(row[1]) : "—", row ? "num has" : "num") +
            td(row ? fmt(row[2]) : "—", "num") + "</tr>";
  }
  return html + "</tbody></table>";
}

function seg(values, onPick) {
  const buttons = values.map(([key, label]) => h("button", { type: "button", text: label, "data-key": key }));
  const el = h("div.seg", null, ...buttons);
  const set = (key) => buttons.forEach((b) => b.classList.toggle("on", b.dataset.key === key));
  el.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (b) { set(b.dataset.key); onPick(b.dataset.key); }
  });
  return { el, set };
}

export function statsScreen(store) {
  let mode = "full", scope = "session", view = "solves", flaggedOnly = false;
  let rows = [];
  let token = 0;
  let shown = false;

  const summary = statsBlock();
  const body = h("div");
  const note = h("div.hint", { style: "text-align:left" });
  const tabs = seg([["full", "Full Solve"], ["oll", "OLL"], ["pll", "PLL"]], (k) => { mode = k; viewSeg.el.hidden = k === "full"; show(); });
  const scopeSeg = seg([["session", "This session"], ["all", "All time"]], (k) => { scope = k; show(); });
  const viewSeg = seg([["solves", "Solves"], ["cases", "Cases"]], (k) => { view = k; show(); });
  const flagBox = h("input", { type: "checkbox", onchange: () => { flaggedOnly = flagBox.checked; show(); } });
  tabs.set(mode); scopeSeg.set(scope); viewSeg.set(view); viewSeg.el.hidden = true;

  body.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-act]");
    const tr = btn && btn.closest("tr[data-id]");
    if (!tr) return;
    const solve = rows.find((r) => String(r.id) === tr.dataset.id);
    // the table's rows carry `time` too; solveAction only needs id / penalty / flag / note
    solveAction(store, mode, solve, btn.dataset.act);
  });
  // a change anywhere (here, a history, a new attempt) repaints the open table
  store.onTimes((m) => shown && m === mode && show());

  async function show() {
    const t = ++token;
    summary.update(store.stats[mode]);
    try {
      let html;
      if (mode !== "full" && view === "cases") {
        html = caseTable(store.cases[mode], await api.summary(mode));
        note.textContent = "Best and average leave out DNFs; +2 penalties are included.";
      } else {
        const r = await api.solves(mode, scope, flaggedOnly, LIMIT);
        if (t !== token) return;
        rows = r.rows;
        store.stats[mode] = { session_no: r.session_no, session: r.session, all: r.all };
        summary.update(store.stats[mode]);
        const best = (scope === "session" ? r.session : r.all).best;
        html = solveTable(mode, rows, best);
        const what = flaggedOnly ? "flagged solves" : "solves";
        note.textContent = (rows.length >= LIMIT ? `Latest ${LIMIT} ${what} shown; ` : "") +
          `${r.total} solve(s) in ${scope === "session" ? `session ${r.session_no}` : "all"}.`;
      }
      if (t === token) body.innerHTML = html;
    } catch (err) {
      if (t === token) body.innerHTML = '<p class="muted">Couldn\'t load statistics - is the server running?</p>';
    }
  }

  const el = h("section.screen.stats-screen", null,
    h("div.page-head", null, h("h1", { text: "Statistics" }),
      h("button.btn", { type: "button", text: "Refresh", onclick: () => show() })),
    h("div.tabs", null, tabs.el),
    summary.el,
    h("div.row.stats-filters", null, viewSeg.el, scopeSeg.el,
      h("label.switch", null, flagBox, "Flagged only")),
    note,
    body);
  return {
    el,
    onShow: () => { shown = true; show(); },
    onHide: () => { shown = false; },
  };
}
