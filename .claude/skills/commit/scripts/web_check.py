"""Drive the web UI in headless Chrome against a temp copy of the database."""
import hashlib, os, shutil, sqlite3, sys, tempfile, threading, time
from pathlib import Path as _P
ROOT = str(_P(__file__).resolve().parents[4])   # the project folder
sys.path.insert(0, ROOT)
os.chdir(ROOT)
SHOTS = tempfile.mkdtemp(prefix="cube_web_shots_")
REAL = os.path.join(ROOT, "cube_times.db")
before = hashlib.md5(open(REAL, "rb").read()).hexdigest()
tmp = os.path.join(tempfile.mkdtemp(), "t.db"); shutil.copy(REAL, tmp)

import uvicorn, cube_web
from playwright.sync_api import sync_playwright

port = cube_web._free_port(8900)
server = uvicorn.Server(uvicorn.Config(cube_web.create_app(tmp), host="127.0.0.1", port=port, log_level="warning"))
threading.Thread(target=server.run, daemon=True).start()
while not server.started: time.sleep(0.02)
URL = f"http://127.0.0.1:{port}/"

def rows(mode):
    with sqlite3.connect(tmp) as c:
        return c.execute("SELECT COUNT(*) FROM times WHERE mode=?", (mode,)).fetchone()[0]

def rows_where(cond):
    with sqlite3.connect(tmp) as c:
        return c.execute(f"SELECT COUNT(*) FROM times WHERE {cond}").fetchone()[0]

def last_penalty(mode):
    with sqlite3.connect(tmp) as c:
        return c.execute("SELECT penalty FROM times WHERE mode=? ORDER BY id DESC LIMIT 1",
                         (mode,)).fetchone()[0]

