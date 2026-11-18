#!/usr/bin/env python3
"""
Cube Timer - Rubik's Cube Practice Timer
Full solves, OLL training (57 cases), PLL training (21 cases)
Times stored in SQLite for progress tracking.

Requirements: pip install rich
"""

import math
import time
import sqlite3
import json
import logging
import os
import random
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

log = logging.getLogger("cube_timer.data")
LOG_FILE = Path(__file__).with_name("cube_timer.log")


def setup_logging():
    """
    Log to cube_timer.log next to the scripts (rotated at 512 KB, 2 old files
    kept). INFO by default; set CUBE_TIMER_DEBUG=1 for every selection change.
    Uncaught errors are logged too (the GUI also logs errors inside Tk callbacks,
    the web app errors inside requests and in the browser).
    """
    handler = RotatingFileHandler(LOG_FILE, maxBytes=512_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if os.environ.get("CUBE_TIMER_DEBUG") else logging.INFO)

    def excepthook(exc_type, exc, tb):
        log.critical("Uncaught error", exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)
    sys.excepthook = excepthook


try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box

    console = Console()
except ImportError:
    print("Please install rich:  pip install rich")
    sys.exit(1)


# =============================================================================
# OLL CASES  (57 cases)
# =============================================================================
OLL_CASES = [
    {"id":  1, "name": "OLL 1",  "group": "Dot",       "alg": "R U2 R2 F R F' U2 R' F R F'"},
    {"id":  2, "name": "OLL 2",  "group": "Dot",       "alg": "F R U R' U' F' f R U R' U' f'"},
    {"id":  3, "name": "OLL 3",  "group": "Dot",       "alg": "f U R U' R' f' U' F R U R' U' F'"},
    {"id":  4, "name": "OLL 4",  "group": "Dot",       "alg": "f R U R' U' f' U F R U R' U' F'"},
    {"id":  5, "name": "OLL 5",  "group": "Square",    "alg": "r' U2 R U R' U r"},
    {"id":  6, "name": "OLL 6",  "group": "Square",    "alg": "r U2 R' U' R U' r'"},
    {"id":  7, "name": "OLL 7",  "group": "Square",    "alg": "r U R' U R U2 r'"},
    {"id":  8, "name": "OLL 8",  "group": "Square",    "alg": "r' U' R U' R' U2 r"},
    {"id":  9, "name": "OLL 9",  "group": "Fish",      "alg": "R U R' U' R' F R2 U R' U' F'"},
    {"id": 10, "name": "OLL 10", "group": "Fish",      "alg": "R U R' U R' F R F' R U2 R'"},
    {"id": 11, "name": "OLL 11", "group": "Fish",      "alg": "r' R2 U R' U R U2 R' U M'"},
    {"id": 12, "name": "OLL 12", "group": "Fish",      "alg": "M' R' U' R U' R' U2 R U' M"},
    {"id": 13, "name": "OLL 13", "group": "Knight",    "alg": "F U R U' R2 F' R U R U' R'"},
    {"id": 14, "name": "OLL 14", "group": "Knight",    "alg": "R' F R U R' F' R F U' F'"},
    {"id": 15, "name": "OLL 15", "group": "Knight",    "alg": "r' U' r R' U' R U r' U r"},
    {"id": 16, "name": "OLL 16", "group": "Knight",    "alg": "r U r' R U R' U' r U' r'"},
    {"id": 17, "name": "OLL 17", "group": "Dot",       "alg": "F R' F' R2 r' U R U' R' U' M'"},
    {"id": 18, "name": "OLL 18", "group": "Dot",       "alg": "r U R' U R U2 r2 U' R U' R' U2 r"},
    {"id": 19, "name": "OLL 19", "group": "Dot",       "alg": "r' R U R U R' U' M' R' F R F'"},
    {"id": 20, "name": "OLL 20", "group": "Dot",       "alg": "M U R U R' U' M2 U R U' r'"},
    {"id": 21, "name": "OLL 21", "group": "Cross",     "alg": "R U2 R' U' R U R' U' R U' R'"},
    {"id": 22, "name": "OLL 22", "group": "Cross",     "alg": "R U2 R2 U' R2 U' R2 U2 R"},
    {"id": 23, "name": "OLL 23", "group": "Cross",     "alg": "R2 D' R U2 R' D R U2 R"},
    {"id": 24, "name": "OLL 24", "group": "Cross",     "alg": "r U R' U' r' F R F'"},
    {"id": 25, "name": "OLL 25", "group": "Cross",     "alg": "F' r U R' U' r' F R"},
    {"id": 26, "name": "OLL 26", "group": "Cross",     "alg": "R U2 R' U' R U' R'"},
    {"id": 27, "name": "OLL 27", "group": "Cross",     "alg": "R U R' U R U2 R'"},
    {"id": 28, "name": "OLL 28", "group": "Cross",     "alg": "r U R' U' r' R U R U' R'"},
    {"id": 29, "name": "OLL 29", "group": "Cross",     "alg": "R U R' U' R U' R' F' U' F R U R'"},
    {"id": 30, "name": "OLL 30", "group": "Cross",     "alg": "F R' F R2 U' R' U' R U R' F2"},
    {"id": 31, "name": "OLL 31", "group": "Cross",     "alg": "R' U' F U R U' R' F' R"},
    {"id": 32, "name": "OLL 32", "group": "Cross",     "alg": "S R U R' U' R' F R f'"},
    {"id": 33, "name": "OLL 33", "group": "Cross",     "alg": "R U R' U' R' F R F'"},
    {"id": 34, "name": "OLL 34", "group": "Cross",     "alg": "R U R2 U' R' F R U R U' F'"},
    {"id": 35, "name": "OLL 35", "group": "Fish",      "alg": "R U2 R2 F R F' R U2 R'"},
    {"id": 36, "name": "OLL 36", "group": "Fish",      "alg": "L' U' L U' L' U L U L F' L' F"},
    {"id": 37, "name": "OLL 37", "group": "Fish",      "alg": "F R U' R' U' R U R' F'"},
    {"id": 38, "name": "OLL 38", "group": "Fish",      "alg": "R U R' U R U' R' U' R' F R F'"},
    {"id": 39, "name": "OLL 39", "group": "T-shape",   "alg": "L F' L' U' L U F U' L'"},
    {"id": 40, "name": "OLL 40", "group": "T-shape",   "alg": "R' F R U R' U' F' U R"},
    {"id": 41, "name": "OLL 41", "group": "Lightning", "alg": "R U R' U R U2 R' F R U R' U' F'"},
    {"id": 42, "name": "OLL 42", "group": "Lightning", "alg": "R' U' R U' R' U2 R F R U R' U' F'"},
    {"id": 43, "name": "OLL 43", "group": "P-shape",   "alg": "R' U' F' U F R"},
    {"id": 44, "name": "OLL 44", "group": "P-shape",   "alg": "F U R U' R' F'"},
    {"id": 45, "name": "OLL 45", "group": "T-shape",   "alg": "F R U R' U' F'"},
    {"id": 46, "name": "OLL 46", "group": "T-shape",   "alg": "R' U' R' F R F' U R"},
    {"id": 47, "name": "OLL 47", "group": "L-shape",   "alg": "F' L' U' L U L' U' L U F"},
    {"id": 48, "name": "OLL 48", "group": "L-shape",   "alg": "F R U R' U' R U R' U' F'"},
    {"id": 49, "name": "OLL 49", "group": "L-shape",   "alg": "r U' r2 U r2 U r2 U' r"},
    {"id": 50, "name": "OLL 50", "group": "L-shape",   "alg": "r' U r2 U' r2 U' r2 U r'"},
    {"id": 51, "name": "OLL 51", "group": "Lightning", "alg": "f R U R' U' R U R' U' f'"},
    {"id": 52, "name": "OLL 52", "group": "Lightning", "alg": "R U R' U R U' B U' B' R'"},
    {"id": 53, "name": "OLL 53", "group": "W-shape",   "alg": "r' U' R U' R' U R U' R' U2 r"},
    {"id": 54, "name": "OLL 54", "group": "W-shape",   "alg": "r U R' U R U' R' U R U2 r'"},
    {"id": 55, "name": "OLL 55", "group": "C-shape",   "alg": "R U2 R2 U' R U' R' U2 F R F'"},
    {"id": 56, "name": "OLL 56", "group": "C-shape",   "alg": "r' U' r U' R' U R U' R' U R r' U r"},
    {"id": 57, "name": "OLL 57", "group": "Cross",     "alg": "R U R' U' M' U R U' r'"},
]

