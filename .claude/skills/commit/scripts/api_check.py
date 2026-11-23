"""API tests for cube_web.py against a temporary copy of the database."""
import hashlib, json, os, re, shutil, sys, tempfile, time
from pathlib import Path as _P
ROOT = str(_P(__file__).resolve().parents[4])   # the project folder
sys.path.insert(0, ROOT)
os.chdir(ROOT)
REAL = os.path.join(ROOT, "cube_times.db")
before = hashlib.md5(open(REAL, "rb").read()).hexdigest()
tmp = os.path.join(tempfile.mkdtemp(), "t.db"); shutil.copy(REAL, tmp)

from fastapi.testclient import TestClient
import cube_web
from cube_diagram import case_diagram, state_diagram, scramble_state, _apply, _solved, _parse
from cube_timer import OLL_CASES, PLL_CASES

results = []
def check(name, cond, detail=""): results.append((name, bool(cond), detail))

t = time.perf_counter()
app = cube_web.create_app(tmp)
check("create_app time", True, f"{time.perf_counter()-t:.2f}s")
with TestClient(app) as c:
    t = time.perf_counter(); r = c.get("/"); dt = time.perf_counter() - t
    check("index 200", r.status_code == 200, f"{len(r.content)//1024} KB in {dt*1000:.0f} ms")
    m = re.search(r'<script id="boot" type="application/json">(.*?)</script>', r.text, re.S)
    boot = json.loads(m.group(1))
    check("boot oll 57", len(boot["cases"]["oll"]) == 57)
    check("boot pll 21", len(boot["cases"]["pll"]) == 21)
    check("boot diagrams", all(len(x["diagram"]["top"]) == 9 for m_ in ("oll", "pll") for x in boot["cases"][m_]))
    check("pll arrows", all(x["diagram"]["perm"] and x["diagram"]["arrows"] for x in boot["cases"]["pll"]))
    r = c.get("/", headers={"Accept-Encoding": "gzip"})
    check("gzip", r.headers.get("content-encoding") == "gzip")
    for f in ["style.css", "js/app.js", "js/trainer.js"]:
        r = c.get("/" + f); check(f"static {f}", r.status_code == 200 and "etag" in r.headers, r.headers.get("cache-control"))
        r2 = c.get("/" + f, headers={"If-None-Match": r.headers["etag"]})
        check(f"304 {f}", r2.status_code == 304)

    # every case: scramble + (U turn) + the case's algorithm solves it
    # (PLL: whole cube, up to a final U turn; OLL: top face and first two layers).
    # Colours are compared with the centres, since some algorithms rotate the cube.
    AUF = ["", "U", "U2", "U'"]
    def faces_ok(state, only_top_and_f2l):
        centre = {f: col for pos, f, col, _ in state if sum(map(abs, pos)) == 1}
        up = next(f for f, col in centre.items() if col == "#f6d90b")
        for pos, f, col, _ in state:
            in_top = sum(a * b for a, b in zip(pos, up)) == 1
            if only_top_and_f2l and in_top and f != up:
                continue
            if col != centre[f]:
                return False
        return True
    bad = []
    t = time.perf_counter(); n = 0; dt_deal = 0
    for mode, cases in (("oll", OLL_CASES), ("pll", PLL_CASES)):
        for case in cases:
            t1 = time.perf_counter()
            d = c.get(f"/api/deal/{mode}/{case['name']}").json(); n += 1
            dt_deal += time.perf_counter() - t1
            ok = any(faces_ok(scramble_state(" ".join(filter(None, [d["scramble"], pre, case["alg"], post]))),
                              mode == "oll")
                     for pre in AUF for post in (AUF if mode == "pll" else [""]))
            # the picture sent is the scrambled cube's top layer
            ok = ok and d["diagram"] == cube_web.diagram_json(state_diagram(scramble_state(d["scramble"])))
            if not ok: bad.append(case["name"])
    check("every deal sets up its case", not bad, f"{n} deals, {dt_deal/n*1000:.1f} ms each; bad={bad}")
    check("deal unknown case 404", c.get("/api/deal/oll/Nope").status_code == 404)

    # times round trip
    r = c.post("/api/times", json={"mode": "oll", "case": "OLL 21", "seconds": 3.21, "scramble": "R U"}).json()
    top = r["recent"][0]
    check("add time", (top["case"], top["seconds"], top["id"]) == ("OLL 21", 3.21, r["id"])
          and r["case_times"][0] == 3.21 and r["stats"]["session"]["count"] >= 1)
    oll_id = r["id"]
    r = c.post("/api/times", json={"mode": "full", "seconds": 15.5, "scramble": "R"}).json()
    check("add full", r["recent"][0]["seconds"] == 15.5)

    # penalties, flags, single deletes and sessions
    r = c.put(f"/api/solves/{oll_id}/penalty", json={"penalty": "+2"}).json()
    check("+2 penalty", r["recent"][0]["penalty"] == "+2" and r["case_times"][0] == 5.21)
    r = c.put(f"/api/solves/{oll_id}/penalty", json={"penalty": "dnf"}).json()
    check("DNF left out of case times", r["stats"]["session"]["dnf"] >= 1
          and 3.21 not in r["case_times"] and 5.21 not in r["case_times"])
    check("bad penalty 400", c.put(f"/api/solves/{oll_id}/penalty", json={"penalty": "x"}).status_code == 400)
    r = c.put(f"/api/solves/{oll_id}/flag", json={"flagged": True, "note": " lucky "}).json()
    check("flag with note", r["recent"][0]["flagged"] and r["recent"][0]["note"] == "lucky")
    t = c.get("/api/solves/oll?scope=all&flagged=true").json()
    check("flagged-only list", [x["id"] for x in t["rows"]] == [oll_id] and t["rows"][0]["time"] == "DNF")
    for s in (10, 11, 12, 13):
        c.post("/api/times", json={"mode": "full", "seconds": s})
    st = c.get("/api/stats/full").json()
    check("session ao5", st["session"]["ao5"] is not None, st["session"]["ao5"])
    check("stats: std dev, ao3 and best averages", all(k in st["session"] for k in
          ("sd", "ao3", "best_ao3", "best_ao5", "best_ao12", "best_ao50", "best_ao100"))
          and st["session"]["sd"] is not None and st["session"]["ao3"] is not None, sorted(st["session"]))
    t = c.get("/api/solves/full?scope=session").json()
    check("solve rows carry ao3", all("ao3" in x for x in t["rows"]) and t["rows"][0]["ao3"] is not None)
    all_before = st["all"]["count"]
    old_n = st["session_no"]
    r = c.post("/api/session/full", json={"name": "  GAN 12 "}).json()
    new_n = r["stats"]["session_no"]
    check("new named session", r["stats"]["session"]["count"] == 0 and r["recent"] == []
          and r["stats"]["all"]["count"] == all_before and new_n > old_n
          and r["stats"]["session_name"] == "GAN 12"
          and {"n": new_n, "name": "GAN 12", "count": 0, "last": None} in r["stats"]["sessions"])
    c.post("/api/times", json={"mode": "full", "seconds": 20.0})
    r = c.put(f"/api/session/full/{old_n}").json()
    check("select earlier session", r["stats"]["session_no"] == old_n
          and r["stats"]["session"]["count"] == st["session"]["count"]
          and all(x["seconds"] != 20.0 for x in r["recent"]))
    r = c.delete("/api/times/last/full").json()
    left = {s["n"]: s["count"] for s in r["stats"]["sessions"]}
    check("delete last stays in the selected session", r["deleted"] and left[new_n] == 1
          and left[old_n] == st["session"]["count"] - 1)
    r = c.patch(f"/api/session/full/{new_n}", json={"name": "MoYu OH"}).json()
    check("rename session", any(s["n"] == new_n and s["name"] == "MoYu OH" for s in r["stats"]["sessions"]))
    check("unknown session 404", c.put("/api/session/full/9999").status_code == 404)
    r = c.delete(f"/api/session/full/{new_n}").json()
    check("delete session and its solves", all(s["n"] != new_n for s in r["stats"]["sessions"])
          and r["stats"]["all"]["count"] == all_before - 1)
    only = c.get("/api/stats/pll").json()
    if len(only["sessions"]) == 1:
        check("last session can't be deleted",
              c.delete(f"/api/session/pll/{only['session_no']}").status_code == 400)
    t = c.get("/api/solves/oll?scope=all&case=OLL%2021&limit=5000").json()
    check("solves for one case", t["rows"] and all(x["case"] == "OLL 21" for x in t["rows"]))
    check("unknown case 400", c.get("/api/solves/oll?scope=all&case=Nope").status_code == 400)
    # settings and attempts recorded with an inspection penalty
    s0 = c.get("/api/settings").json()
    check("default settings", s0["hold_to_start"] is True and s0["inspection.full"] is False
          and s0["inspection_seconds.oll"] == 8, s0)
    s1 = c.put("/api/settings", json={"values": {"inspection.full": True, "hold_ms": 550}}).json()
    check("save settings", s1["inspection.full"] is True and s1["hold_ms"] == 550
          and c.get("/api/bootstrap").json()["settings"]["hold_ms"] == 550)
    check("bad setting 400", c.put("/api/settings", json={"values": {"hold_ms": 7}}).status_code == 400
          and c.put("/api/settings", json={"values": {"nope": 1}}).status_code == 400
          and c.put("/api/settings", json={"values": {"inspection.oll": "yes"}}).status_code == 400)
    r = c.post("/api/times", json={"mode": "full", "seconds": 12.0, "penalty": "+2"}).json()
    check("attempt with +2", r["recent"][0]["penalty"] == "+2")
    # OLL / PLL averages leave DNFs out by default; Full Solve always follows WCA
    c.put("/api/settings", json={"values": {"averages_skip_dnf": True}})
    on = c.get("/api/stats/pll").json()["session"]
    c.put("/api/settings", json={"values": {"averages_skip_dnf": False}})
    off = c.get("/api/stats/pll").json()["session"]
    full = c.get("/api/stats/full").json()["session"]
    check("averages_skip_dnf setting", on["skip_dnf"] is True and off["skip_dnf"] is False
          and full["skip_dnf"] is False and "dnf_rate" in on, (on["skip_dnf"], off["skip_dnf"]))
    check("bad averages_skip_dnf 400",
          c.put("/api/settings", json={"values": {"averages_skip_dnf": 1}}).status_code == 400)
    c.put("/api/settings", json={"values": {"averages_skip_dnf": True}})
    r = c.post("/api/times", json={"mode": "full", "seconds": 0, "penalty": "dnf"}).json()
    check("inspection DNF (0 s)", r["recent"][0]["penalty"] == "dnf")
    check("0 s without DNF 400", c.post("/api/times", json={"mode": "full", "seconds": 0}).status_code == 400)
    c.delete("/api/times/last/full"); c.delete("/api/times/last/full")
    r = c.delete(f"/api/solves/{oll_id}").json()
    check("delete any solve", r["case"] == "OLL 21" and c.delete(f"/api/solves/{oll_id}").status_code == 404)
    r = c.post("/api/times", json={"mode": "oll", "case": "OLL 21", "seconds": 3.21}).json()
    check("bad time 400", c.post("/api/times", json={"mode": "oll", "case": "OLL 21", "seconds": -1}).status_code == 400)
    check("bad case 400", c.post("/api/times", json={"mode": "oll", "case": "X", "seconds": 1}).status_code == 400)
    r = c.delete("/api/times/last/oll").json()
    check("delete last", r["deleted"] and r["case"] == "OLL 21" and (not r["case_times"] or r["case_times"][0] != 3.21))
    c.delete("/api/times/last/full")
    check("times list", isinstance(c.get("/api/times/full?limit=5").json(), list))
    check("summary", isinstance(c.get("/api/summary/pll").json(), dict))

    # selection / status / groups
    c.put("/api/selected/pll", json={"names": ["T Perm", "Y Perm"]})
    st = c.get("/api/state").json()
    check("selected", sorted(st["pll"]["selected"]) == ["T Perm", "Y Perm"])
    c.put("/api/status/pll", json={"names": ["T Perm"], "status": "learning"})
    check("status", c.get("/api/state").json()["pll"]["statuses"].get("T Perm") == "learning")
    c.put("/api/status/pll", json={"names": ["T Perm"], "status": "unlearned"})
    check("status cleared", "T Perm" not in c.get("/api/state").json()["pll"]["statuses"])
    check("bad status 400", c.put("/api/status/pll", json={"names": ["T Perm"], "status": "x"}).status_code == 400)
    c.put("/api/groups/pll/My%20G", json={"names": ["T Perm"]})
    check("group saved", c.get("/api/state").json()["pll"]["custom"] == {"My G": ["T Perm"]} or
          "My G" in c.get("/api/state").json()["pll"]["custom"])
    c.delete("/api/groups/pll/My%20G")
    check("group deleted", "My G" not in c.get("/api/state").json()["pll"]["custom"])
    check("client log", c.post("/api/log", json={"message": "test from api_test"}).status_code == 200)
    check("docs", c.get("/api/docs").status_code == 200)

    # export / import
    r = c.get("/api/export/csv")
    lines = r.text.strip().splitlines()
    n_all = sum(c.get(f"/api/stats/{m}").json()["all"]["count"] for m in ("full", "oll", "pll"))
    check("export CSV", r.headers["content-type"].startswith("text/csv")
          and "attachment" in r.headers["content-disposition"]
          and lines[0].startswith("mode,session,session_name,case,time") and len(lines) == n_all + 1,
          f"{len(lines) - 1} rows / {n_all}")
    backup = c.get("/api/export/backup").json()
    check("export backup", backup["app"] == "cube-timer" and len(backup["solves"]) == n_all)
    r = c.post("/api/import", json={"data": backup}).json()
    check("re-import own backup adds nothing", r["added"] == 0 and r["skipped"] == n_all, r)
    cs = c.get("/api/export/cstimer?modes=full").json()
    check("export csTimer", "properties" in cs and "session1" in cs)
    fixture = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "cstimer_sample.txt"), encoding="utf-8"))
    r = c.post("/api/import", json={"data": fixture}).json()
    names_now = [s["name"] for s in c.get("/api/stats/full").json()["sessions"]]
    check("import csTimer file", r["added"] == 7 and r["sessions"] == 2
          and {"Fixture GAN", "Fixture OH"} <= set(names_now), r)
    t = c.get("/api/solves/full?scope=all&limit=5000").json()["rows"]
    got = {(x["seconds"], x["penalty"], x["note"]) for x in t}
    check("csTimer penalties and comments", {(13.21, "+2", None), (15.0, "dnf", None),
                                             (11.87, None, "pb attempt")} <= got)
    r = c.post("/api/import", json={"data": fixture}).json()
    check("import twice adds nothing", r["added"] == 0 and r["skipped"] == 7)
    check("import junk 400", c.post("/api/import", json={"data": {"x": 1}}).status_code == 400)
    check("import a copy first", any("before-import" in f for f in os.listdir(os.path.dirname(tmp))))

# dependency check: too-old packages give a clear exit message, not a crash
real_version = cube_web.version
try:
    cube_web.version = lambda pkg: {"fastapi": "0.70.1", "pydantic": "1.8.2"}.get(pkg, "99.0")
    try:
        cube_web.check_dependencies(); msg = ""
    except SystemExit as exc:
        msg = str(exc)
    check("old packages named on exit", "fastapi: 0.70.1 is too old" in msg and "pydantic: 1.8.2" in msg
          and "pip install --upgrade -r" in msg)
    cube_web.version = lambda pkg: "99.0"
    try:
        cube_web.check_dependencies(); ok = True
    except SystemExit:
        ok = False
    check("current packages pass", ok)
finally:
    cube_web.version = real_version

after = hashlib.md5(open(REAL, "rb").read()).hexdigest()
check("real DB untouched", before == after)
fails = [r for r in results if not r[1]]
for name, ok, d in results: print(("PASS " if ok else "FAIL ") + name + (f"  [{d}]" if d else ""))
print(f"\n{len(results)-len(fails)}/{len(results)} passed")
sys.exit(1 if fails else 0)