results = []
def check(name, cond, detail=""): results.append((name, bool(cond), detail))
errors = []

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.on("pageerror", lambda e: errors.append(str(e)))

    t = time.perf_counter()
    page.goto(URL + "#full")
    page.wait_for_selector("section.screen.shown .scramble-box:not(:empty)")
    load_ms = (time.perf_counter() - t) * 1000
    nav = page.evaluate("""() => { const n = performance.getEntriesByType('navigation')[0];
        const fcp = performance.getEntriesByName('first-contentful-paint')[0];
        return {dcl: n.domContentLoadedEventEnd, load: n.loadEventEnd, fcp: fcp && fcp.startTime}; }""")
    check("first load", True, f"wall {load_ms:.0f} ms; DOMContentLoaded {nav['dcl']:.0f} ms; first paint {nav['fcp'] or 0:.0f} ms")
    page.wait_for_function("() => Object.keys(window.cubeApp.timings).length >= 6", timeout=5000)
    check("screen build times (ms)", True, str(page.evaluate("window.cubeApp.timings")))
    page.screenshot(path=os.path.join(SHOTS, "web_full.png"))

    # --- Full solve: space start / stop / next
    n0 = rows("full")
    page.keyboard.press("Space"); page.wait_for_timeout(350)
    check("full running", page.locator(".shown .timer.running").count() == 1)
    page.keyboard.press("Space")
    check("full stopped", page.locator(".shown .timer.stopped").count() == 1, page.inner_text(".shown .timer"))
    page.wait_for_timeout(200)
    check("full saved", rows("full") == n0 + 1)
    check("full result bar", "Last:" in page.inner_text(".shown .result-bar"))
    old = page.inner_text(".shown .scramble-box")
    page.keyboard.press("Space")
    check("full next scramble", page.inner_text(".shown .scramble-box") != old and page.locator(".shown .timer.running").count() == 0)
    page.click("text=Delete Last"); page.wait_for_timeout(200)
    check("full delete last", rows("full") == n0)

    # --- sessions: penalties, flags, delete any solve, new session
    answers = []
    on_dialog = lambda d: d.accept(answers.pop(0) if answers else "")
    page.on("dialog", on_dialog)
    for _ in range(2):
        page.keyboard.press("Space"); page.wait_for_timeout(120)
        page.keyboard.press("Space"); page.wait_for_timeout(250)
        page.keyboard.press("Space"); page.wait_for_timeout(50)
    page.click(".shown .last-solve button[data-act=dnf]"); page.wait_for_timeout(250)
    check("last solve DNF", last_penalty("full") == "dnf")
    check("history shows DNF", page.inner_text(".shown .history.solves li[data-id] .time") == "DNF")
    page.click(".shown .last-solve button[data-act='+2']"); page.wait_for_timeout(250)
    check("last solve +2", last_penalty("full") == "+2")
    page.locator(".shown .history.solves li[data-id]").nth(1).click()
    answers.append("check test")
    page.click(".shown .history.solves li.actions button[data-act=flag]"); page.wait_for_timeout(250)
    check("flag with note", rows_where("flagged=1 AND note='check test'") == 1)
    n1 = rows("full")
    page.locator(".shown .history.solves li[data-id]").first.click()
    page.click(".shown .history.solves li.actions button[data-act=delete]"); page.wait_for_timeout(250)
    check("delete a solve from the history", rows("full") == n1 - 1)
    all_n = page.evaluate("window.cubeApp.store.stats.full.all.count")
    old_n = page.evaluate("window.cubeApp.store.stats.full.session_no")
    answers.append("Web Check Cube")
    page.click(".shown .session-picker button:has-text('New')"); page.wait_for_timeout(300)
    st = page.evaluate("window.cubeApp.store.stats.full")
    check("new named session", st["session"]["count"] == 0 and st["all"]["count"] == all_n
          and st["session_name"] == "Web Check Cube"
          and page.locator(".shown .history.solves li[data-id]").count() == 0)
    check("picker shows the new session",
          "Web Check Cube" in page.locator(".shown .session-select option:checked").inner_text())
    page.select_option(".shown .session-select", str(old_n)); page.wait_for_timeout(300)
    st = page.evaluate("window.cubeApp.store.stats.full")
    check("switch back to the earlier session", st["session_no"] == old_n
          and page.locator(".shown .history.solves li[data-id]").count() == st["session"]["count"] > 0)
    page.screenshot(path=os.path.join(SHOTS, "web_full_session.png"))
    page.remove_listener("dialog", on_dialog)

    # --- screen switching speed
    sw = page.evaluate("""async () => { const out = {};
        for (const s of ['oll','pll','cases','stats','full','oll']) {
            const t = performance.now(); window.cubeApp.show(s);
            await new Promise(r => requestAnimationFrame(() => setTimeout(r)));
            out[s] = +(performance.now() - t).toFixed(1); }
        return out; }""")
    check("screen switch incl. paint (ms)", max(sw.values()) < 100, str(sw))

    # --- OLL trainer
    page.goto(URL + "#oll"); page.wait_for_selector(".shown .case-scramble:not(:empty)")
    oll = ".shown"
    SRC = "select[title='Where cases come from']"   # the From menu, not the session picker
    name = page.inner_text(f"{oll} .case-name")
    check("oll case shown", name.startswith("OLL"), name)
    check("oll picture", page.locator(f"{oll} .case-head svg rect").count() >= 9)
    page.wait_for_timeout(200)   # let the next deal prefetch
    k0 = rows("oll")
    page.keyboard.press("Space"); page.wait_for_timeout(200); page.keyboard.press("Space")
    page.wait_for_timeout(200)
    check("oll attempt saved", rows("oll") == k0 + 1)
    check("oll history", page.locator(f"{oll} .history li").count() >= 1)
    old_scr = page.inner_text(f"{oll} .case-scramble")
    ms = page.evaluate("""() => new Promise(res => {
        const el = document.querySelector('.shown .case-scramble'); const before = el.textContent;
        const t = performance.now();
        const obs = new MutationObserver(() => { if (el.textContent !== before) { obs.disconnect(); res(performance.now() - t); } });
        obs.observe(el, {childList: true, characterData: true, subtree: true});
        window.dispatchEvent(new KeyboardEvent('keydown', {code: 'Space', key: ' '}));
    })""")
    check("next case, Space -> new scramble shown (ms)", ms < 30, f"{ms:.1f}")
    page.screenshot(path=os.path.join(SHOTS, "web_oll.png"))

    # sources
    opts = page.eval_on_selector_all(f"{oll} {SRC} option", "els => els.map(e => e.value)")
    bad = []
    for v in opts:
        page.select_option(f"{oll} {SRC}", v); page.wait_for_timeout(30)
        st = page.evaluate("(() => { const s = window.cubeApp.screens.oll.state; return [s.source, s.current && s.current.name]; })()")
        if st[0] != v: bad.append(v)
    check("oll every source selectable", not bad, f"{len(opts)} sources; bad={bad}")
    page.select_option(f"{oll} {SRC}", "all")

    # picker click / double-click
    tile = page.locator(f"{oll} .tile[data-name='OLL 21']")
    sel_before = page.evaluate("[...window.cubeApp.store.selected.oll].includes('OLL 21')")
    tile.click(); page.wait_for_timeout(50)
    sel_after = page.evaluate("[...window.cubeApp.store.selected.oll].includes('OLL 21')")
    check("picker click toggles", sel_after != sel_before)
    check("picker click -> source selected", page.evaluate("window.cubeApp.screens.oll.state.source") == "selected")
    tile.click(); page.wait_for_timeout(50)   # back
    page.select_option(f"{oll} {SRC}", "all")
    tile.dblclick(); page.wait_for_timeout(150)
    st = page.evaluate("(() => { const s = window.cubeApp.screens.oll.state; return [s.source, s.pinned && s.pinned.name, s.current.name]; })()")
    check("picker dblclick pins", st[1] == "OLL 21" and st[2] == "OLL 21", str(st))
    check("dblclick leaves selection & source", page.evaluate("[...window.cubeApp.store.selected.oll].includes('OLL 21')") == sel_before and st[0] == "all")
    page.keyboard.press("Space"); page.keyboard.press("Space"); page.keyboard.press("Space"); page.wait_for_timeout(100)
    check("pinned case repeats", page.inner_text(f"{oll} .case-name") == "OLL 21")
    page.click(f"{oll} .pin-bar button")
    check("unpinned", page.evaluate("window.cubeApp.screens.oll.state.pinned") is None)

    # group tick, mark selected, save group (prompt), edit cycle (confirm)
    page.click(f"{oll} .tools.compact >> text=None")
    page.locator(f"{oll} .group-head .tick").first.click()
    n_dot = page.evaluate("window.cubeApp.store.selected.oll.size")
    check("group tick selects group", n_dot == 8, str(n_dot))
    page.click(f"{oll} .tools.compact >> text=Learning")
    check("mark selected learning", page.evaluate("[...window.cubeApp.store.statuses.oll.values()].filter(s=>s==='learning').length") >= 8)
    page.click(f"{oll} .tools.compact >> text=Unlearned")
    page.once("dialog", lambda d: d.accept("Smoke Dots"))
    page.click(f"{oll} .tools.compact >> text=Save as group…"); page.wait_for_timeout(150)
    check("group saved (UI)", page.locator(f"{oll} .chip >> text=★ Smoke Dots (8)").count() == 1)
    tile.click(); page.wait_for_timeout(50)
    check("edit bar shows pending", "1 unsaved" in page.inner_text(f"{oll} .edit-bar"))
    page.once("dialog", lambda d: d.accept())
    page.click(f"{oll} .edit-bar >> text=Done"); page.wait_for_timeout(50)
    check("done closes edit", page.locator(f"{oll} .edit-bar").count() == 0)
    with sqlite3.connect(tmp) as c:
        g = c.execute("SELECT COUNT(*) FROM custom_groups WHERE group_name='Smoke Dots'").fetchone()[0]
    check("group in DB", g == 8, str(g))
    page.select_option(f"{oll} {SRC}", "custom:Smoke Dots"); page.wait_for_timeout(50)
    cur = page.evaluate("window.cubeApp.screens.oll.state.current.group")
    check("custom source deals from group", cur == "Dot", cur)
    page.once("dialog", lambda d: d.accept())
    page.click(f"{oll} .chip:has-text('Smoke Dots') .del"); page.wait_for_timeout(150)
    with sqlite3.connect(tmp) as c:
        g = c.execute("SELECT COUNT(*) FROM custom_groups WHERE group_name='Smoke Dots'").fetchone()[0]
    check("group deleted", g == 0)
    page.click(f"{oll} .tools.compact >> text=None")

    # status segment for current case
    page.click(f"{oll} .seg >> text=Finished"); page.wait_for_timeout(100)
    cname = page.inner_text(f"{oll} .case-name")
    with sqlite3.connect(tmp) as c:
        s = c.execute("SELECT status FROM case_status WHERE mode='oll' AND case_name=?", (cname,)).fetchone()
    check("status segment saves", s and s[0] == "finished")
    page.click(f"{oll} .seg >> text=Unlearned"); page.wait_for_timeout(100)

    # hide algorithm
    page.click(f"{oll} label.switch")
    check("hide algorithm", page.inner_text(f"{oll} .case-alg") == "algorithm hidden")
    page.click(f"{oll} label.switch")

    # side tabs
    page.click(f"{oll} .side .seg >> text=History")
    check("history tab", page.locator(f"{oll} .history").is_visible())
    page.click(f"{oll} .side .seg >> text=Cases")

    # --- PLL picture with arrows
    page.goto(URL + "#pll"); page.wait_for_selector(".shown .case-scramble:not(:empty)")
    check("pll arrows drawn", page.locator(".shown .case-head svg polygon").count() >= 1)
    page.screenshot(path=os.path.join(SHOTS, "web_pll.png"))

    # --- gallery
    page.goto(URL + "#cases"); page.wait_for_selector(".shown .card")
    check("gallery cards", page.locator(".shown .card").count() == 78)
    card = page.locator(".shown .card[data-name='OLL 45']")
    was = page.evaluate("window.cubeApp.store.selected.oll.has('OLL 45')")
    card.locator(".name").click(); page.wait_for_timeout(50)
    check("gallery click selects", page.evaluate("window.cubeApp.store.selected.oll.has('OLL 45')") != was)
    check("card shows selected", ("sel" in card.get_attribute("class")) != was)
    card.locator(".name").click()
    card.locator(".status").click(); page.wait_for_timeout(50)
    check("status cycles", card.locator(".status").inner_text() == "LEARNING")
    card.locator(".status").click(); card.locator(".status").click(); page.wait_for_timeout(50)
    check("status cycles back", card.locator(".status").inner_text() == "UNLEARNED")
    page.screenshot(path=os.path.join(SHOTS, "web_gallery.png"))
    card.locator(".name").dblclick(); page.wait_for_timeout(200)
    st = page.evaluate("(() => { const s = window.cubeApp.screens.oll.state; return [location.hash, s.pinned && s.pinned.name]; })()")
    check("gallery dblclick opens trainer pinned", st == ["#oll", "OLL 45"], str(st))
    check("gallery dblclick keeps selection", page.evaluate("window.cubeApp.store.selected.oll.has('OLL 45')") == was)

    # --- stats
    page.goto(URL + "#stats"); page.wait_for_selector(".shown table.stat-block")
    page.click(".shown .stats-filters button[data-key=all]"); page.wait_for_timeout(300)
    check("stats all-time solves", page.locator(".shown table.solves-table tbody tr").count() >= 1)
    page.check(".shown .stats-filters input[type=checkbox]"); page.wait_for_timeout(300)
    flagged = page.locator(".shown table.solves-table tbody tr").count()
    check("stats flagged only", flagged == rows_where("flagged=1 AND mode='full'"), flagged)
    page.uncheck(".shown .stats-filters input[type=checkbox]"); page.wait_for_timeout(300)
    page.click(".shown .tabs button[data-key=oll]"); page.wait_for_timeout(150)
    page.click(".shown .stats-filters button[data-key=cases]"); page.wait_for_timeout(300)
    check("stats oll table", page.locator(".shown table.stats tbody tr").count() == 57)
    page.click(".shown .tabs button[data-key=pll]"); page.wait_for_timeout(300)
    check("stats pll table", page.locator(".shown table.stats tbody tr").count() == 21)
    page.screenshot(path=os.path.join(SHOTS, "web_stats.png"))

    # narrow window: no horizontal scroll
    page.set_viewport_size({"width": 390, "height": 800})
    page.goto(URL + "#oll"); page.wait_for_selector(".shown .case-scramble:not(:empty)")
    check("phone width: no horizontal scroll", page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"))
    browser.close()

server.should_exit = True
time.sleep(0.5)
check("no browser errors", not errors, "; ".join(errors[:5]))
check("real DB untouched", hashlib.md5(open(REAL, "rb").read()).hexdigest() == before)
fails = [r for r in results if not r[1]]
for name, ok, d in results: print(("PASS " if ok else "FAIL ") + name + (f"  [{d}]" if d else ""))
print(f"\n{len(results)-len(fails)}/{len(results)} passed; screenshots in {SHOTS}")
sys.exit(1 if fails else 0)
