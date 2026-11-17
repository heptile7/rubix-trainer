// OLL / PLL practice: a port of CaseTrainerScreen. Each round deals a case
// from the chosen source (or the pinned case), shows a scramble that sets it
// up, and records the time. The right-hand column holds the picker and history.
//
// Speed: the next case is chosen and its scramble fetched as soon as the
// current one is shown, so Next / Space never waits on the server.

import { api } from "./api.js";
import { diagramSvg } from "./diagram.js";
import { Timer } from "./timer.js";
import { h, fmt, STATUSES, SLOWEST_COUNT, titleCase, groupOrder, pick, pickWeighted, resultBar, toast } from "./util.js";
import { selectionTools, casePicker } from "./widgets.js";

const PICK_HINT = "Click: select  •  double-click: pin";
const READY = "Scramble from solved (yellow top, green front), then press SPACE";
const EMPTY_NOTE = {
  selected: "Nothing selected yet - click cases in the picker.",
  slowest: "No times yet to find the slowest cases.",
  status: "No cases have that status yet.",
  custom: "That group no longer exists.",
};

function segmented(values, onPick) {
  const el = h("div.seg");
  const buttons = values.map((v) => h("button", { type: "button", text: v, onclick: () => { set(v); onPick(v); } }));
  el.append(...buttons);
  const set = (v) => buttons.forEach((b) => b.classList.toggle("on", b.textContent === v));
  return { el, set, get: () => buttons.find((b) => b.classList.contains("on"))?.textContent };
}