# =============================================================================
# PLL CASES  (21 cases)
# =============================================================================
PLL_CASES = [
    {"id":  1, "name": "Aa Perm", "group": "Corners Only",   "alg": "x R' U R' D2 R U' R' D2 R2 x'"},
    {"id":  2, "name": "Ab Perm", "group": "Corners Only",   "alg": "x R2 D2 R U R' D2 R U' R x'"},
    {"id":  3, "name": "E Perm",  "group": "Corners Only",   "alg": "x' R U' R' D R U R' D' R U R' D R U' R' D' x"},
    {"id":  4, "name": "F Perm",  "group": "Adj + Corners",  "alg": "R' U' F' R U R' U' R' F R2 U' R' U' R U R' U R"},
    {"id":  5, "name": "Ga Perm", "group": "G Perms",        "alg": "R2 U R' U R' U' R U' R2 U' D R' U R D'"},
    {"id":  6, "name": "Gb Perm", "group": "G Perms",        "alg": "R' U' R U D' R2 U R' U R U' R U' R2 D"},
    {"id":  7, "name": "Gc Perm", "group": "G Perms",        "alg": "R2 U' R U' R U R' U R2 U D' R U' R' D"},
    {"id":  8, "name": "Gd Perm", "group": "G Perms",        "alg": "R U R' U' D R2 U' R U' R' U R' U R2 D'"},
    {"id":  9, "name": "H Perm",  "group": "Edges Only",     "alg": "M2 U M2 U2 M2 U M2"},
    {"id": 10, "name": "Ja Perm", "group": "J Perms",        "alg": "x R2 F R F' R U2 r' U r U2 x'"},
    {"id": 11, "name": "Jb Perm", "group": "J Perms",        "alg": "R U R' F' R U R' U' R' F R2 U' R'"},
    {"id": 12, "name": "Na Perm", "group": "N Perms",        "alg": "R U R' U R U R' F' R U R' U' R' F R2 U' R' U2 R U' R'"},
    {"id": 13, "name": "Nb Perm", "group": "N Perms",        "alg": "R' U R U' R' F' U' F R U R' F R' F' R U' R"},
    {"id": 14, "name": "Ra Perm", "group": "R Perms",        "alg": "R U' R' U' R U R D R' U' R D' R' U2 R'"},
    {"id": 15, "name": "Rb Perm", "group": "R Perms",        "alg": "R' U2 R U2 R' F R U R' U' R' F' R2"},
    {"id": 16, "name": "T Perm",  "group": "Adj + Corners",  "alg": "R U R' U' R' F R2 U' R' U' R U R' F'"},
    {"id": 17, "name": "Ua Perm", "group": "Edges Only",     "alg": "R U' R U R U R U' R' U' R2"},
    {"id": 18, "name": "Ub Perm", "group": "Edges Only",     "alg": "R2 U R U R' U' R' U' R' U R'"},
    {"id": 19, "name": "V Perm",  "group": "Adj + Corners",  "alg": "R' U R' U' y R' F' R2 U' R' U R' F R F"},
    {"id": 20, "name": "Y Perm",  "group": "Adj + Corners",  "alg": "F R U' R' U' R U R' F' R U R' U' R' F R F'"},
    {"id": 21, "name": "Z Perm",  "group": "Edges Only",     "alg": "M' U M2 U M2 U M' U2 M2"},
]


# =============================================================================
# SCRAMBLE GENERATOR
# =============================================================================
_FACES = ["R", "L", "U", "D", "F", "B"]
_MODS = ["", "'", "2"]
_OPPOSITE = {"R": "L", "L": "R", "U": "D", "D": "U", "F": "B", "B": "F"}


def generate_scramble(length=20):
    """WCA-style random scramble — no redundant or cancelling moves."""
    scramble = []
    last = None
    second_last = None
    for _ in range(length):
        pool = [f for f in _FACES if f != last]
        if second_last and _OPPOSITE.get(second_last) == last:
            pool = [f for f in pool if f != second_last]
        face = random.choice(pool)
        scramble.append(face + random.choice(_MODS))
        second_last, last = last, face
    return " ".join(scramble)


