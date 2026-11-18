#!/usr/bin/env python3
"""
Export and import for the Cube Timer database (used by cube_web.py and
cube_timer_gui.py; depends only on cube_timer's data layer).

Formats
- CSV: one row per attempt, for spreadsheets. Export only.
- Backup (JSON, "app": "cube-timer"): sessions with their names, every
  attempt with penalty / flag / note / scramble / date, the practice
  selection, case statuses and custom groups. Export and import.
- csTimer (JSON, its "Export to file" format): one csTimer session per
  (mode, session). Each solve is [[penalty_ms, time_ms], scramble, comment,
  unix time], with penalty_ms 0, 2000 (+2) or -1 (DNF). Export and import.

Importing always merges, never replaces. A session is matched by mode and
name, or created after the existing ones (the selected session doesn't
change). An attempt that is already there, with the same mode, time (to the
millisecond) and date, is skipped, so importing a file twice adds nothing.
Before an import the database file is copied to
cube_times.before-import-<date-time>.db.
"""

import csv
import io
import json
import logging
import sqlite3
import time
from datetime import datetime

from cube_timer import PENALTIES, effective

log = logging.getLogger("cube_timer.io")

MODES = ("full", "oll", "pll")
MODE_LABEL = {"full": "", "oll": "OLL – ", "pll": "PLL – "}
BACKUP_VERSION = 1
TS_FORMAT = "%Y-%m-%d %H:%M:%S"


# ---------------------------------------------------------------------------
# Reading the database
# ---------------------------------------------------------------------------
def _attempts(db, modes):
    """Every attempt in these modes, oldest first, as dicts."""
    marks = ",".join("?" * len(modes))
    rows = db.conn.execute(
        f"SELECT mode,session,case_name,seconds,penalty,flagged,note,scramble,ts "
        f"FROM times WHERE mode IN ({marks}) ORDER BY id", list(modes)).fetchall()
    keys = ("mode", "session", "case", "seconds", "penalty", "flagged", "note", "scramble", "ts")
    return [dict(zip(keys, r)) for r in rows]


def _session_names(db, modes):
    return {(m, n): name for m in modes for n, name, _c, _l in db.list_sessions(m)}


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------
CSV_COLUMNS = ["mode", "session", "session_name", "case", "time", "seconds", "penalty",
               "flagged", "note", "scramble", "date"]


def export_csv(db, modes=MODES):
    """The attempts as CSV text. `time` has the penalty applied ("DNF" for a DNF);
    `seconds` is the time on the clock."""
    names = _session_names(db, modes)
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(CSV_COLUMNS)
    for a in _attempts(db, modes):
        t = effective(a["seconds"], a["penalty"])
        w.writerow([a["mode"], a["session"], names.get((a["mode"], a["session"]), ""),
                    a["case"] or "", "DNF" if a["penalty"] == "dnf" else f"{t:.3f}",
                    f"{a['seconds']:.3f}", a["penalty"] or "", 1 if a["flagged"] else 0,
                    a["note"] or "", a["scramble"] or "", a["ts"]])
    return out.getvalue()


# ---------------------------------------------------------------------------
# Backup (this app's own format)
# ---------------------------------------------------------------------------
def export_backup(db):
    sessions = []
    for m in MODES:
        created = dict(db.conn.execute(
            "SELECT number, created FROM session_list WHERE mode=?", (m,)).fetchall())
        for n, name, _c, _l in db.list_sessions(m):
            sessions.append({"mode": m, "number": n, "name": name, "created": created.get(n)})
    trainer = ("oll", "pll")
    return {
        "app": "cube-timer",
        "version": BACKUP_VERSION,
        "exported": datetime.now().strftime(TS_FORMAT),
        "sessions": sessions,
        "current": {m: db.current_session(m) for m in MODES},
        "solves": [{**a, "flagged": bool(a["flagged"])} for a in _attempts(db, MODES)],
        "selected": {m: sorted(db.get_selected(m)) for m in trainer},
        "statuses": {m: db.get_statuses(m) for m in trainer},
        "groups": {m: {g: sorted(c) for g, c in db.get_custom_groups(m).items()} for m in trainer},
        "settings": db.get_settings(),
    }


class ImportProblem(ValueError):
    """The file isn't something we can import (message is for the user)."""


def _existing_keys(db):
    return {(m, round(s, 3), ts) for m, s, ts in
            db.conn.execute("SELECT mode, seconds, ts FROM times")}


def _session_for(db, mode, name, cache):
    """Local session number for (mode, name), creating it (unselected) if needed."""
    key = (mode, name)
    if key not in cache:
        found = [n for n, nm, _c, _l in db.list_sessions(mode) if nm == name]
        cache[key] = found[0] if found else db.create_session(mode, name)
    return cache[key]


