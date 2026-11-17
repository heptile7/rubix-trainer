// Case Gallery: a picture of every OLL and PLL case, grouped by shape
// (CasesScreen). Click selects, double-click practises that one case,
// clicking the status cycles it. Cards are built once; refresh flips classes.

import { h, STATUSES, groupOrder } from "./util.js";
import { selectionTools, myGroups, groupHeader } from "./widgets.js";

export function galleryScreen(store, { openCase, practiseSelected }) {
  const panes = {};
  const tabButtons = {};
  const refreshers = {};

  function buildPane(mode) {
    const cases = store.cases[mode];
    const practise = h("button.btn.primary", { type: "button", onclick: () => practiseSelected(mode) });
    const cards = new Map();
    const headers = [];
    const sections = [];
    for (const group of groupOrder(cases)) {
      const members = cases.filter((c) => c.group === group);
      const header = groupHeader(group, (g) => store.toggleGroup(mode, g));
      const grid = h("div.cards");
      for (const c of members) {
        const card = h("div.card", { "data-name": c.name });
        card.innerHTML = c.svg;
        card.append(
          h("div.name", { text: c.name }),
          h("div.group", { text: c.group }),
          h("div.alg", { text: c.alg }),
          h("div.status", { title: "Click to change" }));
        cards.set(c.name, card);
        grid.append(card);
      }
      headers.push([header, members.map((c) => c.name)]);
      sections.push(h("div.lazy", null, header.el, grid));
    }

    const body = h("div.gallery-pane", null, myGroups(store, mode), ...sections);
    const caseOf = (e) => {
      const card = e.target.closest(".card");
      return card ? store.byName[mode][card.dataset.name] : null;
    };
    body.addEventListener("click", (e) => {
      const c = caseOf(e);
      if (!c) return;
      if (e.target.closest(".status")) {
        // Unlearned -> Learning -> Finished -> Unlearned
        const i = STATUSES.indexOf(store.status(mode, c.name));
        store.setStatus(mode, c.name, STATUSES[(i + 1) % STATUSES.length]);
      } else if (e.detail < 2) {    // a double-click's second click: see dblclick
        store.toggle(mode, c.name);
      }
    });
    body.addEventListener("dblclick", (e) => {
      const c = caseOf(e);
      if (!c || e.target.closest(".status")) return;
      // the first click of the double-click toggled the card; put it back
      store.toggle(mode, c.name);
      openCase(mode, c);
    });

    const pane = h("div", { hidden: true }, h("div.gallery-bar", null,
      selectionTools(store, mode), practise), body);

    refreshers[mode] = () => {
      const sel = store.selected[mode];
      for (const [name, card] of cards) {
        const s = store.status(mode, name);
        card.className = "card" + (sel.has(name) ? " sel" : "") + (s === "unlearned" ? "" : ` st-${s}`);
        const label = card.lastElementChild;
        const text = s.toUpperCase();
        if (label.textContent !== text) label.textContent = text;
      }
      for (const [header, names] of headers) header.show(names.filter((n) => sel.has(n)).length, names.length);
      practise.textContent = `Practise selected (${sel.size})`;
      practise.disabled = !sel.size;
    };
    refreshers[mode]();
    store.listen((m) => m === mode && refreshers[mode]());
    return pane;
  }

  const tabs = h("div.seg.tabs");
  function showTab(mode) {
    for (const m of ["oll", "pll"]) {
      panes[m].hidden = m !== mode;
      tabButtons[m].classList.toggle("on", m === mode);
    }
  }
  for (const mode of ["oll", "pll"]) {
    panes[mode] = buildPane(mode);
    tabButtons[mode] = h("button", { type: "button", text: `${mode.toUpperCase()} (${store.cases[mode].length})`,
                                     onclick: () => showTab(mode) });
    tabs.append(tabButtons[mode]);
  }
  showTab("oll");

  const el = h("section.screen", null,
    h("div.page-head", null, h("h1", { text: "Case Gallery" }),
      h("span.muted", { text: "Click to select  •  double-click to practise one case  •  click the status to change it" })),
    tabs, panes.oll, panes.pll);
  return { el, showTab };
}