_AUF = ["", "U", "U2", "U'"]
_U_TURNS = {"U": 1, "U2": 2, "U'": 3}


def invert_alg(alg):
    """The algorithm that undoes the given one."""
    out = []
    for tok in reversed(alg.split()):
        if "2" in tok:
            out.append(tok.rstrip("'"))
        elif tok.endswith("'"):
            out.append(tok[:-1])
        else:
            out.append(tok + "'")
    return " ".join(out)


def case_scramble(alg):
    """
    Setup scramble for a last-layer case. Applied to a solved cube it leaves
    exactly the case that `alg` solves, seen from a random angle: a random turn
    of the top layer is added before and after, so the case has to be
    recognised rather than always arriving the same way round.
    """
    moves = [random.choice(_AUF)] + invert_alg(alg).split() + [random.choice(_AUF)]
    return _merge_u(moves)


_SCRAMBLE_FILE = Path(__file__).with_name("case_scrambles.json")
_scramble_bank = None


def setup_scramble(case):
    """
    Scramble for practising a case. Uses a solver-made scramble from
    case_scrambles.json (see make_scrambles.py) with an extra random turn of
    the top layer; falls back to case_scramble() if the case has none.
    """
    global _scramble_bank
    if _scramble_bank is None:
        try:
            _scramble_bank = json.loads(_SCRAMBLE_FILE.read_text())["scrambles"]
        except (OSError, ValueError, KeyError) as exc:
            log.warning("no solver scrambles (%s); using reversed algorithms", exc)
            _scramble_bank = {}
    options = _scramble_bank.get(case["name"])
    if not options:
        return case_scramble(case["alg"])
    return _merge_u(random.choice(options).split() + [random.choice(_AUF)])


def _merge_u(moves):
    """Join moves, combining neighbouring U turns (U + U2 -> U')."""
    merged = []
    for m in moves:
        if not m:
            continue
        if merged and m in _U_TURNS and merged[-1] in _U_TURNS:
            total = (_U_TURNS[merged.pop()] + _U_TURNS[m]) % 4
            if total:
                merged.append(_AUF[total])
        else:
            merged.append(m)
    return " ".join(merged)


# =============================================================================
# TIME UTILITIES
# =============================================================================
DNF = math.inf                      # a DNF counts as infinitely slow in averages
PENALTIES = (None, "+2", "dnf")      # times.penalty: none, plus two seconds, did not finish

# Timer settings, shared by the web app and the GUI (table settings, JSON values).
# Full Solve inspection is WCA's 15 s with its penalties; OLL / PLL inspection
# is a plain countdown of inspection_seconds.<mode>, with no penalties.
WCA_INSPECTION = 15
DEFAULT_SETTINGS = {
    "inspection.full": False,
    "inspection.oll": False,
    "inspection.pll": False,
    "inspection_seconds.oll": 8,
    "inspection_seconds.pll": 8,
    "inspection_voice": False,       # say "eight seconds" / "twelve seconds" (WCA)
    "hold_to_start": True,
    "hold_ms": 300,
}
SETTING_CHOICES = {
    "inspection_seconds.oll": (5, 8, 12, 15),
    "inspection_seconds.pll": (5, 8, 12, 15),
    "hold_ms": (300, 550, 1000),
}


def check_setting(key, value):
    """None if value is allowed for key, else what is wrong."""
    if key not in DEFAULT_SETTINGS:
        return f"unknown setting {key!r}"
    if type(value) is not type(DEFAULT_SETTINGS[key]):
        return f"{key} must be a {type(DEFAULT_SETTINGS[key]).__name__}"
    if key in SETTING_CHOICES and value not in SETTING_CHOICES[key]:
        return f"{key} must be one of {SETTING_CHOICES[key]}"
    return None


def effective(seconds, penalty):
    """A solve's time once its penalty is applied (DNF for a DNF)."""
    if penalty == "dnf":
        return DNF
    return seconds + 2 if penalty == "+2" else seconds


def fmt(seconds):
    """Format seconds as M:SS.cc or SS.cc ("DNF" for a DNF, "—" for None)."""
    if seconds is None:
        return "—"
    if seconds == DNF:
        return "DNF"
    if seconds < 60:
        return f"{seconds:.2f}"
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m}:{s:05.2f}"


def fmt_solve(seconds, penalty):
    """A solve as shown in a history: 12.34, 14.34+ (a +2) or DNF."""
    if penalty == "dnf":
        return "DNF"
    return fmt(effective(seconds, penalty)) + ("+" if penalty == "+2" else "")


def calc_ao(times, n):
    """
    Average of the latest n times (newest first), trimming the best and worst
    5% (at least one each side), as WCA and csTimer do. A DNF (math.inf) counts
    as the worst time, so one DNF is trimmed and two make the average a DNF.
    Returns None if there are fewer than n times.
    """
    if len(times) < n:
        return None
    recent = sorted(times[:n])
    if n <= 2:
        return sum(recent) / n
    trim = max(1, math.ceil(n * 0.05))
    kept = recent[trim:-trim]
    return sum(kept) / len(kept)


def best_ao(times, n):
    """The best average of n over every run of n consecutive times, or None."""
    best = None
    for i in range(len(times) - n + 1):
        a = calc_ao(times[i:i + n], n)
        if best is None or a < best:
            best = a
    return best


def solve_stats(times):
    """
    Summary of a list of times, newest first, penalties applied (DNF = math.inf):
    count, dnf, best, worst, mean (DNFs left out of these three), current ao5 /
    ao12 / ao50 / ao100 and the best ao5 / ao12. Missing values are None.
    """
    ok = [t for t in times if t != DNF]
    stats = {
        "count": len(times),
        "dnf":   len(times) - len(ok),
        "best":  min(ok) if ok else None,
        "worst": max(ok) if ok else None,
        "mean":  sum(ok) / len(ok) if ok else None,
    }
    for n in (5, 12, 50, 100):
        stats[f"ao{n}"] = calc_ao(times, n)
    for n in (5, 12):
        stats[f"best_ao{n}"] = best_ao(times, n)
    return stats


