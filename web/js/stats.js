// Statistics (StatsScreen): for Full Solve, OLL and PLL, the session and
// all-time summary, then every solve with its ao5 / ao12 and actions
// (+2 / DNF / flag / delete), filtered by session or all time and by flag.
// OLL / PLL also have the per-case progress table.
// Fetched when the screen or a filter changes; tables are built as one HTML string.

import { api } from "./api.js";
import { h, fmt, fmtSolve } from "./util.js";
import { statsBlock, solveAction, timeClass, sessionPicker } from "./solves.js";
import { progressChart } from "./chart.js";

const LIMIT = 200;      // rows listed at most (the stats cover every solve)
const CHART_LIMIT = 5000;  // solves charted at most

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

/**
 * Export (CSV / backup / csTimer downloads) and Import (a backup or a csTimer
 * file; merged on the server after it copies the database), for the page head.
 */
function exportImport() {
  const link = (href, text, title) => h("a.menu-item", { href, text, title, download: "" });
  const menu = h("details.menu", null,
    h("summary.btn", { text: "Export ▾" }),
    h("div.menu-list", null,
      link("/api/export/csv", "CSV (spreadsheet)", "Every solve, one row each"),
      link("/api/export/backup", "Cube Timer backup", "Sessions, solves, selections and groups; import it here later"),
      link("/api/export/cstimer?modes=full,oll,pll", "csTimer file", "Open in csTimer with Import from file")));
  document.addEventListener("click", (e) => { if (!menu.contains(e.target)) menu.open = false; });
  const file = h("input", { type: "file", accept: ".json,.txt,application/json,text/plain", hidden: true });
  file.onchange = async () => {
    const f = file.files[0];
    file.value = "";
    if (!f) return;
    let data;
    try { data = JSON.parse(await f.text()); } catch {
      alert("That file isn't a Cube Timer backup or a csTimer export (it isn't JSON). CSV files can't be imported.");
      return;
    }
    const cstimer = data && data.properties && Object.keys(data).some((k) => /^session\d+$/.test(k));
    const what = data && data.app === "cube-timer" ? "this Cube Timer backup"
      : cstimer ? "this csTimer file (its sessions go into Full Solve)" : null;
    if (!what) { alert("That file is neither a Cube Timer backup nor a csTimer export."); return; }
    if (!confirm(`Import ${what}?
Solves you already have are skipped; nothing is replaced, and the database is copied first.`)) return;
    const res = await fetch("/api/import", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data, mode: "full" }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) { alert(`Couldn't import: ${body.detail || res.statusText}`); return; }
    alert(body.message);
    location.reload();      // every screen reads the merged data afresh
  };
  const importBtn = h("button.btn", { type: "button", text: "Import…", title: "Merge a Cube Timer backup or a csTimer export",
                                      onclick: () => file.click() });
  return h("div.row.io", null, menu, importBtn, file);
}