def import_backup(db, data, case_names=None):
    """
    Merge a backup into db. case_names: {mode: set of valid case names}; attempts
    and selections naming unknown cases are skipped. Returns a summary dict.
    """
    if not isinstance(data, dict) or data.get("app") != "cube-timer":
        raise ImportProblem("This is not a Cube Timer backup.")
    if data.get("version", 0) > BACKUP_VERSION:
        raise ImportProblem("This backup was made by a newer version of Cube Timer.")
    names = {(s["mode"], s["number"]): s["name"] for s in data.get("sessions", [])
             if s.get("mode") in MODES}
    existing, cache = _existing_keys(db), {}
    added = skipped = 0
    before = {m: len(db.list_sessions(m)) for m in MODES}
    for a in data.get("solves", []):
        mode = a.get("mode")
        if mode not in MODES or a.get("penalty") not in PENALTIES:
            skipped += 1
            continue
        case = a.get("case")
        if mode != "full" and case_names and case not in case_names.get(mode, ()):
            skipped += 1
            continue
        seconds, ts = float(a["seconds"]), a.get("ts") or datetime.now().strftime(TS_FORMAT)
        key = (mode, round(seconds, 3), ts)
        if key in existing:
            skipped += 1
            continue
        session = _session_for(db, mode, names.get((mode, a.get("session")),
                                                   f"Session {a.get('session', 1)}"), cache)
        db.add_imported(mode, session, None if mode == "full" else case, seconds,
                        a.get("penalty"), bool(a.get("flagged")), a.get("note"),
                        a.get("scramble"), ts)
        existing.add(key)
        added += 1
    # practice set, statuses and groups: add what's new, keep what's here
    for m in ("oll", "pll"):
        valid = case_names.get(m) if case_names else None
        ok = lambda names_: [n for n in names_ if valid is None or n in valid]
        sel = set(ok(data.get("selected", {}).get(m, [])))
        if sel - db.get_selected(m):
            db.set_selected(m, db.get_selected(m) | sel)
        have = db.get_statuses(m)
        for name, status in data.get("statuses", {}).get(m, {}).items():
            if name not in have and ok([name]) and status in ("learning", "finished"):
                db.set_status(m, name, status)
        groups = db.get_custom_groups(m)
        for g, members in data.get("groups", {}).get(m, {}).items():
            if g not in groups and ok(members):
                db.save_custom_group(m, g, ok(members))
    db.conn.commit()
    created = sum(len(db.list_sessions(m)) - before[m] for m in MODES)
    log.info("imported backup: %d added, %d skipped, %d new sessions", added, skipped, created)
    return {"format": "cube-timer", "added": added, "skipped": skipped, "sessions": created}


# ---------------------------------------------------------------------------
# csTimer
# ---------------------------------------------------------------------------
def _unix(ts):
    try:
        return int(time.mktime(time.strptime(ts, TS_FORMAT)))
    except (TypeError, ValueError):
        return int(time.time())


def export_cstimer(db, modes=("full",)):
    """csTimer's export file: one session per (mode, session). For practice modes the
    case goes into the comment ("OLL 21" or "OLL 21 · note") and the name gets a prefix."""
    data, meta, k = {}, {}, 0
    by_session = {}
    for a in _attempts(db, modes):
        by_session.setdefault((a["mode"], a["session"]), []).append(a)
    for m in modes:
        for n, name, _c, _l in db.list_sessions(m):
            solves = by_session.get((m, n), [])
            k += 1
            out = []
            for a in solves:
                penalty = -1 if a["penalty"] == "dnf" else 2000 if a["penalty"] == "+2" else 0
                comment = " · ".join(x for x in (a["case"], a["note"]) if x)
                out.append([[penalty, int(round(a["seconds"] * 1000))], a["scramble"] or "",
                            comment, _unix(a["ts"])])
            data[f"session{k}"] = out
            meta[str(k)] = {"name": f"{MODE_LABEL[m]}{name}", "opt": {}, "rank": k}
    data["properties"] = {"sessionData": json.dumps(meta), "sessionN": k}
    return data


def is_cstimer(data):
    return isinstance(data, dict) and "properties" in data and any(
        k.startswith("session") and k[7:].isdigit() for k in data)


def _practice_target(name, case_names):
    """("oll", "GAN 12") for a session this app exported as "OLL – GAN 12", else None."""
    for m, label in MODE_LABEL.items():
        if label and name.startswith(label) and case_names and m in case_names:
            return m, name[len(label):].strip() or "Session 1"
    return None