# =============================================================================
# DATABASE
# =============================================================================
# A solve that has no DNF, and its time with any +2 added, for SQL queries.
_NOT_DNF   = "(penalty IS NULL OR penalty != 'dnf')"
_EFFECTIVE = "(seconds + CASE WHEN penalty = '+2' THEN 2 ELSE 0 END)"
_SOLVE_COLS = "id,case_name,seconds,penalty,flagged,note,ts,session"


class Database:
    """
    The SQLite store shared by the terminal app, the GUI and the web app.

    Every attempt is a row in `times`. Besides its raw time it has a penalty
    (None, "+2" or "dnf"), a flag with an optional note, and the number of the
    practice session it belongs to. Each mode has its own current session
    (table `sessions`); new_session() starts the next one, so "session" stats
    cover the attempts since then and "all time" stats cover every attempt.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.conn = sqlite3.connect(str(path))
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS times (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                mode      TEXT    NOT NULL,
                case_name TEXT,
                seconds   REAL    NOT NULL,
                scramble  TEXT,
                ts        TEXT    DEFAULT (datetime('now','localtime'))
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS selected_cases (
                mode      TEXT NOT NULL,
                case_name TEXT NOT NULL,
                PRIMARY KEY (mode, case_name)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS case_status (
                mode      TEXT NOT NULL,
                case_name TEXT NOT NULL,
                status    TEXT NOT NULL,
                PRIMARY KEY (mode, case_name)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_groups (
                mode       TEXT NOT NULL,
                group_name TEXT NOT NULL,
                case_name  TEXT NOT NULL,
                PRIMARY KEY (mode, group_name, case_name)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                mode    TEXT PRIMARY KEY,
                current INTEGER NOT NULL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS session_list (
                mode    TEXT    NOT NULL,
                number  INTEGER NOT NULL,
                name    TEXT    NOT NULL,
                created TEXT    DEFAULT (datetime('now','localtime')),
                PRIMARY KEY (mode, number)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        self._add_solve_columns()
        self._add_session_names()
        self.conn.commit()

    def _add_session_names(self):
        """Name every session that has times or is selected but has no name yet."""
        cur = self.conn.execute("""
            INSERT OR IGNORE INTO session_list (mode, number, name)
            SELECT mode, n, 'Session ' || n FROM (
                SELECT DISTINCT mode, session AS n FROM times
                UNION SELECT mode, current FROM sessions)
        """)
        if cur.rowcount > 0:
            log.info("named %d existing session(s)", cur.rowcount)

    def _add_solve_columns(self):
        """Give an older database the penalty / flag / note / session columns."""
        have = {r[1] for r in self.conn.execute("PRAGMA table_info(times)")}
        new = [(name, decl) for name, decl in (
            ("penalty", "TEXT"),
            ("flagged", "INTEGER NOT NULL DEFAULT 0"),
            ("note",    "TEXT"),
            ("session", "INTEGER NOT NULL DEFAULT 1"),
        ) if name not in have]
        if not new:
            return
        count = self.conn.execute("SELECT COUNT(*) FROM times").fetchone()[0]
        if count:
            # one copy of the old file, in case anything goes wrong
            backup = self.path.with_name(self.path.stem + ".before-sessions.db")
            if not backup.exists():
                dest = sqlite3.connect(str(backup))
                self.conn.backup(dest)
                dest.close()
                log.info("backed up %s to %s before adding columns", self.path.name, backup.name)
        for name, decl in new:
            self.conn.execute(f"ALTER TABLE times ADD COLUMN {name} {decl}")
        log.info("added columns %s to times (%d rows)", [n for n, _ in new], count)

    # --- sessions -----------------------------------------------------------
    # Each mode has a list of named sessions (session_list) and one selected
    # session (sessions.current). New attempts go into the selected session,
    # and "session" stats and histories cover it.
    SESSION_NAME_MAX = 40

    def current_session(self, mode):
        """Number of the selected session in this mode."""
        row = self.conn.execute(
            "SELECT current FROM sessions WHERE mode=?", (mode,)).fetchone()
        return row[0] if row else 1

    def _ensure_session(self, mode, n):
        self.conn.execute(
            "INSERT OR IGNORE INTO session_list (mode,number,name) VALUES (?,?,?)",
            (mode, n, f"Session {n}"))

    def _clean_name(self, name, n):
        return (name or "").strip()[:self.SESSION_NAME_MAX].strip() or f"Session {n}"

    def list_sessions(self, mode):
        """[(number, name, solve count, last solve ts or None)], oldest first."""
        self._ensure_session(mode, self.current_session(mode))
        # sqlite3 opens a write transaction even for an ignored INSERT; never
        # leave it open, or the other app (and backups) would wait on the lock
        if self.conn.in_transaction:
            self.conn.commit()
        return self.conn.execute("""
            SELECT l.number, l.name, COUNT(t.id), MAX(t.ts)
            FROM session_list l
            LEFT JOIN times t ON t.mode = l.mode AND t.session = l.number
            WHERE l.mode = ? GROUP BY l.number ORDER BY l.number""", (mode,)).fetchall()

    def session_name(self, mode, n=None):
        n = self.current_session(mode) if n is None else n
        row = self.conn.execute("SELECT name FROM session_list WHERE mode=? AND number=?",
                                (mode, n)).fetchone()
        return row[0] if row else f"Session {n}"

    def new_session(self, mode, name=None):
        """Create a session after every existing one and select it; returns its number."""
        n = self.create_session(mode, name)
        self.conn.execute(
            "INSERT OR REPLACE INTO sessions (mode,current) VALUES (?,?)", (mode, n))
        self.conn.commit()
        log.info("%s: started session %d (%s)", mode, n, self.session_name(mode, n))
        return n

    def create_session(self, mode, name):
        """Add a named session after every existing one without selecting it (imports)."""
        row = self.conn.execute("""
            SELECT MAX(n) FROM (
                SELECT number AS n FROM session_list WHERE mode=?
                UNION SELECT session FROM times WHERE mode=?
                UNION SELECT current FROM sessions WHERE mode=?)""",
                                (mode, mode, mode)).fetchone()
        n = (row[0] or 0) + 1
        self.conn.execute("INSERT INTO session_list (mode,number,name) VALUES (?,?,?)",
                          (mode, n, self._clean_name(name, n)))
        return n

    def select_session(self, mode, n):
        """Make an existing session the one new attempts go into."""
        if not self.conn.execute("SELECT 1 FROM session_list WHERE mode=? AND number=?",
                                 (mode, n)).fetchone():
            raise KeyError(f"no session {n} in {mode}")
        self.conn.execute(
            "INSERT OR REPLACE INTO sessions (mode,current) VALUES (?,?)", (mode, n))
        self.conn.commit()
        log.info("%s: selected session %d", mode, n)

    def rename_session(self, mode, n, name):
        self._ensure_session(mode, n)
        self.conn.execute("UPDATE session_list SET name=? WHERE mode=? AND number=?",
                          (self._clean_name(name, n), mode, n))
        self.conn.commit()
        log.info("%s: session %d renamed to %r", mode, n, self.session_name(mode, n))

    def delete_session(self, mode, n):
        """
        Delete a session and its attempts; returns how many attempts went.
        The last session of a mode can't be deleted. Deleting the selected one
        selects the newest remaining session.
        """
        numbers = [r[0] for r in self.list_sessions(mode)]
        if n not in numbers:
            raise KeyError(f"no session {n} in {mode}")
        if len(numbers) == 1:
            raise ValueError("the last session can't be deleted")
        cur = self.conn.execute("DELETE FROM times WHERE mode=? AND session=?", (mode, n))
        self.conn.execute("DELETE FROM session_list WHERE mode=? AND number=?", (mode, n))
        if self.current_session(mode) == n:
            self.conn.execute("INSERT OR REPLACE INTO sessions (mode,current) VALUES (?,?)",
                              (mode, max(x for x in numbers if x != n)))
        self.conn.commit()
        log.info("%s: deleted session %d with %d attempt(s)", mode, n, cur.rowcount)
        return cur.rowcount

    # --- single solves ----------------------------------------------------------
    def solves(self, mode, scope="all", case_name=None, flagged_only=False, limit=None):
        """
        Attempts newest first, as tuples (id, case_name, seconds, penalty,
        flagged, note, ts, session). scope is "session" or "all".
        """
        sql, args = f"SELECT {_SOLVE_COLS} FROM times WHERE mode=?", [mode]
        if scope == "session":
            sql += " AND session=?"
            args.append(self.current_session(mode))
        if case_name:
            sql += " AND case_name=?"
            args.append(case_name)
        if flagged_only:
            sql += " AND flagged=1"
        sql += " ORDER BY id DESC"
        if limit:
            sql += " LIMIT ?"
            args.append(limit)
        return self.conn.execute(sql, args).fetchall()

    def solve(self, solve_id):
        """One attempt as (mode, id, case_name, seconds, penalty, flagged, note, ts, session), or None."""
        return self.conn.execute(
            f"SELECT mode,{_SOLVE_COLS} FROM times WHERE id=?", (solve_id,)).fetchone()

    def set_penalty(self, solve_id, penalty):
        if penalty not in PENALTIES:
            raise ValueError(f"unknown penalty {penalty!r}")
        self.conn.execute("UPDATE times SET penalty=? WHERE id=?", (penalty, solve_id))
        self.conn.commit()
        log.info("solve %s: penalty %s", solve_id, penalty or "none")

    def set_flag(self, solve_id, flagged, note=None):
        """Flag a solve (with an optional note) or unflag it (which drops the note)."""
        note = (note or "").strip()[:200] or None
        self.conn.execute("UPDATE times SET flagged=?, note=? WHERE id=?",
                          (1 if flagged else 0, note if flagged else None, solve_id))
        self.conn.commit()
        log.info("solve %s: %s", solve_id, f"flagged ({note})" if flagged else "unflagged")

    def delete_solve(self, solve_id):
        cur = self.conn.execute("DELETE FROM times WHERE id=?", (solve_id,))
        self.conn.commit()
        log.info("deleted solve %s", solve_id)
        return cur.rowcount > 0

    def solve_table(self, mode, scope="all", flagged_only=False, limit=None, case_name=None):
        """
        (rows, total) for a statistics table or the progress chart: rows are
        dicts, newest first, with the solve's fields plus `time` (penalty
        applied) and the ao5 / ao12 ending at that solve. The averages are
        worked out over every solve in scope (one case's, with case_name), so
        they are right even when only flagged solves are listed.
        """
        all_rows = self.solves(mode, scope, case_name=case_name)
        times = [effective(r[2], r[3]) for r in all_rows]
        out = []
        for i, r in enumerate(all_rows):
            if flagged_only and not r[4]:
                continue
            out.append({"n": len(all_rows) - i, "id": r[0], "case": r[1], "seconds": r[2], "penalty": r[3],
                        "flagged": bool(r[4]), "note": r[5], "ts": r[6], "session": r[7],
                        "time": times[i],
                        "ao5": calc_ao(times[i:], 5), "ao12": calc_ao(times[i:], 12)})
            if limit and len(out) >= limit:
                break
        return out, len(all_rows)

    def stats(self, mode, scope="all"):
        """solve_stats() of every attempt in this mode, or of the current session."""
        return solve_stats([effective(r[2], r[3]) for r in self.solves(mode, scope)])

    def get_custom_groups(self, mode):
        """{group name: set of case names} for the user's own groups."""
        groups = {}
        for name, case in self.conn.execute(
                "SELECT group_name,case_name FROM custom_groups WHERE mode=? "
                "ORDER BY rowid", (mode,)):
            groups.setdefault(name, set()).add(case)
        return groups

    def save_custom_group(self, mode, name, cases):
        """Create or replace a custom group."""
        self.conn.execute(
            "DELETE FROM custom_groups WHERE mode=? AND group_name=?", (mode, name))
        self.conn.executemany(
            "INSERT INTO custom_groups (mode,group_name,case_name) VALUES (?,?,?)",
            [(mode, name, c) for c in cases])
        self.conn.commit()

    def delete_custom_group(self, mode, name):
        self.conn.execute(
            "DELETE FROM custom_groups WHERE mode=? AND group_name=?", (mode, name))
        self.conn.commit()

    def set_statuses(self, mode, names, status):
        """Give several cases the same status in one go."""
        self.conn.executemany(
            "DELETE FROM case_status WHERE mode=? AND case_name=?",
            [(mode, n) for n in names])
        if status != "unlearned":
            self.conn.executemany(
                "INSERT INTO case_status (mode,case_name,status) VALUES (?,?,?)",
                [(mode, n, status) for n in names])
        self.conn.commit()

    def get_statuses(self, mode):
        """{case name: status} for cases marked learning / finished."""
        cur = self.conn.execute(
            "SELECT case_name,status FROM case_status WHERE mode=?", (mode,))
        return dict(cur.fetchall())

    def set_status(self, mode, name, status):
        if status == "unlearned":
            self.conn.execute(
                "DELETE FROM case_status WHERE mode=? AND case_name=?", (mode, name))
        else:
            self.conn.execute(
                "INSERT OR REPLACE INTO case_status (mode,case_name,status) VALUES (?,?,?)",
                (mode, name, status))
        self.conn.commit()

    def recent_means(self, mode, n=5):
        """{case name: mean of its latest n times}."""
        cur = self.conn.execute(
            f"SELECT case_name,{_EFFECTIVE} FROM times WHERE mode=? AND case_name IS NOT NULL "
            f"AND {_NOT_DNF} ORDER BY rowid DESC", (mode,))
        latest = {}
        for name, seconds in cur:
            times = latest.setdefault(name, [])
            if len(times) < n:
                times.append(seconds)
        return {name: sum(t) / len(t) for name, t in latest.items()}

    def get_selected(self, mode):
        """Names of the cases picked for practice in this mode."""
        cur = self.conn.execute(
            "SELECT case_name FROM selected_cases WHERE mode=?", (mode,))
        return {r[0] for r in cur.fetchall()}

    def set_selected(self, mode, names):
        self.conn.execute("DELETE FROM selected_cases WHERE mode=?", (mode,))
        self.conn.executemany(
            "INSERT INTO selected_cases (mode,case_name) VALUES (?,?)",
            [(mode, n) for n in names],
        )
        self.conn.commit()

    def recent(self, mode, limit=40):
        """Latest attempts in a mode, newest first: (case_name, time, ts), penalty applied."""
        cur = self.conn.execute(
            "SELECT case_name,seconds,penalty,ts FROM times WHERE mode=? ORDER BY rowid DESC LIMIT ?",
            (mode, limit),
        )
        return [(c, effective(s, p), ts) for c, s, p, ts in cur]

    def add(self, mode, seconds, case_name=None, scramble=None, penalty=None):
        """Record an attempt in the selected session; returns its id.
        penalty is None, "+2" or "dnf" (e.g. from overrunning WCA inspection)."""
        if penalty not in PENALTIES:
            raise ValueError(f"unknown penalty {penalty!r}")
        session = self.current_session(mode)
        self._ensure_session(mode, session)
        cur = self.conn.execute(
            "INSERT INTO times (mode,case_name,seconds,scramble,session,penalty) "
            "VALUES (?,?,?,?,?,?)",
            (mode, case_name, seconds, scramble, session, penalty),
        )
        self.conn.commit()
        return cur.lastrowid

    def add_imported(self, mode, session, case_name, seconds, penalty, flagged, note,
                     scramble, ts):
        """Insert an attempt from an import with its own session and date (no commit;
        cube_io commits once at the end)."""
        if penalty not in PENALTIES:
            raise ValueError(f"unknown penalty {penalty!r}")
        self._ensure_session(mode, session)
        note = (note or "").strip()[:200] or None
        self.conn.execute(
            "INSERT INTO times (mode,case_name,seconds,scramble,ts,session,penalty,flagged,note) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (mode, case_name, seconds, scramble, ts, session, penalty,
             1 if flagged else 0, note if flagged else None))

    # --- settings ----------------------------------------------------------------
    def get_settings(self):
        """Every setting: the saved values over DEFAULT_SETTINGS."""
        out = dict(DEFAULT_SETTINGS)
        for key, value in self.conn.execute("SELECT key,value FROM settings"):
            if key in out:
                try:
                    out[key] = json.loads(value)
                except ValueError:
                    pass
        return out

    def set_setting(self, key, value):
        """Save one setting; check_setting() says whether the value is allowed."""
        problem = check_setting(key, value)
        if problem:
            raise ValueError(problem)
        self.conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)",
                          (key, json.dumps(value)))
        self.conn.commit()
        log.info("setting %s = %r", key, value)

    def get(self, mode, case_name=None, limit=100):
        """Latest (time, ts) pairs, newest first; time has the penalty applied (DNF = inf)."""
        if case_name:
            cur = self.conn.execute(
                "SELECT seconds,penalty,ts FROM times WHERE mode=? AND case_name=? "
                "ORDER BY rowid DESC LIMIT ?",
                (mode, case_name, limit),
            )
        else:
            cur = self.conn.execute(
                "SELECT seconds,penalty,ts FROM times WHERE mode=? ORDER BY rowid DESC LIMIT ?",
                (mode, limit),
            )
        return [(effective(s, p), ts) for s, p, ts in cur]

    def case_summary(self, mode):
        cur = self.conn.execute(
            f"SELECT case_name,COUNT(*),"
            f"MIN(CASE WHEN {_NOT_DNF} THEN {_EFFECTIVE} END),"
            f"AVG(CASE WHEN {_NOT_DNF} THEN {_EFFECTIVE} END) "
            "FROM times WHERE mode=? GROUP BY case_name ORDER BY case_name",
            (mode,),
        )
        return cur.fetchall()

    def delete_last(self, mode, case_name=None):
        """Delete the newest attempt of the selected session (optionally of one case)."""
        session = self.current_session(mode)
        if case_name:
            cur = self.conn.execute(
                "SELECT id FROM times WHERE mode=? AND session=? AND case_name=? "
                "ORDER BY rowid DESC LIMIT 1",
                (mode, session, case_name),
            )
        else:
            cur = self.conn.execute(
                "SELECT id FROM times WHERE mode=? AND session=? ORDER BY rowid DESC LIMIT 1",
                (mode, session),
            )
        row = cur.fetchone()
        if row:
            self.conn.execute("DELETE FROM times WHERE id=?", (row[0],))
            self.conn.commit()
            log.info("deleted last %s time (id %s)", mode, row[0])
            return True
        return False

    def close(self):
        self.conn.close()


