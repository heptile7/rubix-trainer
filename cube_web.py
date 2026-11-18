#!/usr/bin/env python3
"""
Cube Timer - web front end.

A small FastAPI server on localhost that serves the browser UI in web/ and a
JSON API over the same data layer and database as the other front ends
(cube_timer.py, cube_times.db). The browser does all the drawing; the server
only reads and writes SQLite and makes scrambles.

    python cube_web.py               # opens the app in the default browser
    python cube_web.py --window      # own window instead (needs: pip install pywebview)
    python cube_web.py --no-browser  # just serve (prints the address)

Requirements: pip install -r requirements.txt  (fastapi, uvicorn, pydantic, rich)
"""

import argparse
import json
import logging
import re
import socket
import sys
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

# Oldest versions that work (keep in step with requirements.txt). Checked before
# importing them: an old pydantic (< 1.10) doesn't merely lack features, it
# crashes on import under Python 3.11 ("'not' is not a valid parameter name").
MIN_VERSIONS = {"fastapi": (0, 110), "uvicorn": (0, 29), "pydantic": (1, 10), "rich": (13, 0)}


def check_dependencies():
    """Exit with a clear message if a package is missing or too old for this app."""
    problems = []
    for package, minimum in MIN_VERSIONS.items():
        try:
            found = version(package)
        except PackageNotFoundError:
            problems.append(f"  {package}: not installed (need {'.'.join(map(str, minimum))} or later)")
            continue
        parts = tuple(int(n) for n in re.findall(r"\d+", found)[:2])
        if parts < minimum:
            problems.append(f"  {package}: {found} is too old (need {'.'.join(map(str, minimum))} or later)")
    if problems:
        sys.exit("Cube Timer web app can't start with this Python's packages:\n"
                 + "\n".join(problems)
                 + f"\n\nPython: {sys.executable}\nFix:    \"{sys.executable}\" -m pip install "
                 f"--upgrade -r \"{Path(__file__).with_name('requirements.txt')}\"")


check_dependencies()

from fastapi import FastAPI, HTTPException, Request  # noqa: E402  (after the check above)
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cube_diagram import case_diagram, case_weight, scramble_state, state_diagram
from cube_timer import (DNF, OLL_CASES, PENALTIES, PLL_CASES, Database, check_setting, effective,
                        setup_logging, setup_scramble)

log = logging.getLogger("cube_timer.web")

ROOT     = Path(__file__).parent
WEB_DIR  = ROOT / "web"
DB_PATH  = ROOT / "cube_times.db"
CASES    = {"oll": OLL_CASES, "pll": PLL_CASES}
MODES    = ("full", "oll", "pll")
STATUSES = ("unlearned", "learning", "finished")
HISTORY  = 100      # attempts of the current session sent for a screen's history
CASE_N   = 12       # times kept per case (result bar: last, best, ao5, ao12)


# ---------------------------------------------------------------------------
# Diagrams as JSON
# ---------------------------------------------------------------------------
def diagram_json(diagram):
    """state_diagram() output in a compact JSON-friendly form."""
    top, sides, arrows, perm = diagram
    return {
        "top":    [[x, z, c] for (x, z), c in top.items()],
        "sides":  [[x, z, nx, nz, c] for (x, z, nx, nz), c in sides.items()],
        "arrows": [[a[0], a[1], b[0], b[1], swap] for a, b, swap in arrows],
        "perm":   perm,
    }


def _static_cases():
    """Every case with its picture and realistic weight, worked out once."""
    start = time.perf_counter()
    out = {mode: [{"name": c["name"], "group": c["group"], "alg": c["alg"],
                   "weight": case_weight(c["alg"]),
                   "diagram": diagram_json(case_diagram(c["alg"]))}
                  for c in cases]
           for mode, cases in CASES.items()}
    log.info("case pictures worked out in %.2fs", time.perf_counter() - start)
    return out


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------
class Attempt(BaseModel):
    mode: str
    case: str | None = None
    seconds: float
    scramble: str | None = None
    penalty: str | None = None      # +2 / dnf from inspection


class Names(BaseModel):
    names: list[str]


class StatusChange(BaseModel):
    names: list[str]
    status: str


class PenaltyChange(BaseModel):
    penalty: str | None = None      # None, "+2" or "dnf"


class Settings(BaseModel):
    values: dict


class SessionName(BaseModel):
    name: str | None = None


class FlagChange(BaseModel):
    flagged: bool
    note: str | None = None


class ClientLog(BaseModel):
    level: str = "error"
    message: str


def jsonable(value):
    """JSON has no infinity: a DNF time or average is sent as the string "DNF"."""
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    return "DNF" if value == DNF else value


