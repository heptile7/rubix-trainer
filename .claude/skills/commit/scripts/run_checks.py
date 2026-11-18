"""
Run the checks a change needs before it is committed.

    python .claude/skills/commit/scripts/run_checks.py          # checks for what changed
    python .claude/skills/commit/scripts/run_checks.py --all    # every check
    python .claude/skills/commit/scripts/run_checks.py --list   # just say what would run

What changed = uncommitted changes (staged or not) plus untracked files, as
git reports them. Every check uses a temporary copy of cube_times.db and
fails if the real one changes. Exit code 0 only if every check passed.
"""
import subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]

CHECKS = {
    "compile": "byte-compile every script",
    "algorithms": "python cube_diagram.py (every OLL/PLL algorithm)",
    "cli": "terminal app driven by scripted input",
    "gui": "customtkinter app driven headlessly (93 checks)",
    "api": "web API via TestClient, incl. every case's scramble",
    "web": "web page in headless Chrome via Playwright",
}

# which checks a changed path needs
RULES = [
    (lambda p: p == "cube_timer.py",       {"compile", "algorithms", "cli", "gui", "api", "web"}),
    (lambda p: p == "cube_diagram.py",     {"compile", "algorithms", "gui", "api", "web"}),
    (lambda p: p == "cube_timer_gui.py",   {"compile", "gui"}),
    (lambda p: p == "cube_web.py",         {"compile", "api", "web"}),
    (lambda p: p == "cube_io.py",          {"compile", "gui", "api", "web"}),
    (lambda p: p.startswith(".claude/skills/commit/scripts/fixtures/"), {"gui", "api", "web"}),
    (lambda p: p.startswith("web/"),       {"api", "web"}),
    (lambda p: p == "case_scrambles.json", {"api", "gui"}),
    (lambda p: p == "requirements.txt",    {"compile", "gui", "api", "web"}),
    (lambda p: p.endswith(".py"),          {"compile", "algorithms"}),
]
CODE = lambda p: p.endswith((".py", ".js", ".html", ".css", ".json")) or p == "requirements.txt"


def changed_files():
    out = subprocess.run(["git", "status", "--porcelain", "-uall"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    files = []
    for line in out.splitlines():
        path = line[3:].split(" -> ")[-1].strip().strip('"')
        files.append(path.replace("\\", "/"))
    return files


def run(name):
    if name == "compile":
        import py_compile
        bad = []
        for p in sorted(ROOT.glob("*.py")) + sorted(HERE.glob("*.py")):
            try:
                py_compile.compile(str(p), doraise=True)
            except py_compile.PyCompileError as exc:
                bad.append(f"{p.name}: {exc.msg.strip()}")
        return not bad, "\n".join(bad) or "all scripts compile"
    if name == "algorithms":
        r = subprocess.run([sys.executable, "cube_diagram.py"], cwd=ROOT, capture_output=True, text=True)
        ok = r.returncode == 0 and "All OLL and PLL algorithms check out." in r.stdout
        return ok, (r.stdout + r.stderr).strip()[-1500:]
    script = HERE / f"{name}_check.py"
    r = subprocess.run([sys.executable, str(script)], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=600)
    lines = r.stdout.strip().splitlines()
    # the FAIL lines if any, else the summary line ("46/46 passed ...")
    detail = "\n".join(l for l in lines if l.startswith("FAIL")) or (lines[-1] if lines else "")
    if r.returncode != 0 and not detail.startswith("FAIL"):
        detail = (detail + "\n" + r.stderr[-1500:]).strip()   # crashed before reporting
    return r.returncode == 0, detail


def main():
    files = changed_files()
    if "--all" in sys.argv:
        needed = set(CHECKS)
    else:
        needed = set()
        for f in files:
            for match, checks in RULES:
                if match(f):
                    needed |= checks
                    break

    print("Changed:", ", ".join(files) or "(nothing)")
    order = [c for c in CHECKS if c in needed]
    print("Checks:", ", ".join(order) or "(none needed)")
    if "--list" in sys.argv:
        return 0

    failed = []
    for name in order:
        start = time.perf_counter()
        ok, detail = run(name)
        print(f"\n[{'PASS' if ok else 'FAIL'}] {name} - {CHECKS[name]} ({time.perf_counter() - start:.1f}s)")
        if detail:
            print("    " + detail.replace("\n", "\n    "))
        if not ok:
            failed.append(name)

    # reminders that are not failures
    code = [f for f in files if CODE(f) and not f.startswith(".claude/")]
    if code and not {"README.md", "CLAUDE.md"} & set(files):
        print("\nNOTE: code changed but README.md / CLAUDE.md did not - update them or confirm "
              "nothing user- or maintainer-facing changed.")
    if "cube_times.db" in files:
        print("\nNOTE: cube_times.db (the user's times) has changed. Do not stage it unless the "
              "user asks.")

    print("\nRESULT:", "all checks passed" if not failed else f"FAILED: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