export function statsScreen(store) {
  let mode = "full", scope = "session", view = "solves", flaggedOnly = false;
  let rows = [];
  let token = 0;
  let shown = false;

  const summary = statsBlock();
  const body = h("div");
  const note = h("div.hint", { style: "text-align:left" });
  const tabs = seg([["full", "Full Solve"], ["oll", "OLL"], ["pll", "PLL"]], (k) => {
    mode = k;
    if (mode === "full" && view === "cases") { view = "solves"; viewSeg.set(view); }
    show();
  });
  const scopeSeg = seg([["session", "This session"], ["all", "All time"]], (k) => { scope = k; show(); });
  const viewSeg = seg([["solves", "Solves"], ["chart", "Chart"], ["cases", "Cases"]], (k) => { view = k; show(); });
  const flagBox = h("input", { type: "checkbox", onchange: () => { flaggedOnly = flagBox.checked; show(); } });
  const flagLabel = h("label.switch", null, flagBox, "Flagged only");
  const caseSelect = h("select.small-select.chart-case", { title: "Chart one case", onchange: () => { caseSelect.blur(); show(); } });
  const chart = progressChart();
  tabs.set(mode); scopeSeg.set(scope); viewSeg.set(view);
  // one session picker per mode; the open mode's is shown
  const titles = { full: "Full Solve", oll: "OLL", pll: "PLL" };
  const pickers = Object.fromEntries(Object.keys(titles).map((m) => [m, sessionPicker(store, m, { title: titles[m] })]));

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
    for (const [m, p] of Object.entries(pickers)) { p.el.hidden = m !== mode; if (m === mode) p.refresh(); }
    viewSeg.el.querySelector("[data-key=cases]").hidden = mode === "full";
    flagLabel.hidden = view !== "solves";
    scopeSeg.el.hidden = view === "cases";
    syncCases();
    caseSelect.hidden = !(view === "chart" && mode !== "full");
    chart.el.hidden = view !== "chart";
    body.hidden = view === "chart";
    try {
      let html;
      if (view === "chart") {
        const caseName = mode === "full" ? "" : caseSelect.value;
        const r = await api.solves(mode, scope, false, CHART_LIMIT, caseName);
        if (t !== token) return;
        const { rows: _rows, total: _total, ...fresh } = r;
        store.stats[mode] = fresh;
        pickers[mode].refresh();
        summary.update(store.stats[mode]);
        const names = Object.fromEntries(fresh.sessions.map((x) => [x.n, x.name]));
        chart.update(r.rows, names, scope === "all");
        note.textContent = (r.rows.length >= CHART_LIMIT ? `Latest ${CHART_LIMIT} shown; ` : "") +
          `${r.rows.length} solve(s)${caseName ? ` of ${caseName}` : ""} in ` +
          `${scope === "session" ? `“${fresh.session_name}”` : "all sessions"}. Hover or use the arrow keys for values.`;
        return;
      }
      if (mode !== "full" && view === "cases") {
        html = caseTable(store.cases[mode], await api.summary(mode));
        note.textContent = "Best and average leave out DNFs; +2 penalties are included.";
      } else {
        const r = await api.solves(mode, scope, flaggedOnly, LIMIT);
        if (t !== token) return;
        rows = r.rows;
        const { rows: _rows, total: _total, ...fresh } = r;
        store.stats[mode] = fresh;
        pickers[mode].refresh();
        summary.update(store.stats[mode]);
        const best = (scope === "session" ? r.session : r.all).best;
        html = solveTable(mode, rows, best);
        const what = flaggedOnly ? "flagged solves" : "solves";
        note.textContent = (rows.length >= LIMIT ? `Latest ${LIMIT} ${what} shown; ` : "") +
          `${r.total} solve(s) in ${scope === "session" ? `“${r.session_name}”` : "all"}.`;
      }
      if (t === token) body.innerHTML = html;
    } catch (err) {
      if (t === token) body.innerHTML = '<p class="muted">Couldn\'t load statistics - is the server running?</p>';
    }
  }

  let casesFor = "";
  function syncCases() {
    if (mode === "full" || casesFor === mode) return;
    casesFor = mode;
    caseSelect.replaceChildren(h("option", { value: "", text: "All cases" }),
      ...store.cases[mode].map((c) => h("option", { value: c.name, text: c.name })));
  }

  const el = h("section.screen.stats-screen", null,
    h("div.page-head", null, h("h1", { text: "Statistics" }),
      h("div.row", null, exportImport(),
        h("button.btn", { type: "button", text: "Refresh", onclick: () => show() }))),
    h("div.tabs", null, tabs.el),
    summary.el,
    h("div.row.stats-filters", null, viewSeg.el, ...Object.values(pickers).map((p) => p.el), scopeSeg.el,
      flagLabel, caseSelect),
    note,
    chart.el,
    body);
  return {
    el,
    chart,
    onShow: () => { shown = true; show(); },
    onHide: () => { shown = false; },
  };
}
