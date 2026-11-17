// The cases picked for practice, each case's learning status and the user's
// own groups, per mode: a port of SelectionStore in cube_timer_gui.py.
// Every change updates memory first (so the page repaints at once), then is
// saved through the API; listeners are told which mode changed.
// The sets are mutated in place, never rebound: screens keep references.

import { api, setWriteFailedHandler } from "./api.js";
import { SLOWEST_COUNT } from "./util.js";

export class Store {
  constructor(boot) {
    this.cases = {};        // mode -> [{name, group, alg, weight, diagram}]
    this.byName = {};       // mode -> {name: case}
    this.selected = {};     // mode -> Set of names
    this.statuses = {};     // mode -> Map name -> "learning" | "finished"
    this.custom = {};       // mode -> Map group name -> Set of names
    this.active = {};       // mode -> custom group being edited, or null
    this.caseTimes = {};    // mode -> {name: latest 12 times, newest first}
    this.recent = boot.recent;  // mode -> [[case, seconds, ts]], newest first
    this._listeners = [];
    for (const mode of ["oll", "pll"]) {
      this.cases[mode] = boot.cases[mode];
      this.byName[mode] = Object.fromEntries(boot.cases[mode].map((c) => [c.name, c]));
      this.selected[mode] = new Set();
      this.statuses[mode] = new Map();
      this.custom[mode] = new Map();
      this.active[mode] = null;
      this.caseTimes[mode] = boot.case_times[mode];
    }
    this._load(boot.state);
    setWriteFailedHandler(() => this.reload());
  }

  _load(state) {
    for (const mode of ["oll", "pll"]) {
      const s = state[mode];
      this.selected[mode].clear();
      for (const n of s.selected) this.selected[mode].add(n);
      this.statuses[mode].clear();
      for (const [n, st] of Object.entries(s.statuses)) this.statuses[mode].set(n, st);
      this.custom[mode].clear();
      for (const [g, names] of Object.entries(s.custom)) this.custom[mode].set(g, new Set(names));
      if (this.active[mode] !== null && !this.custom[mode].has(this.active[mode])) this.active[mode] = null;
    }
  }

  /** After a failed save: take the server's state as the truth again. */
  async reload() {
    try {
      this._load(await api.state());
      this._changed("oll");
      this._changed("pll");
    } catch { /* server gone; the toast already said so */ }
  }

  listen(fn) { this._listeners.push(fn); }
  _changed(mode) { for (const fn of this._listeners) fn(mode); }

  status(mode, name) { return this.statuses[mode].get(name) || "unlearned"; }

  set(mode, names) {
    const sel = this.selected[mode];
    const next = new Set(names);
    sel.clear();
    for (const n of next) sel.add(n);
    api.setSelected(mode, [...sel]);
    this._changed(mode);
  }

  toggle(mode, name) {
    const next = new Set(this.selected[mode]);
    next.has(name) ? next.delete(name) : next.add(name);
    this.set(mode, next);
  }

  /** Select the whole group, or clear it if it is already all selected. */
  toggleGroup(mode, group) {
    const names = this.cases[mode].filter((c) => c.group === group).map((c) => c.name);
    const sel = this.selected[mode];
    const all = names.every((n) => sel.has(n));
    const next = new Set(sel);
    for (const n of names) all ? next.delete(n) : next.add(n);
    this.set(mode, next);
  }

  /** Give every selected case the same status. Returns how many changed. */
  markSelected(mode, status) {
    const names = [...this.selected[mode]];
    if (!names.length) return 0;
    for (const n of names) {
      if (status === "unlearned") this.statuses[mode].delete(n);
      else this.statuses[mode].set(n, status);
    }
    api.setStatus(mode, names, status);
    this._changed(mode);
    return names.length;
  }

  setStatus(mode, name, status) {
    if (status === "unlearned") this.statuses[mode].delete(name);
    else this.statuses[mode].set(name, status);
    api.setStatus(mode, [name], status);
    this._changed(mode);
  }

  // --- the user's own groups ----------------------------------------
  // A loaded group becomes the active group: the selection is then a working
  // copy of it, and nothing changes in the group until saveActive().

  /** Create (or overwrite) a custom group; it becomes the active group. */
  saveGroup(mode, name, names) {
    this.custom[mode].set(name, new Set(names));
    this.active[mode] = name;
    api.saveGroup(mode, name, [...names]);
    this._changed(mode);
  }

  deleteGroup(mode, name) {
    this.custom[mode].delete(name);
    if (this.active[mode] === name) this.active[mode] = null;
    api.deleteGroup(mode, name);
    this._changed(mode);
  }

  /** Make a custom group the selection and start editing it. */
  loadGroup(mode, name) {
    this.active[mode] = name;
    this.set(mode, this.custom[mode].get(name) || []);
  }

  /** Cases added to or removed from the active group but not saved yet. */
  pendingChanges(mode) {
    const name = this.active[mode];
    if (name === null) return 0;
    const group = this.custom[mode].get(name) || new Set();
    const sel = this.selected[mode];
    let n = 0;
    for (const x of sel) if (!group.has(x)) n++;
    for (const x of group) if (!sel.has(x)) n++;
    return n;
  }

  saveActive(mode) {
    const name = this.active[mode];
    if (name !== null) this.saveGroup(mode, name, this.selected[mode]);
  }

  revertActive(mode) {
    const name = this.active[mode];
    if (name !== null) this.set(mode, this.custom[mode].get(name) || []);
  }

  /** Stop editing the group (the selection stays as it is). */
  closeActive(mode) {
    this.active[mode] = null;
    this._changed(mode);
  }

  /** {name: mean of its latest 5 times} (Database.recent_means). */
  recentMeans(mode) {
    const out = {};
    for (const [name, times] of Object.entries(this.caseTimes[mode])) {
      const t = times.slice(0, 5);
      if (t.length) out[name] = t.reduce((a, b) => a + b, 0) / t.length;
    }
    return out;
  }

  /** Names of the slowest cases by recent average (only cases with times). */
  slowest(mode) {
    const means = this.recentMeans(mode);
    return this.cases[mode]
      .filter((c) => c.name in means)
      .sort((a, b) => means[b.name] - means[a.name])
      .slice(0, SLOWEST_COUNT)
      .map((c) => c.name);
  }

  /** Custom groups sorted by name, case-insensitive. */
  groups(mode) {
    return [...this.custom[mode].entries()]
      .sort((a, b) => a[0].toLowerCase().localeCompare(b[0].toLowerCase()));
  }

  // --- times ----------------------------------------------------------
  /** Apply what the server returned after an attempt was added or deleted. */
  applyTimes(mode, caseName, result) {
    if (!result) return;
    this.recent[mode] = result.recent;
    if (caseName && result.case_times) {
      if (mode === "full") return;
      if (result.case_times.length) this.caseTimes[mode][caseName] = result.case_times;
      else delete this.caseTimes[mode][caseName];
    }
  }
}
