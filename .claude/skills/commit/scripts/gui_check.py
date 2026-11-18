"""End-to-end smoke test of the Cube Timer GUI against a temp copy of the DB."""
import os, shutil, sys, tempfile, time, traceback, hashlib
from pathlib import Path as _P
ROOT = str(_P(__file__).resolve().parents[4])   # the project folder
sys.path.insert(0, ROOT)
os.chdir(ROOT)

REAL_DB = os.path.join(ROOT, "cube_times.db")
before = hashlib.md5(open(REAL_DB, "rb").read()).hexdigest()
tmp = os.path.join(tempfile.mkdtemp(), "cube_times.db")
shutil.copy(REAL_DB, tmp)

import cube_timer as ct
import cube_timer_gui as g
RealDB = g.Database
g.Database = lambda path: RealDB(tmp)

errors = []
results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))

app = g.CubeTimerApp()
app.root.report_callback_exception = lambda *e: errors.append("".join(traceback.format_exception(*e)))
def pump(n=15):
    for _ in range(n):
        app.root.update(); time.sleep(0.01)

pump()
# --- every screen opens ---
for name in ["full", "oll", "pll", "cases", "stats", "full"]:
    t = time.perf_counter()
    app.show_screen(name); pump()
    check(f"open {name}", app.screen(name).winfo_ismapped(), f"{time.perf_counter()-t:.2f}s")

# --- full solve: start, stop, record ---
db = app.db
n0 = len(db.get("full", limit=10000))
full = app.screen("full"); app.show_screen("full"); pump()
full.timer_toggle(); pump(); time.sleep(0.3); pump()
check("full running", full._state == "running")
full.timer_toggle(); pump()
check("full stopped", full._state == "stopped", full.timer_label.cget("text"))
check("full time saved", len(db.get("full", limit=10000)) == n0 + 1)
full.timer_toggle(); pump()
check("full back to idle", full._state == "idle")

# --- OLL / PLL trainers ---
for mode in ("oll", "pll"):
    s = app.screen(mode); app.show_screen(mode); pump()
    check(f"{mode} has case", s._current_case is not None,
          s._current_case and s._current_case["name"])
    k0 = len(db.get(mode, limit=10000))
    s.timer_toggle(); pump(); time.sleep(0.2); s.timer_toggle(); pump()
    rows = db.get(mode, limit=10000)
    check(f"{mode} attempt saved", len(rows) == k0 + 1)
    s.timer_toggle(); pump()
    # every source in the From menu deals a case from its pool (or nothing if empty)
    for key, label in s._source_options():
        s.set_source(key); pump(3)
        pool = [c["name"] for c in s._pool()]
        cur = s._current_case and s._current_case["name"]
        check(f"{mode} source {key}", (not pool) or cur in pool, f"pool={len(pool)} cur={cur}")
    s.set_source("all"); pump()
    # pin / unpin
    case = s.cases[3]
    s.select_case(case); pump()
    for _ in range(3):
        s.timer_toggle(); s.timer_toggle(); s.timer_toggle(); pump(2)
    check(f"{mode} pin holds", s._current_case["name"] == case["name"])
    s.unpin(); pump()
    check(f"{mode} unpinned", s._pinned is None)
    # selection store
    st = app.store
    st.set(mode, set()); pump()
    st.toggle(mode, case["name"]); pump()
    check(f"{mode} toggle", st.selected[mode] == {case["name"]})
    st.toggle_group(mode, case["group"]); pump()
    grp = {c["name"] for c in s.cases if c["group"] == case["group"]}
    check(f"{mode} toggle_group", grp <= st.selected[mode] or not (grp & st.selected[mode]),
          f"{len(st.selected[mode])} selected")
    st.set(mode, grp); st.mark_selected(mode, "learning"); pump()
    check(f"{mode} mark learning", all(st.status(mode, n) == "learning" for n in grp))
    st.mark_selected(mode, "unlearned"); pump()
    st.save_group(mode, "SmokeTest", grp); pump()
    check(f"{mode} save group", "SmokeTest" in st.custom[mode])
    s.set_source("custom:SmokeTest"); pump()
    check(f"{mode} custom source", s._current_case["name"] in grp)
    st.load_group(mode, "SmokeTest"); st.toggle(mode, case["name"]); pump()
    check(f"{mode} pending", bool(st.pending_changes(mode)))
    st.revert_active(mode); st.close_active(mode)
    st.delete_group(mode, "SmokeTest"); pump()
    check(f"{mode} delete group", "SmokeTest" not in st.custom[mode])

# --- gallery double-click opens trainer pinned ---
app.show_screen("cases"); pump()
case = ct.PLL_CASES[5]
app._open_case("pll", case); pump()
check("gallery open pins", app.screen("pll")._pinned is case, app._active_screen)
app.show_screen("stats"); pump(30)
check("stats after records", app.screen("stats").winfo_ismapped())

# --- sessions: penalty / flag / delete / new session (dialogs replaced) ---
full = app.screen("full"); app.show_screen("full"); pump()
for _ in range(2):
    full.timer_toggle(); pump(3); time.sleep(0.12); full.timer_toggle(); pump(3); full.timer_toggle(); pump(3)
newest = db.solves("full", "session", limit=1)[0][0]
full.last_bar.buttons["dnf"].invoke(); pump()
check("last solve DNF", db.solve(newest)[4] == "dnf")
full.last_bar.buttons["+2"].invoke(); pump()
check("last solve +2", db.solve(newest)[4] == "+2")
panel = full.session
second = panel._rows[1][0]
panel.select(second); pump()
panel.actions.ask_note = lambda prompt: "gui check"
panel.buttons.buttons["flag"].invoke(); pump()
check("flag with note", db.solve(second)[5:7] == (1, "gui check"))
panel.actions.confirm = lambda msg: True
panel.buttons.buttons["delete"].invoke(); pump()
check("delete selected solve", db.solve(second) is None)
all_n = db.stats("full")["count"]
panel.confirm = lambda msg: True
panel.new_session(); pump()
check("new session", db.stats("full", "session")["count"] == 0 and db.stats("full")["count"] == all_n
      and not panel._rows)
st = app.screen("stats"); app.show_screen("stats"); pump()
st._set(scope="all"); pump()
check("stats all-time rows", len(st._rows) >= 1)

# resize: layouts reflow without error
app.root.geometry("1600x1000"); app.show_screen("cases"); pump(40)
app.root.geometry("1000x660"); app.show_screen("oll"); pump(40)

app._on_close()
after = hashlib.md5(open(REAL_DB, "rb").read()).hexdigest()
check("real DB untouched", before == after)

# --- data layer ---
check("fmt", ct.fmt(61.234) in ("1:01.23",), ct.fmt(61.234))
check("calc_ao5", ct.calc_ao([1, 2, 3, 4, 100], 5) is not None, ct.calc_ao([1,2,3,4,100],5))
check("scramble len", len(ct.generate_scramble().split()) >= 15, ct.generate_scramble())
check("setup_scramble", all(ct.setup_scramble(c) for c in ct.OLL_CASES + ct.PLL_CASES))

fails = [r for r in results if not r[1]]
for name, ok, d in results:
    print(("PASS " if ok else "FAIL ") + name + (f"  [{d}]" if d else ""))
print(f"\n{len(results)-len(fails)}/{len(results)} passed, {len(errors)} Tk callback errors")
for e in errors: print(e)
sys.exit(1 if fails or errors else 0)
