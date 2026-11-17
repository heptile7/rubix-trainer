// Statistics: Full Solve session table and OLL / PLL progress (StatsScreen).
// Fetched when the screen or a tab is opened; tables are built as one HTML string.

import { api } from "./api.js";
import { h, fmt, calcAo } from "./util.js";

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const td = (v, cls = "") => `<td${cls ? ` class="${cls}"` : ""}>${esc(v)}</td>`;

function sessionTable(rows) {
  if (!rows.length) return '<p class="muted">No times recorded yet.</p>';
  const all = rows.map((r) => r[0]);
  const best = Math.min(...all);
  let html = '<table class="stats"><thead><tr><th>#</th><th>Time</th><th>ao5</th><th>ao12</th><th>Timestamp</th></tr></thead><tbody>';
  rows.forEach(([t, ts], i) => {
    const a5 = calcAo(all.slice(i), 5), a12 = calcAo(all.slice(i), 12);
    html += "<tr>" + td(rows.length - i) + td(fmt(t), t === best ? "num best" : "num") +
            td(a5 ? fmt(a5) : "—", "num") + td(a12 ? fmt(a12) : "—", "num") + td(ts) + "</tr>";
  });
  const mean = all.reduce((a, b) => a + b, 0) / all.length;
  const a5 = calcAo(all, 5), a12 = calcAo(all, 12);
  const summary = `Count: ${all.length}   Best: ${fmt(best)}   Mean: ${fmt(mean)}` +
                  (a5 ? `   ao5: ${fmt(a5)}` : "") + (a12 ? `   ao12: ${fmt(a12)}` : "");
  return html + `</tbody></table><div class="summary">${esc(summary)}</div>`;
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

export function statsScreen(store) {
  const tabs = [["full", "Full Solve"], ["oll", "OLL Progress"], ["pll", "PLL Progress"]];
  let tab = "full";
  let token = 0;
  const body = h("div");
  const buttons = tabs.map(([key, label]) => h("button", { type: "button", text: label, onclick: () => show(key) }));

  async function show(key) {
    tab = key;
    buttons.forEach((b, i) => b.classList.toggle("on", tabs[i][0] === key));
    const t = ++token;
    try {
      const html = key === "full"
        ? sessionTable(await api.times("full", 50))
        : caseTable(store.cases[key], await api.summary(key));
      if (t === token) body.innerHTML = html;
    } catch (err) {
      if (t === token) body.innerHTML = '<p class="muted">Couldn\'t load statistics - is the server running?</p>';
    }
  }

  const el = h("section.screen", null,
    h("div.page-head", null, h("h1", { text: "Statistics" }),
      h("button.btn", { type: "button", text: "Refresh", onclick: () => show(tab) })),
    h("div.seg.tabs", null, ...buttons),
    body);
  return { el, onShow: () => show(tab) };
}