# =============================================================================
# TIMER
# =============================================================================
def run_timer():
    """
    Interactive timer.
    Press ENTER to start, ENTER to stop, 'q'+ENTER to cancel.
    Returns elapsed seconds, or None if cancelled.
    """
    console.print(
        "\n[dim]  ENTER to start  •  ENTER to stop  •  [bold]q[/bold]+ENTER to cancel[/dim]"
    )
    line = input().strip().lower()
    if line == "q":
        return None

    start = time.perf_counter()
    stop_evt = threading.Event()

    def _wait():
        input()
        stop_evt.set()

    threading.Thread(target=_wait, daemon=True).start()

    try:
        while not stop_evt.is_set():
            elapsed = time.perf_counter() - start
            sys.stdout.write(f"\r  \033[1;32m{fmt(elapsed)}\033[0m  ")
            sys.stdout.flush()
            time.sleep(0.05)
    except KeyboardInterrupt:
        return None

    final = time.perf_counter() - start
    sys.stdout.write(f"\r  \033[1;33m{fmt(final)}\033[0m  \n")
    sys.stdout.flush()
    return final


# =============================================================================
# DISPLAY HELPERS
# =============================================================================
def show_header():
    console.print(
        Panel("[bold cyan]CUBE TIMER[/bold cyan]  [dim]v1.0[/dim]", expand=False, style="cyan")
    )


