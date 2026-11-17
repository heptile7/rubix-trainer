"""
Drive the terminal app (cube_timer.py) with scripted input against a temporary
copy of the database: a full solve, session stats, OLL and PLL practice
(cancelled at the timer), all three statistics views, then quit.
Exit code 0 when it saves exactly one full solve and exits cleanly.
"""
import hashlib, os, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
REAL = ROOT / "cube_times.db"

if len(sys.argv) > 1 and sys.argv[1] == "--child":
    # runs inside the subprocess: patch the database, then run the menu
    tmp = sys.argv[2]
    sys.path.insert(0, str(ROOT))
    import cube_timer as ct
    real_db = ct.Database
    ct.Database = lambda path: real_db(tmp)
    try:
        ct.main()
    except EOFError:
        print("EOF before quit")
        sys.exit(2)
    sys.exit(0)

before = hashlib.md5(REAL.read_bytes()).hexdigest()
tmp = os.path.join(tempfile.mkdtemp(), "t.db")
shutil.copy(REAL, tmp)
sys.path.insert(0, str(ROOT))
import sqlite3
count = lambda: dict(sqlite3.connect(tmp).execute("SELECT mode, COUNT(*) FROM times GROUP BY mode").fetchall())
n0 = count()

# full: Enter start, Enter stop, s(tats), Enter, q | OLL: q cancels timer, q, q
# PLL: same | stats: 1, 2, 3 with Enter each, q | quit
keys = "1\n\n\ns\n\nq\n2\nq\nq\nq\n3\nq\nq\nq\n4\n1\n\n2\n\n3\n\nq\nq\n"
proc = subprocess.run([sys.executable, __file__, "--child", tmp], input=keys, text=True,
                      capture_output=True, timeout=60, encoding="utf-8",
                      env={**os.environ, "PYTHONIOENCODING": "utf-8"})
n1 = count()
out = proc.stdout + proc.stderr

results = [
    ("exits cleanly", proc.returncode == 0 and "Goodbye" in out, f"code {proc.returncode}"),
    ("no traceback", "Traceback" not in out, ""),
    ("one full solve saved", n1.get("full", 0) == n0.get("full", 0) + 1, f"{n0} -> {n1}"),
    ("cancelled drills save nothing",
     n1.get("oll", 0) == n0.get("oll", 0) and n1.get("pll", 0) == n0.get("pll", 0), ""),
    ("real DB untouched", hashlib.md5(REAL.read_bytes()).hexdigest() == before, ""),
]
for name, ok, d in results:
    print(("PASS " if ok else "FAIL ") + name + (f"  [{d}]" if d else ""))
fails = [r for r in results if not r[1]]
if fails:
    print("\n--- output tail ---\n" + out[-2000:])
print(f"\n{len(results) - len(fails)}/{len(results)} passed")
sys.exit(1 if fails else 0)