def import_cstimer(db, data, mode="full", case_names=None):
    """
    Merge a csTimer export. Its sessions go into Full Solve (csTimer solves have no
    case), except sessions this app exported from OLL / PLL ("OLL – name"), whose
    comments start with the case: with case_names given they go back to that mode.
    """
    if not is_cstimer(data):
        raise ImportProblem("This is not a csTimer export file.")
    if mode != "full":
        raise ImportProblem("csTimer solves have no OLL / PLL case, so they can only go into Full Solve.")
    meta = data["properties"].get("sessionData", {})
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except ValueError:
            meta = {}
    existing, cache = _existing_keys(db), {}
    added = skipped = 0
    before = sum(len(db.list_sessions(m)) for m in MODES)
    numbers = sorted((int(k[7:]), k) for k in data if k.startswith("session") and k[7:].isdigit())
    for n, key in numbers:
        solves = data[key]
        if not isinstance(solves, list) or not solves:
            continue
        name = str((meta.get(str(n)) or {}).get("name", "") or "").strip()
        name = f"csTimer {name}" if not name or name.isdigit() else name
        target, sname = mode, name
        practice = _practice_target(name, case_names)
        if practice:
            target, sname = practice
        for s in solves:
            try:
                (penalty_ms, time_ms), scramble = s[0][:2], s[1] if len(s) > 1 else ""
                comment = s[2] if len(s) > 2 else ""
                stamp = s[3] if len(s) > 3 else time.time()
            except (TypeError, ValueError, IndexError):
                skipped += 1
                continue
            penalty = "dnf" if penalty_ms == -1 else "+2" if penalty_ms and penalty_ms > 0 else None
            seconds = max(0.0, float(time_ms) / 1000)
            ts = datetime.fromtimestamp(float(stamp)).strftime(TS_FORMAT)
            k = (target, round(seconds, 3), ts)
            if k in existing:
                skipped += 1
                continue
            note, case = (comment or "").strip() or None, None
            if target != "full":
                case, _, rest = (note or "").partition(" · ")
                if case not in case_names[target]:
                    skipped += 1
                    continue
                note = rest.strip() or None
            session = _session_for(db, target, sname, cache)
            db.add_imported(target, session, case, seconds, penalty, bool(note), note,
                            scramble or None, ts)
            existing.add(k)
            added += 1
    db.conn.commit()
    created = sum(len(db.list_sessions(m)) for m in MODES) - before
    log.info("imported csTimer file: %d added, %d skipped, %d new sessions", added, skipped, created)
    return {"format": "cstimer", "added": added, "skipped": skipped, "sessions": created}


# ---------------------------------------------------------------------------
# Either format, with a safety copy first
# ---------------------------------------------------------------------------
def detect_format(data):
    if isinstance(data, dict) and data.get("app") == "cube-timer":
        return "cube-timer"
    if is_cstimer(data):
        return "cstimer"
    return None


def backup_before_import(db):
    """Copy the database file next to it; returns the copy's path."""
    db.conn.commit()            # a pending write would make the backup wait forever
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    dest_path, k = db.path.with_name(f"{db.path.stem}.before-import-{stamp}.db"), 1
    while dest_path.exists():
        k += 1
        dest_path = db.path.with_name(f"{db.path.stem}.before-import-{stamp}-{k}.db")
    dest = sqlite3.connect(str(dest_path))
    db.conn.backup(dest)
    dest.close()
    log.info("copied the database to %s before importing", dest_path.name)
    return dest_path


def import_any(db, data, mode="full", case_names=None):
    """Detect the format, copy the database, then merge. Returns the summary."""
    fmt_ = detect_format(data)
    if fmt_ is None:
        raise ImportProblem("This file is neither a Cube Timer backup nor a csTimer export.")
    copy = backup_before_import(db)
    summary = (import_backup(db, data, case_names) if fmt_ == "cube-timer"
               else import_cstimer(db, data, mode, case_names))
    return {**summary, "backup": copy.name}


def summary_text(s):
    """One line for the user, e.g. "Added 120 solves in 2 new sessions; 3 were already there."."""
    new = f" in {s['sessions']} new session{'s' if s['sessions'] != 1 else ''}" if s["sessions"] else ""
    skipped = f"; {s['skipped']} {'was' if s['skipped'] == 1 else 'were'} already there or unreadable" \
        if s["skipped"] else ""
    return f"Added {s['added']} solve{'s' if s['added'] != 1 else ''}{new}{skipped}."


__all__ = ["export_csv", "export_backup", "export_cstimer", "import_backup", "import_cstimer",
           "import_any", "detect_format", "summary_text", "ImportProblem"]