def show_session(rows, title):
    """Print a table of recent times with rolling ao5/ao12."""
    if not rows:
        console.print("[dim]No times recorded yet.[/dim]")
        return

    all_t = [r[0] for r in rows]

    tbl = Table(title=title, box=box.SIMPLE_HEAVY, header_style="bold cyan", expand=False)
    tbl.add_column("#", style="dim", width=4)
    tbl.add_column("Time", justify="right", min_width=8)
    tbl.add_column("ao5",  justify="right", min_width=8)
    tbl.add_column("ao12", justify="right", min_width=8)
    tbl.add_column("Timestamp", style="dim")

    for i, (t, ts) in enumerate(rows):
        a5  = calc_ao(all_t[i:], 5)
        a12 = calc_ao(all_t[i:], 12)
        tbl.add_row(
            str(len(rows) - i),
            fmt(t),
            fmt(a5)  if a5  else "-",
            fmt(a12) if a12 else "-",
            ts,
        )
    console.print(tbl)

    # Summary stats panel
    ok    = [t for t in all_t if t != DNF]       # best and mean leave out DNFs
    best  = min(ok) if ok else DNF
    mean  = sum(ok) / len(ok) if ok else DNF
    ao5   = calc_ao(all_t, 5)
    ao12  = calc_ao(all_t, 12)
    ao50  = calc_ao(all_t, 50)
    ao100 = calc_ao(all_t, 100)

    lines = [f"Count: {len(all_t)}  Best: [green]{fmt(best)}[/green]  Mean: {fmt(mean)}"]
    if ao5:   lines.append(f"ao5: [cyan]{fmt(ao5)}[/cyan]")
    if ao12:  lines.append(f"ao12: [cyan]{fmt(ao12)}[/cyan]")
    if ao50:  lines.append(f"ao50: {fmt(ao50)}")
    if ao100: lines.append(f"ao100: {fmt(ao100)}")

    console.print(Panel("  ".join(lines), title="Stats", border_style="dim"))