def solve_json(row):
    """A Database.solves() tuple as the object the page uses."""
    sid, case, seconds, penalty, flagged, note, ts, _session = row
    return {"id": sid, "case": case, "seconds": seconds, "penalty": penalty,
            "flagged": bool(flagged), "note": note, "ts": ts}


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
def create_app(db_path=DB_PATH):
    """
    The web app over the database at db_path. Every endpoint is `async def`, so
    they all run on the event-loop thread, which is also the thread that opens
    the database (in lifespan): the one sqlite connection is never used from
    two threads, and no locks are needed.
    """
    db    = None        # opened in lifespan
    cases = _static_cases()
    names = {m: {c["name"] for c in cs} for m, cs in CASES.items()}
    by_name = {m: {c["name"]: c for c in cs} for m, cs in CASES.items()}

    @asynccontextmanager
    async def lifespan(app):
        nonlocal db
        db = app.state.db = Database(db_path)
        yield
        log.info("closing")
        db.close()

    app = FastAPI(title="Cube Timer", docs_url="/api/docs", redoc_url=None,
                  openapi_url="/api/openapi.json", lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # --- helpers --------------------------------------------------------
    def check_mode(mode, trainer=False):
        if mode not in (CASES if trainer else MODES):
            raise HTTPException(404, f"unknown mode {mode!r}")

    def check_names(mode, given):
        unknown = set(given) - names[mode]
        if unknown:
            raise HTTPException(400, f"unknown cases: {sorted(unknown)}")

    def case_times(mode):
        """{case name: its latest CASE_N times, newest first}, in one query."""
        out = {}
        for name, seconds, penalty in db.conn.execute(
                "SELECT case_name,seconds,penalty FROM times WHERE mode=? AND case_name IS NOT NULL "
                "ORDER BY rowid DESC", (mode,)):
            times = out.setdefault(name, [])
            if len(times) < CASE_N and penalty != "dnf":
                times.append(effective(seconds, penalty))
        return out

    def one_case_times(mode, case):
        rows = db.solves(mode, case_name=case, limit=CASE_N * 3)
        return [effective(r[2], r[3]) for r in rows if r[3] != "dnf"][:CASE_N]

    def recent(mode):
        """The current session's latest attempts, newest first."""
        return [solve_json(r) for r in db.solves(mode, "session", limit=HISTORY)]

    def stats(mode):
        """Stats of the selected session and of all time, plus the session list."""
        return {"session_no": db.current_session(mode),
                "session_name": db.session_name(mode),
                "sessions":   [{"n": n, "name": name, "count": count, "last": last}
                               for n, name, count, last in db.list_sessions(mode)],
                "session":    jsonable(db.stats(mode, "session")),
                "all":        jsonable(db.stats(mode))}

    def user_state():
        return {m: {"selected": sorted(db.get_selected(m)),
                    "statuses": db.get_statuses(m),
                    "custom":   {g: sorted(n) for g, n in db.get_custom_groups(m).items()}}
                for m in CASES}

    def bootstrap():
        return {
            "cases":      cases,
            "state":      user_state(),
            "recent":     {m: recent(m) for m in MODES},
            "stats":      {m: stats(m) for m in MODES},
            "settings":   db.get_settings(),
            "case_times": {m: case_times(m) for m in CASES},
        }

    def times_after_change(mode, case):
        """What a screen needs to repaint after an attempt is added, changed or removed."""
        out = {"mode": mode, "case": case, "recent": recent(mode), "stats": stats(mode)}
        if case:
            out["case_times"] = one_case_times(mode, case)
        return out

    def find_solve(solve_id):
        row = db.solve(solve_id)
        if not row:
            raise HTTPException(404, f"no solve {solve_id}")
        return row[0], row[2]       # mode, case name

    # --- page -----------------------------------------------------------
    # index.html carries the bootstrap data inline, so the first paint needs no
    # second round trip. The template is re-read only when the file changes.
    template = {"mtime": None, "text": ""}

    @app.get("/", response_class=HTMLResponse)
    async def index():
        path = WEB_DIR / "index.html"
        mtime = path.stat().st_mtime
        if template["mtime"] != mtime:
            template.update(mtime=mtime, text=path.read_text(encoding="utf-8"))
        data = json.dumps(bootstrap(), separators=(",", ":")).replace("</", "<\\/")
        html = template["text"].replace("<!--BOOT-->", data)
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    # --- API ------------------------------------------------------------
    @app.get("/api/bootstrap")
    async def get_bootstrap():
        return bootstrap()

    @app.get("/api/state")
    async def get_state():
        return user_state()

    @app.get("/api/deal/{mode}/{case}")
    async def deal(mode: str, case: str):
        """A setup scramble for the case and a picture of the cube it leaves."""
        check_mode(mode, trainer=True)
        if case not in by_name[mode]:
            raise HTTPException(404, f"unknown case {case!r}")
        scramble = setup_scramble(by_name[mode][case])
        return {"case": case, "scramble": scramble,
                "diagram": diagram_json(state_diagram(scramble_state(scramble)))}

    @app.post("/api/times")
    async def add_time(a: Attempt):
        check_mode(a.mode)
        if a.mode != "full":
            check_names(a.mode, [a.case])
        if not 0 <= a.seconds < 24 * 3600 or (a.seconds == 0 and a.penalty != "dnf"):
            raise HTTPException(400, "time out of range")
        if a.penalty not in PENALTIES:
            raise HTTPException(400, f"unknown penalty {a.penalty!r}")
        case = a.case if a.mode != "full" else None
        sid = db.add(a.mode, a.seconds, case_name=case, scramble=a.scramble, penalty=a.penalty)
        log.info("%s attempt: %s %.2f", a.mode, a.case or "-", a.seconds)
        return {"id": sid, **times_after_change(a.mode, case)}

    @app.delete("/api/times/last/{mode}")
    async def delete_last(mode: str):
        """Remove the newest attempt of the selected session (the top row of the history)."""
        check_mode(mode)
        row = db.conn.execute("SELECT case_name FROM times WHERE mode=? AND session=? "
                              "ORDER BY rowid DESC LIMIT 1",
                              (mode, db.current_session(mode))).fetchone()
        if not row or not db.delete_last(mode):
            return {"deleted": False, **times_after_change(mode, None)}
        return {"deleted": True, **times_after_change(mode, row[0])}

    @app.get("/api/times/{mode}")
    async def get_times(mode: str, limit: int = 50):
        """Latest [time, timestamp] pairs, penalties applied."""
        check_mode(mode)
        return jsonable([[s, ts] for s, ts in db.get(mode, limit=max(1, min(limit, 1000)))])

    # --- single solves and sessions ----------------------------------------
    @app.get("/api/solves/{mode}")
    async def get_solves(mode: str, scope: str = "session", flagged: bool = False,
                         limit: int = 200, case: str | None = None):
        """Rows for the Statistics table and chart, each with its ao5 / ao12, plus
        the total in scope. case narrows them (and the averages) to one case."""
        check_mode(mode)
        if scope not in ("session", "all"):
            raise HTTPException(400, f"unknown scope {scope!r}")
        if case:
            check_mode(mode, trainer=True)
            check_names(mode, [case])
        rows, total = db.solve_table(mode, scope, flagged_only=flagged,
                                     limit=max(1, min(limit, 5000)), case_name=case or None)
        return {"rows": jsonable(rows), "total": total, **stats(mode)}

    @app.get("/api/stats/{mode}")
    async def get_stats(mode: str):
        check_mode(mode)
        return stats(mode)

    @app.put("/api/solves/{solve_id}/penalty")
    async def put_penalty(solve_id: int, body: PenaltyChange):
        mode, case = find_solve(solve_id)
        if body.penalty not in PENALTIES:
            raise HTTPException(400, f"unknown penalty {body.penalty!r}")
        db.set_penalty(solve_id, body.penalty)
        return times_after_change(mode, case)

    @app.put("/api/solves/{solve_id}/flag")
    async def put_flag(solve_id: int, body: FlagChange):
        mode, case = find_solve(solve_id)
        db.set_flag(solve_id, body.flagged, body.note)
        return times_after_change(mode, case)

    @app.delete("/api/solves/{solve_id}")
    async def delete_solve(solve_id: int):
        mode, case = find_solve(solve_id)
        db.delete_solve(solve_id)
        return times_after_change(mode, case)

    @app.post("/api/session/{mode}")
    async def new_session(mode: str, body: SessionName | None = None):
        """Create a named session after the others and select it."""
        check_mode(mode)
        db.new_session(mode, body.name if body else None)
        return times_after_change(mode, None)

    def check_session(mode, n):
        check_mode(mode)
        if n not in {s[0] for s in db.list_sessions(mode)}:
            raise HTTPException(404, f"no session {n} in {mode}")

    @app.put("/api/session/{mode}/{n}")
    async def select_session(mode: str, n: int):
        """Select a session: new attempts go into it, and its history and stats show."""
        check_session(mode, n)
        db.select_session(mode, n)
        return times_after_change(mode, None)

    @app.patch("/api/session/{mode}/{n}")
    async def rename_session(mode: str, n: int, body: SessionName):
        check_session(mode, n)
        db.rename_session(mode, n, body.name)
        return times_after_change(mode, None)

    @app.delete("/api/session/{mode}/{n}")
    async def delete_session(mode: str, n: int):
        """Delete a session and its attempts (not the last session of a mode)."""
        check_session(mode, n)
        try:
            db.delete_session(mode, n)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return times_after_change(mode, None)

    @app.get("/api/settings")
    async def get_settings():
        return db.get_settings()

    @app.put("/api/settings")
    async def put_settings(body: Settings):
        """Save some settings (inspection, hold to start); returns all of them."""
        problems = [p for p in (check_setting(k, v) for k, v in body.values.items()) if p]
        if problems:
            raise HTTPException(400, "; ".join(problems))
        for key, value in body.values.items():
            db.set_setting(key, value)
        return db.get_settings()

    @app.get("/api/summary/{mode}")
    async def summary(mode: str):
        check_mode(mode, trainer=True)
        return {name: [n, best, avg] for name, n, best, avg in db.case_summary(mode)}

    @app.put("/api/selected/{mode}")
    async def put_selected(mode: str, body: Names):
        check_mode(mode, trainer=True)
        check_names(mode, body.names)
        db.set_selected(mode, set(body.names))
        log.debug("%s selection now %d cases", mode, len(body.names))
        return {"ok": True}

    @app.put("/api/status/{mode}")
    async def put_status(mode: str, body: StatusChange):
        check_mode(mode, trainer=True)
        check_names(mode, body.names)
        if body.status not in STATUSES:
            raise HTTPException(400, f"unknown status {body.status!r}")
        db.set_statuses(mode, body.names, body.status)
        log.info("%s: marked %d cases %s", mode, len(body.names), body.status)
        return {"ok": True}

    @app.put("/api/groups/{mode}/{name}")
    async def put_group(mode: str, name: str, body: Names):
        check_mode(mode, trainer=True)
        check_names(mode, body.names)
        name = name.strip()[:30]
        if not name:
            raise HTTPException(400, "empty group name")
        db.save_custom_group(mode, name, body.names)
        log.info("%s group %r saved with %d cases", mode, name, len(body.names))
        return {"ok": True}

    @app.delete("/api/groups/{mode}/{name}")
    async def delete_group(mode: str, name: str):
        check_mode(mode, trainer=True)
        db.delete_custom_group(mode, name)
        log.info("%s group %r deleted", mode, name)
        return {"ok": True}

    @app.post("/api/log")
    async def client_log(entry: ClientLog):
        level = logging.ERROR if entry.level == "error" else logging.INFO
        logging.getLogger("cube_timer.browser").log(level, "%s", entry.message[:4000])
        return {"ok": True}

    @app.exception_handler(Exception)
    async def on_error(request: Request, exc: Exception):
        log.error("Error in %s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse({"detail": "server error"}, status_code=500)

    # Static files (ETag + Last-Modified; no-cache makes the browser revalidate,
    # so a reload is a cheap 304 and an edited file is never served stale).
    @app.middleware("http")
    async def revalidate(request: Request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-cache")
        return response

    app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
    return app


# ---------------------------------------------------------------------------
def _free_port(start=8765, tries=40):
    for port in range(start, start + tries):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit("no free port found")


def main():
    parser = argparse.ArgumentParser(description="Cube Timer web app")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser")
    parser.add_argument("--window", action="store_true",
                        help="open in its own window (needs pywebview)")
    args = parser.parse_args()

    setup_logging()
    import uvicorn

    start = time.perf_counter()
    port = args.port or _free_port()
    url = f"http://127.0.0.1:{port}/"
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port,
                                           log_level="warning"))

    def when_up(fn):
        def wait():
            while not server.started:
                time.sleep(0.02)
            log.info("serving %s (ready in %.2fs)", url, time.perf_counter() - start)
            fn()
        threading.Thread(target=wait, daemon=True).start()

    if args.window:
        try:
            import webview
        except ImportError:
            raise SystemExit("--window needs pywebview:  pip install pywebview")
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        while not server.started:
            time.sleep(0.02)
        webview.create_window("Cube Timer", url, width=1180, height=760, min_size=(980, 640))
        webview.start()
        server.should_exit = True
        thread.join(timeout=5)
        return

    print(f"Cube Timer at {url}  (Ctrl+C to stop)", flush=True)
    when_up((lambda: None) if args.no_browser else (lambda: webbrowser.open(url)))
    server.run()


if __name__ == "__main__":
    main()
