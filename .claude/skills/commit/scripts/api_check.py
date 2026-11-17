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
    check("add time", r["recent"][0][:2] == ["OLL 21", 3.21] and r["case_times"][0] == 3.21)
    r = c.post("/api/times", json={"mode": "full", "seconds": 15.5, "scramble": "R"}).json()
    check("add full", r["recent"][0][1] == 15.5)
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