def show_case_progress(db, mode, cases):
    """Full OLL or PLL progress table."""
    summary = {r[0]: r for r in db.case_summary(mode)}

    tbl = Table(
        title=f"{mode.upper()} Progress — all cases",
        box=box.SIMPLE_HEAVY,
        header_style="bold cyan",
        expand=False,
    )
    tbl.add_column("Case", style="bold", min_width=10)
    tbl.add_column("Group", min_width=12)
    tbl.add_column("Algorithm")
    tbl.add_column("N", justify="right", width=5)
    tbl.add_column("Best", justify="right", min_width=8)
    tbl.add_column("Avg",  justify="right", min_width=8)

    for case in cases:
        row = summary.get(case["name"])
        if row:
            n, best, avg = str(row[1]), fmt(row[2]), fmt(row[3])
        else:
            n, best, avg = "-", "-", "-"
        tbl.add_row(case["name"], case["group"], case["alg"], n, best, avg)

    console.print(tbl)


# =============================================================================
# MODES
# =============================================================================
def full_solve_mode(db):
    while True:
        console.clear()
        show_header()
        scramble = generate_scramble()
        console.print(Panel(
            f"[bold yellow]{scramble}[/bold yellow]",
            title="[bold]Scramble[/bold]",
            border_style="yellow",
        ))

        elapsed = run_timer()
        if elapsed is None:
            console.print("[dim]Cancelled.[/dim]")
        else:
            db.add("full", elapsed, scramble=scramble)
            console.print(f"\n  [bold green]Saved: {fmt(elapsed)}[/bold green]")

        console.print("\n[dim]  [n] next scramble   [s] session stats   [d] delete last   [q] menu[/dim]")
        c = input("> ").strip().lower()
        if c == "q":
            break
        elif c == "s":
            console.clear()
            show_session(db.get("full", limit=20), "Full Solve Session")
            input("\nENTER to continue...")
        elif c == "d":
            if db.delete_last("full"):
                console.print("[yellow]Last solve deleted.[/yellow]")
                time.sleep(0.8)


