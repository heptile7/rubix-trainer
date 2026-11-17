// Selection widgets shared by the trainers' side column and the gallery:
// ports of SelectionTools, MyGroups, GroupHeader and CasePicker.
// Each builds its DOM once; refresh() only flips classes and text.

import { h, STATUSES, SLOWEST_COUNT, titleCase, groupOrder } from "./util.js";

/** All / None / Slowest 10, Mark selected as …, Save as group…, count. */
export function selectionTools(store, mode, { compact = false, onEdit = null } = {}) {
  const names = store.cases[mode].map((c) => c.name);
  const count = h("span.count");

  const run = (fn, edits = true) => () => {
    const message = fn();
    if (edits && onEdit) onEdit();
    if (message) count.textContent = message;
  };
  const button = (text, fn, edits, cls = "") =>
    h(`button.btn.small${cls}`, { type: "button", text, onclick: run(fn, edits) });

  const el = h(compact ? "div.tools.compact" : "div.tools", null,
    button("All", () => store.set(mode, names)),
    button("None", () => store.set(mode, [])),
    button(`Slowest ${SLOWEST_COUNT}`, () => {
      const slow = store.slowest(mode);
      if (!slow.length) return "no times yet";
      store.set(mode, slow);
    }),
    h("span.lbl", { text: "Mark selected as:" }),
    ...STATUSES.map((s) => button(titleCase(s), () => {
      const n = store.markSelected(mode, s);
      return n ? `${n} marked` : "select cases first";
    }, false, s === "unlearned" ? "" : `.${s}`)),
    button("Save as group…", () => {
      const sel = store.selected[mode];
      if (!sel.size) return "select cases first";
      const name = (prompt(`Name for this group of ${sel.size} cases\n(an existing name is replaced):`) || "")
        .trim().slice(0, 30);
      if (!name) return null;
      store.saveGroup(mode, name, sel);
      return "group saved";
    }, false, ".save"),
    count,
  );
  const refresh = () => { count.textContent = `${store.selected[mode].size} selected`; };
  refresh();
  store.listen((m) => m === mode && refresh());
  return el;
}

/** The user's saved groups: click loads one as the selection, ✕ deletes it. */
export function myGroups(store, mode, onEdit = null) {
  const el = h("div.mygroups");

  const load = (name) => {
    const active = store.active[mode];
    const pending = store.pendingChanges(mode);
    if (active !== null && active !== name && pending &&
        !confirm(`Discard ${pending} unsaved change(s) to “${active}” and open “${name}”?`)) return;
    store.loadGroup(mode, name);
    if (onEdit) onEdit();
  };
  const remove = (name) => {
    if (confirm(`Delete the group “${name}”? The cases themselves are kept.`)) store.deleteGroup(mode, name);
  };

  function editBar(name) {
    const pending = store.pendingChanges(mode);
    const btn = (text, fn, enabled, cls = "") =>
      h(`button.btn.small${cls}`, { type: "button", text, disabled: !enabled, onclick: fn });
    return h("div.edit-bar", null,
      h(pending ? "div.what.pending" : "div.what",
        { text: `Editing ★ ${name}  •  ${pending ? `${pending} unsaved` : "saved"}` }),
      h("div.row", { style: "justify-content:flex-start;gap:4px" },
        btn("Save", () => store.saveActive(mode), pending, ".primary"),
        btn("Revert", () => { store.revertActive(mode); if (onEdit) onEdit(); }, pending),
        btn("Done", () => {
          const n = store.pendingChanges(mode);
          if (n && !confirm(`Stop editing “${store.active[mode]}” without saving ${n} change(s)?`)) return;
          store.closeActive(mode);
        }, true)));
  }

  function refresh() {
    const groups = store.groups(mode);
    const active = store.active[mode];
    const kids = [h("div.title", { text: "My groups" })];
    if (!groups.length) {
      kids.push(h("div.empty", { text: "Select cases, then Save as group…" }));
    } else {
      if (active !== null) kids.push(editBar(active));
      kids.push(h("div.chips", null, ...groups.map(([name, members]) =>
        h(name === active ? "div.chip.on" : "div.chip", null,
          h("button.load", { type: "button", title: name, text: `★ ${name} (${members.size})`,
                             onclick: () => load(name) }),
          h("button.del", { type: "button", title: "Delete group", text: "✕",
                            onclick: () => remove(name) })))));
    }
    el.replaceChildren(...kids);
  }
  refresh();
  store.listen((m) => m === mode && refresh());
  return el;
}