export function trainerScreen(store, mode, title) {
  const cases = store.cases[mode];
  const groups = groupOrder(cases);
  const selection = store.selected[mode];

  let source = "all";          // all | selected | slowest | status:<s> | custom:<name> | group:<name>
  let sourceBefore = null;     // source before a picker click (see pin)
  let pinned = null;           // a case to repeat instead of dealing
  let current = null;
  let scramble = "";
  let loadToken = 0;
  let upcoming = null;         // {case, note, deal, key}: chosen ahead, scramble on its way

  // ---- main column --------------------------------------------------------
  const sourceSelect = h("select", { title: "Where cases come from" });
  sourceSelect.onchange = () => setSource(sourceSelect.value);
  const odds = segmented(["Balanced", "Realistic"], () => { upcoming = null; prepareNext(); });
  odds.set("Balanced");
  const statusSeg = segmented(STATUSES.map(titleCase), (v) => current && store.setStatus(mode, current.name, v.toLowerCase()));
  const hint = h("input", { type: "checkbox", checked: true, onchange: showAlg });

  const pic = h("div.pic");
  const nameEl = h("div.case-name");
  const groupEl = h("div.case-group");
  const algEl = h("div.case-alg");
  const scrambleEl = h("div.case-scramble");
  const timerLabel = h("div.timer", { text: "0.00" });
  const statusLine = h("div.status-line");
  const startBtn = h("button.btn.big.primary", { type: "button", text: "Start  [space]" });
  const result = h("div.result-bar");

  const main = h("div.timer-main", null,
    h("h1", { text: title, style: "margin:0 0 2px" }),
    h("div.row", null, h("span.label", { text: "From:" }), sourceSelect,
      h("span.label", { text: "Odds:", style: "margin-left:14px" }), odds.el),
    h("div.row", null, h("span.label", { text: "This case:" }), statusSeg.el,
      h("label.switch", { style: "margin-left:20px" }, hint, "Show algorithm")),
    h("div.case-panel", null,
      h("div.case-head", null, pic, h("div.case-text", null, nameEl, groupEl, algEl)),
      h("div.caption", { text: "SCRAMBLE" }),
      scrambleEl),
    timerLabel,
    statusLine,
    h("div.row", null,
      startBtn,
      h("button.btn.big", { type: "button", text: "Next Case", onclick: () => pickNextCase() }),
      h("button.btn.big.danger", { type: "button", text: "Delete Last", onclick: deleteLast })),
    result);

  // ---- side column: Cases | History ---------------------------------------
  const hoverLabel = h("div.hint", { text: PICK_HINT });
  const pinLabel = h("span");
  const pinBar = h("div.pin-bar", { hidden: true }, pinLabel,
    h("button.btn.small", { type: "button", text: "✕ Unpin", onclick: unpin }));
  const picker = casePicker(store, mode, {
    onToggle(c) { sourceBefore = source; store.toggle(mode, c.name); onSetEdited(); },
    onToggleGroup(g) { store.toggleGroup(mode, g); onSetEdited(); },
    onPin: pin,
    onHover(c) {
      if (!c) { hoverLabel.textContent = PICK_HINT; hoverLabel.style.color = ""; return; }
      hoverLabel.textContent = `${c.name}  •  ${c.group}  •  ${store.status(mode, c.name)}`;
      hoverLabel.style.color = "var(--text)";
    },
    onEdit: onSetEdited,
  });
  const casesTab = h("div.side-body", null,
    selectionTools(store, mode, { compact: true, onEdit: onSetEdited }),
    hoverLabel, pinBar, picker.el);
  const historySummary = h("div.hint");
  const historyList = h("ul.history");
  const historyTab = h("div.side-body", { hidden: true }, historySummary, h("div.scroll", null, historyList));
  const sideTabs = segmented(["Cases", "History"], (v) => {
    casesTab.hidden = v !== "Cases";
    historyTab.hidden = v === "Cases";
  });
  sideTabs.set("Cases");

  const el = h("section.screen", null,
    h("div.trainer", null, main, h("div.side", null, sideTabs.el, casesTab, historyTab)));

  // ---- where cases come from ----------------------------------------------
  const status = (c) => store.status(mode, c.name);

  function sourceOptions() {
    const opts = [["all", "All cases"], ["selected", `Selected (${selection.size})`],
                  ["slowest", `Slowest ${SLOWEST_COUNT}`]];
    for (const s of STATUSES) opts.push([`status:${s}`, `${titleCase(s)} (${cases.filter((c) => status(c) === s).length})`]);
    for (const [name, members] of store.groups(mode)) opts.push([`custom:${name}`, `★ ${name} (${members.size})`]);
    for (const g of groups) opts.push([`group:${g}`, g]);
    return opts;
  }

  let optionsKey = "";
  function syncPickers() {
    const opts = sourceOptions();
    const key = opts.map((o) => o.join("\u0001")).join("\u0002");
    if (key !== optionsKey) {
      optionsKey = key;
      sourceSelect.replaceChildren(...opts.map(([value, text]) => h("option", { value, text })));
    }
    sourceSelect.value = opts.some((o) => o[0] === source) ? source : "all";
  }

  function pool() {
    const i = source.indexOf(":");
    const kind = i < 0 ? source : source.slice(0, i), arg = i < 0 ? "" : source.slice(i + 1);
    if (kind === "all") return cases;
    if (kind === "selected") return cases.filter((c) => selection.has(c.name));
    if (kind === "slowest") {
      // slowest recent average among the selected cases (all if none selected)
      let base = cases.filter((c) => selection.has(c.name));
      if (!base.length) base = cases;
      const means = store.recentMeans(mode);
      return base.filter((c) => c.name in means)
        .sort((a, b) => means[b.name] - means[a.name]).slice(0, SLOWEST_COUNT);
    }
    if (kind === "status") return cases.filter((c) => status(c) === arg);
    if (kind === "custom") {
      const members = store.custom[mode].get(arg) || new Set();
      return cases.filter((c) => members.has(c.name));
    }
    return cases.filter((c) => c.group === arg);
  }

  function setSource(key) {
    source = key;
    pinned = null;
    pinBar.hidden = true;
    syncPickers();
    pickNextCase();
  }

  /** Editing the set from this page means: practise the set. */
  function onSetEdited() {
    if (source !== "selected") {
      source = "selected";
      syncPickers();
    }
  }

  function pin(c) {
    // the first click of the double-click toggled the case; put it back
    const before = sourceBefore;
    store.toggle(mode, c.name);
    if (before) { source = before; syncPickers(); }
    selectCase(c);
  }

  /** Practise one case over and over (picker or gallery double-click). */
  function selectCase(c) {
    pinned = c;
    pinLabel.textContent = `Pinned: ${c.name}`;
    pinBar.hidden = false;
    loadCase(c, null);
  }

  function unpin() {
    pinned = null;
    pinBar.hidden = true;
    pickNextCase();
  }

  // ---- dealing --------------------------------------------------------------
  const dealKey = () => `${source}|${pinned ? pinned.name : ""}|${odds.get()}`;

  function choose() {
    if (pinned) return { case: pinned, note: null };
    let p = pool(), note = null;
    if (!p.length) {
      p = cases;
      note = (EMPTY_NOTE[source.split(":")[0]] || "No cases here.") + " Using all cases.";
    }
    // don't deal the same case twice in a row when there is a choice
    const choices = p.length > 1 ? p.filter((c) => c !== current) : p;
    const c = odds.get() === "Realistic" ? pickWeighted(choices, choices.map((x) => x.weight)) : pick(choices);
    return { case: c, note };
  }

  const fetchDeal = (c) => api.deal(mode, c.name);

  /** Choose the next case now and start fetching its scramble. */
  function prepareNext() {
    const next = choose();
    upcoming = { ...next, key: dealKey(), deal: fetchDeal(next.case) };
    upcoming.deal.catch(() => {});   // reported when (if) it is used
  }

  function pickNextCase() {
    let next = upcoming;
    // still valid if nothing that decides the pool changed, and the case is in it
    if (!next || next.key !== dealKey() ||
        (!pinned && !next.note && !pool().includes(next.case))) next = null;
    upcoming = null;
    if (!next) {
      const c = choose();
      next = { ...c, deal: fetchDeal(c.case) };
    }
    loadCase(next.case, next.note, next.deal);
  }

  function loadCase(c, note, deal = fetchDeal(c)) {
    timer.reset();
    current = c;
    scramble = "";
    const token = ++loadToken;
    nameEl.textContent = c.name;
    groupEl.textContent = c.group;
    showAlg();
    statusSeg.set(titleCase(status(c)));
    statusLine.textContent = note || READY;
    picker.refresh(c.name);
    refreshResult();
    deal.then((d) => {
      if (token !== loadToken) return;
      scramble = d.scramble;
      scrambleEl.textContent = scramble;
      pic.innerHTML = diagramSvg(d.diagram);
      prepareNext();
    }, (err) => {
      if (token !== loadToken) return;
      scrambleEl.textContent = "(couldn't get a scramble - is the server running?)";
      pic.innerHTML = "";
      toast("Couldn't get a scramble from the server.");
      console.error(err);
    });
  }

  function showAlg() {
    if (hint.checked) {
      algEl.textContent = current ? current.alg : "";
      algEl.className = "case-alg";
    } else {
      algEl.textContent = "algorithm hidden";
      algEl.className = "case-alg hidden-alg";
    }
  }

  // ---- results ---------------------------------------------------------------
  function refreshResult() {
    if (!current) return;
    const times = store.caseTimes[mode][current.name];
    result.textContent = times && times.length ? resultBar(times) : "No times for this case yet.";
  }

  function refreshHistory() {
    const rows = store.recent[mode];
    if (!rows.length) {
      historySummary.textContent = "No times yet";
      historyList.replaceChildren();
      return;
    }
    const mean = rows.reduce((a, r) => a + r[1], 0) / rows.length;
    historySummary.textContent = `last ${rows.length}   mean ${fmt(mean)}`;
    historyList.replaceChildren(...rows.map((r) =>
      h("li", null, h("span", { text: r[0] || "?" }), h("span", { text: fmt(r[1]) }))));
  }

  const timer = new Timer(timerLabel, startBtn, {
    onNext: () => pickNextCase(),
    onStop(seconds) {
      if (!current) return;
      const name = current.name;
      // show it at once; the server's answer replaces the local guess
      const times = store.caseTimes[mode][name] || (store.caseTimes[mode][name] = []);
      times.unshift(seconds);
      times.length = Math.min(times.length, 12);
      store.recent[mode].unshift([name, seconds, ""]);
      store.recent[mode].length = Math.min(store.recent[mode].length, 40);
      refreshResult();
      refreshHistory();
      statusLine.textContent = `Saved  ${fmt(seconds)}  —  press SPACE for next case`;
      api.addTime({ mode, case: name, seconds, scramble }).then((r) => {
        store.applyTimes(mode, name, r);
        refreshResult();
        refreshHistory();
      });
    },
  });
  startBtn.onclick = () => timer.toggle();

  /** Removes the newest attempt in this mode (the top row of the history). */
  async function deleteLast() {
    const r = await api.deleteLast(mode);
    if (r && r.deleted) {
      store.applyTimes(mode, r.case, r);
      statusLine.textContent = "Last time deleted.";
      refreshResult();
      refreshHistory();
    }
  }

  // ---- keeping in step with the store ------------------------------------------
  function refreshSelection() {
    syncPickers();
    picker.refresh(current && current.name);
    if (current) statusSeg.set(titleCase(status(current)));
  }
  store.listen((m) => m === mode && refreshSelection());

  syncPickers();
  pickNextCase();
  refreshHistory();

  return {
    el,
    timer,
    selectCase,
    setSource,
    unpin,
    get state() { return { source, pinned, current, scramble, upcoming }; },
    onShow() {
      refreshSelection();
      if (!pinned && source !== "all" && (!current || !pool().includes(current))) pickNextCase();
      refreshHistory();
    },
    onHide: () => timer.reset(),
  };
}