def oll_mode(db):
    group_filter = None
    case = None

    while True:
        console.clear()
        show_header()

        pool = OLL_CASES if not group_filter else [c for c in OLL_CASES if c["group"] == group_filter]
        case = random.choice(pool)

        console.print(Panel(
            f"[bold white]{case['name']}[/bold white]  [dim]{case['group']}[/dim]\n\n"
            f"[bold yellow]{case['alg']}[/bold yellow]",
            title="[bold cyan]OLL Case[/bold cyan]",
            border_style="cyan",
        ))
        console.print("[dim]  Set up this case on your cube, then time the execution.[/dim]")

        elapsed = run_timer()
        if elapsed is not None:
            db.add("oll", elapsed, case_name=case["name"])
            console.print(f"\n  [bold green]Saved: {fmt(elapsed)}[/bold green]")

        console.print(
            "\n[dim]  [n] next   [s] case stats   [a] all OLL stats   "
            "[p] pick case   [g] group filter   [d] delete last   [q] menu[/dim]"
        )
        c = input("> ").strip().lower()

        if c == "q":
            break
        elif c == "s":
            console.clear()
            show_session(db.get("oll", case_name=case["name"], limit=20), case["name"])
            input("\nENTER to continue...")
        elif c == "a":
            console.clear()
            show_case_progress(db, "oll", OLL_CASES)
            input("\nENTER to continue...")
        elif c == "p":
            _pick_oll(db)
        elif c == "g":
            _filter_oll_group(group_filter)
            groups = sorted({c["group"] for c in OLL_CASES})
            console.print("Groups: " + "  ".join(groups))
            console.print("[dim]Type a group name or [all] to clear filter[/dim]")
            g = input("Filter: ").strip()
            if g.lower() == "all":
                group_filter = None
            elif g in groups:
                group_filter = g
        elif c == "d":
            if case and db.delete_last("oll", case_name=case["name"]):
                console.print("[yellow]Last time deleted.[/yellow]")
                time.sleep(0.8)


def _pick_oll(db):
    console.print("\nOLL 1-57 — enter a number:")
    num = input("OLL #: ").strip()
    try:
        n = int(num)
        matches = [c for c in OLL_CASES if c["id"] == n]
        if not matches:
            return
        case = matches[0]
        console.print(Panel(
            f"[bold white]{case['name']}[/bold white]  [dim]{case['group']}[/dim]\n\n"
            f"[bold yellow]{case['alg']}[/bold yellow]",
            title="[bold cyan]OLL Case[/bold cyan]",
            border_style="cyan",
        ))
        elapsed = run_timer()
        if elapsed is not None:
            db.add("oll", elapsed, case_name=case["name"])
            console.print(f"  [bold green]Saved: {fmt(elapsed)}[/bold green]")
        input("ENTER to continue...")
    except ValueError:
        pass


def _filter_oll_group(current):
    if current:
        console.print(f"[dim]Current filter: {current}[/dim]")


def pll_mode(db):
    case = None

    while True:
        console.clear()
        show_header()

        case = random.choice(PLL_CASES)

        console.print(Panel(
            f"[bold white]{case['name']}[/bold white]  [dim]{case['group']}[/dim]\n\n"
            f"[bold yellow]{case['alg']}[/bold yellow]",
            title="[bold magenta]PLL Case[/bold magenta]",
            border_style="magenta",
        ))
        console.print("[dim]  Set up this case on your cube, then time the execution.[/dim]")

        elapsed = run_timer()
        if elapsed is not None:
            db.add("pll", elapsed, case_name=case["name"])
            console.print(f"\n  [bold green]Saved: {fmt(elapsed)}[/bold green]")

        console.print(
            "\n[dim]  [n] next   [s] case stats   [a] all PLL stats   "
            "[p] pick case   [d] delete last   [q] menu[/dim]"
        )
        c = input("> ").strip().lower()

        if c == "q":
            break
        elif c == "s":
            console.clear()
            show_session(db.get("pll", case_name=case["name"], limit=20), case["name"])
            input("\nENTER to continue...")
        elif c == "a":
            console.clear()
            show_case_progress(db, "pll", PLL_CASES)
            input("\nENTER to continue...")
        elif c == "p":
            _pick_pll(db)
        elif c == "d":
            if case and db.delete_last("pll", case_name=case["name"]):
                console.print("[yellow]Last time deleted.[/yellow]")
                time.sleep(0.8)


def _pick_pll(db):
    console.print("\nPLL cases:")
    for c in PLL_CASES:
        console.print(f"  {c['id']:2}. {c['name']}")
    num = input("PLL #: ").strip()
    try:
        n = int(num)
        matches = [c for c in PLL_CASES if c["id"] == n]
        if not matches:
            return
        case = matches[0]
        console.print(Panel(
            f"[bold white]{case['name']}[/bold white]  [dim]{case['group']}[/dim]\n\n"
            f"[bold yellow]{case['alg']}[/bold yellow]",
            title="[bold magenta]PLL Case[/bold magenta]",
            border_style="magenta",
        ))
        elapsed = run_timer()
        if elapsed is not None:
            db.add("pll", elapsed, case_name=case["name"])
            console.print(f"  [bold green]Saved: {fmt(elapsed)}[/bold green]")
        input("ENTER to continue...")
    except ValueError:
        pass


def stats_mode(db):
    while True:
        console.clear()
        show_header()
        console.print("\n[bold]Statistics[/bold]")
        console.print("  [1] Full Solve — session times")
        console.print("  [2] OLL — progress across all 57 cases")
        console.print("  [3] PLL — progress across all 21 cases")
        console.print("  [q] Back to menu")
        c = input("\n> ").strip().lower()
        if c == "q":
            break
        elif c == "1":
            console.clear()
            show_session(db.get("full", limit=50), "Full Solve — last 50")
            input("\nENTER to continue...")
        elif c == "2":
            console.clear()
            show_case_progress(db, "oll", OLL_CASES)
            input("\nENTER to continue...")
        elif c == "3":
            console.clear()
            show_case_progress(db, "pll", PLL_CASES)
            input("\nENTER to continue...")


# =============================================================================
# MAIN
# =============================================================================
def main():
    db_path = Path(__file__).parent / "cube_times.db"
    db = Database(db_path)

    try:
        while True:
            console.clear()
            show_header()
            console.print("\n  [1] Full Solve    — WCA scramble, full 3×3 timing")
            console.print("  [2] OLL Practice  — 57 cases, algorithm timing")
            console.print("  [3] PLL Practice  — 21 cases, algorithm timing")
            console.print("  [4] Statistics")
            console.print("  [q] Quit")
            c = input("\n> ").strip().lower()
            if c == "1":
                full_solve_mode(db)
            elif c == "2":
                oll_mode(db)
            elif c == "3":
                pll_mode(db)
            elif c == "4":
                stats_mode(db)
            elif c == "q":
                break
    except KeyboardInterrupt:
        pass
    finally:
        db.close()
        console.print("\n[dim]Goodbye![/dim]")


if __name__ == "__main__":
    main()