/** '▾ Dot  (3/8)   ☑' - the tick selects or clears the group, the arrow folds it. */
export function groupHeader(group, onTick, onFold = null) {
  const name = h("span.name", { text: group });
  const tick = h("span.tick", { text: "☐", title: "Select / clear this group", onclick: () => onTick(group) });
  const el = h("div.group-head");
  if (onFold) {
    let open = true;
    const fold = h("span.fold", { text: "▾" });
    const toggle = () => { open = !open; fold.textContent = open ? "▾" : "▸"; onFold(group, open); };
    fold.onclick = name.onclick = toggle;
    el.append(fold);
  }
  el.append(name, tick);
  let last = "";
  return {
    el,
    show(picked, total) {
      const key = `${picked}/${total}`;
      if (key === last) return;
      last = key;
      name.textContent = `${group}  (${picked}/${total})`;
      tick.textContent = picked === total ? "☑" : picked === 0 ? "☐" : "◩";
      tick.className = "tick" + (picked === total ? " all" : picked ? " some" : "");
    },
  };
}

/**
 * Mini pictures of every case, grouped by shape, with My groups on top.
 * Click toggles a case, double-click pins it, hovering reports it.
 * One set of listeners on the container handles every tile.
 */
export function casePicker(store, mode, { onToggle, onToggleGroup, onPin, onHover, onEdit }) {
  const cases = store.cases[mode];
  const el = h("div.scroll.picker");
  el.append(myGroups(store, mode, onEdit));

  const tiles = new Map();     // name -> tile element
  const headers = [];          // [header, member names]
  for (const group of groupOrder(cases)) {
    const members = cases.filter((c) => c.group === group);
    const body = h("div.group-body");
    const header = groupHeader(group, onToggleGroup, (g, open) => body.classList.toggle("folded", !open));
    const grid = h("div.tiles");
    for (const c of members) {
      const tile = h("div.tile", { "data-name": c.name, title: c.name });
      tile.innerHTML = c.svg + '<div class="bar"></div>';
      tiles.set(c.name, tile);
      grid.append(tile);
    }
    body.append(grid);
    el.append(header.el, body);
    headers.push([header, members.map((c) => c.name)]);
  }

  const caseOf = (e) => {
    const tile = e.target.closest(".tile");
    return tile ? store.byName[mode][tile.dataset.name] : null;
  };
  // Browsers send click, click, dblclick: the second click is ignored, and
  // the double-click handler undoes the first one's toggle (see onPin).
  el.addEventListener("click", (e) => { const c = caseOf(e); if (c && e.detail < 2) onToggle(c); });
  el.addEventListener("dblclick", (e) => { const c = caseOf(e); if (c) onPin(c); });
  let hovered = null;
  el.addEventListener("mouseover", (e) => {
    const c = caseOf(e);
    if (c !== hovered) onHover(hovered = c);
  });
  el.addEventListener("mouseleave", () => onHover(hovered = null));

  function refresh(current = null) {
    const sel = store.selected[mode];
    for (const [name, tile] of tiles) {
      const status = store.status(mode, name);
      tile.className = "tile" + (sel.has(name) ? " sel" : "") + (name === current ? " cur" : "") +
                       (status === "unlearned" ? "" : ` st-${status}`);
    }
    for (const [header, names] of headers) header.show(names.filter((n) => sel.has(n)).length, names.length);
  }
  return { el, refresh };
}
