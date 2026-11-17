#!/usr/bin/env python3
"""
Claude Code Stop hook for the Cube Timer project (see .claude/settings.json).

Runs after every Claude turn:
  1. cleanup  - removes stray pytest-cache-files-* folders
  2. checks   - only when a .py file changed since the last run:
                byte-compiles every script and runs `python cube_diagram.py`
  3. docs     - if code changed after README.md / CLAUDE.md, asks Claude
                (once per change) to bring the docs up to date
Each run is logged to .claude/hook.log (last 500 lines kept).

A failed check or stale docs makes the hook answer {"decision": "block"},
which sends Claude back to fix it. It never blocks twice in a row
(stop_hook_active), and never nags twice about the same code change.
"""

import json
import py_compile
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLAUDE_DIR = ROOT / ".claude"
LOG = CLAUDE_DIR / "hook.log"
STATE = CLAUDE_DIR / "hook_state.json"
DOCS = [ROOT / "README.md", ROOT / "CLAUDE.md"]


def log(lines):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    old = LOG.read_text(encoding="utf-8").splitlines() if LOG.exists() else []
    new = old + [f"{stamp} {line}" for line in lines]
    LOG.write_text("\n".join(new[-500:]) + "\n", encoding="utf-8")


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = {}
    state = load_state()
    notes, problems = [], []

    # 1. cleanup
    for d in ROOT.glob("pytest-cache-files-*"):
        shutil.rmtree(d, ignore_errors=True)
        notes.append(f"removed {d.name}" if not d.exists() else f"could not remove {d.name}")

    # 2. checks, only if code changed since the last run
    scripts = sorted(ROOT.glob("*.py"))
    code_mtime = max((p.stat().st_mtime for p in scripts), default=0)
    if code_mtime > state.get("checked_mtime", 0):
        for p in scripts:
            try:
                py_compile.compile(str(p), doraise=True)
            except py_compile.PyCompileError as exc:
                problems.append(f"{p.name} does not compile: {exc.msg.strip()}")
        result = subprocess.run([sys.executable, "cube_diagram.py"], cwd=ROOT,
                                capture_output=True, text=True, timeout=120)
        output = (result.stdout + result.stderr).strip()
        if result.returncode or "check out" not in output:
            problems.append("cube_diagram.py check failed:\n" + output[-1500:])
        notes.append(f"checked {len(scripts)} scripts: "
                     + ("FAILED" if problems else "ok"))
        if not problems:
            state["checked_mtime"] = code_mtime

    # 3. docs older than the code?
    docs_mtime = min((p.stat().st_mtime for p in DOCS if p.exists()), default=0)
    stale_docs = code_mtime > docs_mtime and code_mtime > state.get("docs_nagged_mtime", 0)

    reasons = []
    if problems:
        reasons.append("Post-turn checks failed:\n" + "\n".join(problems))
    if stale_docs:
        reasons.append("Code changed after README.md / CLAUDE.md were last updated. "
                       "Bring both up to date with this turn's changes (or confirm "
                       "nothing user- or maintainer-facing changed).")
        state["docs_nagged_mtime"] = code_mtime

    blocked = bool(reasons) and not payload.get("stop_hook_active")
    notes.append("blocked: " + " | ".join(r.splitlines()[0] for r in reasons)
                 if blocked else "done")
    log(notes)
    STATE.write_text(json.dumps(state), encoding="utf-8")

    if blocked:
        print(json.dumps({"decision": "block", "reason": "\n\n".join(reasons)}))


if __name__ == "__main__":
    main()
