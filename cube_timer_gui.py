#!/usr/bin/env python3
"""
Cube Timer GUI - Rubik's Cube Practice Timer
Modern GUI built with customtkinter.
Shares the same SQLite database (cube_times.db) as the CLI version.

Requirements: pip install customtkinter rich
"""

import logging
import random
import sys
import time
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from cube_timer import (
    DNF,
    OLL_CASES,
    PLL_CASES,
    Database,
    calc_ao,
    effective,
    fmt,
    fmt_solve,
    generate_scramble,
    setup_logging,
    setup_scramble,
)
from cube_diagram import CaseDiagram, case_weight

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CASES = {"oll": OLL_CASES, "pll": PLL_CASES}

C_SELECTED = "#00cc44"       # border of a case picked for practice
C_IDLE   = "gray55"
C_RUNNING = "#00cc44"
C_STOPPED = "#ffcc00"
C_PANEL   = "#2b2b2b"        # panel / card background (case diagrams sit on it)
C_CURRENT = "#454545"        # picker tile of the case being practised
SIDE_WIDTH = 262             # practice pages' right-hand column (picker / history)

C_DNF     = "#ff6b6b"        # a DNF in histories and tables
C_PLUS2   = "#ff9f1c"        # a +2
C_TEXT    = "#DCE4EE"        # ctk's label text colour, for plain tk labels
HISTORY   = 100              # attempts of the current session listed in a history

STATUSES = ["unlearned", "learning", "finished"]
STATUS_COLOR = {"unlearned": "gray50", "learning": "#ff9f1c", "finished": "#3fa7ff"}

log = logging.getLogger("cube_timer.gui")


def _px(widget, size):
    """Pixel size matching customtkinter's display scaling (for plain canvases)."""
    try:
        return round(size * ctk.ScalingTracker.get_widget_scaling(widget))
    except Exception:
        return size


# ---------------------------------------------------------------------------
# Timer base class  (shared state machine for Full / OLL / PLL screens)
# ---------------------------------------------------------------------------
class TimerScreenBase(ctk.CTkFrame):
    """
    Provides idle → running → stopped → idle state machine via timer_toggle().
    Subclasses must create self.timer_label and self.start_btn in _build_ui(),
    then implement _next() and _save_result(elapsed).
    """

    def __init__(self, parent, root, db):
        super().__init__(parent, fg_color="transparent")
        self.root   = root
        self.db     = db

        self._state       = "idle"
        self._start_time  = 0.0
        self._timer_id    = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------
    def timer_toggle(self, event=None):
        if self._state == "idle":
            self._start()
        elif self._state == "running":
            self._stop()
        elif self._state == "stopped":
            self._next()

    def _cancel_timer(self):
        """Called by the app when switching away from this screen."""
        if self._timer_id:
            self.root.after_cancel(self._timer_id)
            self._timer_id = None
        self._state = "idle"
        self._reset_display()

    # ------------------------------------------------------------------
    # Internal state transitions
    # ------------------------------------------------------------------
    def _start(self):
        self._start_time = time.perf_counter()
        self._state      = "running"
        self.start_btn.configure(text="Stop  [space]")
        self.timer_label.configure(text_color=C_RUNNING)
        self._tick()

    def _stop(self):
        if self._timer_id:
            self.root.after_cancel(self._timer_id)
            self._timer_id = None
        elapsed      = time.perf_counter() - self._start_time
        self._state  = "stopped"
        self.start_btn.configure(text="Next  [space]")
        self.timer_label.configure(text=fmt(elapsed), text_color=C_STOPPED)
        self._save_result(elapsed)

    def _tick(self):
        if self._state != "running":
            return
        elapsed = time.perf_counter() - self._start_time
        self.timer_label.configure(text=fmt(elapsed))
        self._timer_id = self.root.after(50, self._tick)

    def _reset_display(self):
        self.timer_label.configure(text="0.00", text_color=C_IDLE)
        self.start_btn.configure(text="Start  [space]")

    # ------------------------------------------------------------------
    # Case panel (OLL / PLL screens): picture on the left, text on the right
    # ------------------------------------------------------------------
    def _build_case_panel(self, case_panel):
        case_panel.configure(fg_color=C_PANEL)
        case_panel.grid_columnconfigure(0, weight=1)

        inner = ctk.CTkFrame(case_panel, fg_color="transparent")
        inner.grid(row=0, column=0, padx=16, pady=12)

        self.case_diagram = CaseDiagram(inner, size=_px(self, 112), bg=C_PANEL)
        self.case_diagram.grid(row=0, column=0, rowspan=3, padx=(0, 20))

        self.case_name_label = ctk.CTkLabel(
            inner, text="", font=ctk.CTkFont(size=18, weight="bold"))
        self.case_name_label.grid(row=0, column=1, pady=(6, 2))

        self.case_group_label = ctk.CTkLabel(
            inner, text="", font=ctk.CTkFont(size=12), text_color="gray55")
        self.case_group_label.grid(row=1, column=1, pady=(0, 4))

        self.case_alg_label = ctk.CTkLabel(
            inner, text="",
            font=ctk.CTkFont(family="Courier New", size=15),
            text_color="#ffcc00", wraplength=300,
        )
        self.case_alg_label.grid(row=2, column=1, pady=(0, 6))

        ctk.CTkLabel(inner, text="SCRAMBLE", height=16,
                     font=ctk.CTkFont(size=10), text_color="gray55").grid(
            row=3, column=0, columnspan=2, pady=(10, 0))
        self.case_scramble_label = ctk.CTkLabel(
            inner, text="", font=ctk.CTkFont(family="Consolas", size=15),
            wraplength=430, justify="center",
        )
        self.case_scramble_label.grid(row=4, column=0, columnspan=2)

    # ------------------------------------------------------------------
    # Subclass hooks
    # ------------------------------------------------------------------
    def _next(self):
        raise NotImplementedError

    def _save_result(self, elapsed):
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Sessions and single solves (shared by Full Solve, the trainers and Statistics)
# ---------------------------------------------------------------------------
def result_bar_text(times):
    """"Last │ Best │ ao5 │ ao12" for times newest first, penalties applied."""
    if not times:
        return ""
    ok = [t for t in times if t != DNF]
    parts = [f"Last: {fmt(times[0])}", f"Best: {fmt(min(ok)) if ok else 'DNF'}"]
    a5  = calc_ao(times, 5)
    a12 = calc_ao(times, 12)
    if a5:  parts.append(f"ao5: {fmt(a5)}")
    if a12: parts.append(f"ao12: {fmt(a12)}")
    return "   │   ".join(parts)


def solve_color(penalty):
    return C_DNF if penalty == "dnf" else C_PLUS2 if penalty == "+2" else None


class SolveActions:
    """
    +2 / DNF / OK, flag (with a note), note and delete for one solve, given as a
    Database.solves() tuple. on_change() runs after anything was changed.
    ask_note(prompt) (None = cancelled) and confirm(message) can be replaced in tests.
    """

    def __init__(self, db, on_change):
        self.db        = db
        self.on_change = on_change
        self.ask_note  = lambda prompt: ctk.CTkInputDialog(title="Flag solve", text=prompt).get_input()
        self.confirm   = lambda msg: messagebox.askyesno("Delete solve", msg)

    def run(self, solve, action):
        if solve is None:
            return False
        sid, case, seconds, penalty, flagged, note = solve[:6]
        if action == "ok":
            self.db.set_penalty(sid, None)
        elif action in ("+2", "dnf"):
            self.db.set_penalty(sid, None if penalty == action else action)
        elif action == "flag":
            if flagged:
                self.db.set_flag(sid, False)
            else:
                text = self.ask_note("Flag this solve. Note (optional):")
                if text is None:
                    return False
                self.db.set_flag(sid, True, text)
        elif action == "note":
            now = f"\n(now: {note})" if note else ""
            text = self.ask_note(f"Note for this solve:{now}")
            if text is None:
                return False
            self.db.set_flag(sid, True, text)
        elif action == "delete":
            what = fmt_solve(seconds, penalty) + (f" ({case})" if case else "")
            if not self.confirm(f"Delete the solve {what}?\nIt is removed from every statistic."):
                return False
            self.db.delete_solve(sid)
        else:
            raise ValueError(action)
        self.on_change()
        return True


class SolveButtons(ctk.CTkFrame):
    """A label and OK / +2 / DNF / Flag / Note / Delete buttons for one solve."""

    ACTIONS = [("ok", "OK", 40), ("+2", "+2", 40), ("dnf", "DNF", 46),
               ("flag", "⚑ Flag", 70), ("note", "Note…", 56), ("delete", "✕", 30)]

    def __init__(self, parent, on_action, actions=None):
        super().__init__(parent, fg_color="transparent")
        keep = actions or [a for a, _, _ in self.ACTIONS]
        self.label = ctk.CTkLabel(self, text="", height=26, font=ctk.CTkFont(size=12),
                                  text_color="gray60")
        self.label.grid(row=0, column=0, padx=(0, 6))
        self.buttons = {}
        for col, (act, text, width) in enumerate(
                [a for a in self.ACTIONS if a[0] in keep], start=1):
            btn = ctk.CTkButton(self, text=text, width=width, height=26,
                                font=ctk.CTkFont(size=12), fg_color="gray30",
                                hover_color="#6B0000" if act == "delete" else "gray40",
                                command=lambda a=act: on_action(a))
            btn.grid(row=0, column=col, padx=2)
            self.buttons[act] = btn
        self._shown = None

    def show(self, solve, label=""):
        """Highlight the solve's penalty and flag; disable everything for no solve."""
        state = (label, None if solve is None else (solve[3], bool(solve[4])))
        if state == self._shown:
            return
        self._shown = state
        self.label.configure(text=label)
        penalty, flagged = state[1] if solve is not None else (None, False)
        on = {"ok": solve is not None and penalty is None, "+2": penalty == "+2",
              "dnf": penalty == "dnf", "flag": flagged}
        for act, btn in self.buttons.items():
            btn.configure(state="disabled" if solve is None or (act == "note" and not flagged)
                          else "normal",
                          fg_color="#1f6aa5" if on.get(act) else "gray30")
        if "flag" in self.buttons:
            self.buttons["flag"].configure(text="⚑ Unflag" if flagged else "⚑ Flag")


STAT_ROWS = [("count", "Solves"), ("best", "Best"), ("worst", "Worst"), ("mean", "Mean"),
             ("ao5", "ao5"), ("ao12", "ao12"), ("ao50", "ao50"), ("ao100", "ao100"),
             ("best_ao5", "Best ao5"), ("best_ao12", "Best ao12")]


def stat_text(stats, key):
    if key == "count":
        return f"{stats['count']}  ({stats['dnf']} DNF)" if stats["dnf"] else str(stats["count"])
    return fmt(stats[key])


class StatsBlock(tk.Frame):
    """Session vs all-time summary as a small table of plain tk labels."""

    def __init__(self, parent, bg, compact=False):
        super().__init__(parent, bg=bg)
        family = ctk.ThemeManager.theme["CTkFont"]["family"]
        size   = -_px(parent, 12)
        self.rows = [r for r in STAT_ROWS if not compact or r[0] not in ("worst", "ao50")]
        head = dict(bg=bg, fg="#b3b3b3", font=(family, size, "bold"), anchor="w")
        self.session_head = tk.Label(self, text="Session", **head)
        self.session_head.grid(row=0, column=1, sticky="w", padx=(0, _px(parent, 18)))
        tk.Label(self, text="All time", **head).grid(row=0, column=2, sticky="w")
        self.cells = []
        for i, (_, label) in enumerate(self.rows, start=1):
            tk.Label(self, text=label, bg=bg, fg="gray55", font=(family, size), anchor="w").grid(
                row=i, column=0, sticky="w", padx=(0, _px(parent, 18)))
            pair = [tk.Label(self, text="", bg=bg, fg=C_TEXT, font=("Consolas", size), anchor="w")
                    for _ in range(2)]
            pair[0].grid(row=i, column=1, sticky="w")
            pair[1].grid(row=i, column=2, sticky="w")
            self.cells.append(pair)

    def update_stats(self, session_name, session, all_time):
        self.session_head.configure(text=session_name)
        for (key, _), (a, b) in zip(self.rows, self.cells):
            a.configure(text=stat_text(session, key))
            b.configure(text=stat_text(all_time, key))


class SessionPicker(ctk.CTkFrame):
    """
    The named sessions of one mode: a menu that selects one (new attempts go
    into it) and New / Rename / Delete. on_change() runs after any change.
    ask_name(prompt) (None = cancelled), confirm(message) and tell(message)
    can be replaced in tests.
    """

    def __init__(self, parent, db, mode, title, on_change=None):
        super().__init__(parent, fg_color="transparent")
        self.db        = db
        self.mode      = mode
        self.title     = title
        self.on_change = on_change
        self.ask_name  = lambda prompt: ctk.CTkInputDialog(title="Session", text=prompt).get_input()
        self.confirm   = lambda msg: messagebox.askyesno("Session", msg)
        self.tell      = lambda msg: messagebox.showinfo("Session", msg)
        self._numbers  = {}            # menu label -> session number
        self._shown    = None

        self.grid_columnconfigure(0, weight=1)
        self.menu = ctk.CTkOptionMenu(self, values=[""], height=28, dynamic_resizing=False,
                                      font=ctk.CTkFont(size=13, weight="bold"),
                                      command=self._on_pick)
        self.menu.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        for col, (text, cmd, width) in enumerate(
                [("New…", self.new_session, 52), ("Rename…", self.rename_session, 70),
                 ("Delete…", self.delete_session, 62)], start=1):
            ctk.CTkButton(self, text=text, width=width, height=26, font=ctk.CTkFont(size=12),
                          fg_color="gray30", hover_color="#6B0000" if text == "Delete…" else "gray40",
                          command=cmd).grid(row=0, column=col, padx=1)

    def set_mode(self, mode, title):
        self.mode, self.title, self._shown = mode, title, None
        self.refresh()

    def refresh(self):
        sessions = self.db.list_sessions(self.mode)
        current = self.db.current_session(self.mode)
        state = (self.mode, current, tuple(sessions))
        if state == self._shown:
            return
        self._shown = state
        self._numbers = {}
        for n, name, count, _last in sessions:
            label = f"{name}  ({count})"
            if label in self._numbers:
                label += f"  #{n}"
            self._numbers[label] = n
        self.menu.configure(values=list(self._numbers))
        self.menu.set(next(l for l, n in self._numbers.items() if n == current))

    def _on_pick(self, label):
        n = self._numbers.get(label)
        if n is not None and n != self.db.current_session(self.mode):
            self.select(n)

    def select(self, n):
        self.db.select_session(self.mode, n)
        self._changed()

    def new_session(self):
        numbers = [s[0] for s in self.db.list_sessions(self.mode)]
        name = self.ask_name(f"Name for the new {self.title} session (e.g. the cube you use):")
        if name is None:
            return None
        n = self.db.new_session(self.mode, name or f"Session {max(numbers) + 1}")
        self._changed()
        return n

    def rename_session(self):
        n = self.db.current_session(self.mode)
        name = self.ask_name(f"New name for “{self.db.session_name(self.mode, n)}”:")
        if not name or not name.strip():
            return False
        self.db.rename_session(self.mode, n, name)
        self._changed()
        return True

    def delete_session(self):
        sessions = self.db.list_sessions(self.mode)
        if len(sessions) < 2:
            self.tell("This is the only session, so it can't be deleted.")
            return False
        n = self.db.current_session(self.mode)
        count = next(s[2] for s in sessions if s[0] == n)
        what = f"Delete the session “{self.db.session_name(self.mode, n)}”"
        if not self.confirm(what + (f" and its {count} solve(s)?\nThey are removed from every "
                                    "statistic." if count else "?")):
            return False
        self.db.delete_session(self.mode, n)
        self._changed()
        return True

    def _changed(self):
        self.refresh()
        if self.on_change:
            self.on_change()


class SessionPanel(ctk.CTkFrame):
    """
    The current session of one mode: "Session N" with New session, the session
    and all-time stats, and the session's history. Clicking a solve selects it
    for the buttons at the bottom (the newest solve when none is selected).
    on_change() runs after the session or any solve changed.
    """

    def __init__(self, parent, db, mode, title, show_case=False, on_change=None):
        super().__init__(parent, fg_color="transparent")
        self.db        = db
        self.mode      = mode
        self.title     = title
        self.show_case = show_case
        self.on_change = on_change
        self.actions   = SolveActions(db, self._changed)
        self._selected = None            # solve id picked in the history
        self._rows     = []              # the session's solves, newest first
        self._labels   = {}              # solve id -> its row's labels

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.picker = SessionPicker(self, db, mode, title, on_change=self._session_changed)
        self.picker.grid(row=0, column=0, padx=8, pady=(4, 4), sticky="ew")

        self.stats = StatsBlock(self, bg=C_PANEL, compact=True)
        self.stats.grid(row=1, column=0, padx=10, pady=(0, 4), sticky="w")

        ctk.CTkLabel(self, text="Click a solve, then +2 / DNF / flag / delete", height=16,
                     font=ctk.CTkFont(size=11), text_color="gray55").grid(row=2, column=0)

        self.list = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list.grid(row=3, column=0, padx=2, pady=(0, 4), sticky="nsew")
        self.list.grid_columnconfigure(1, weight=1)

        self.buttons = SolveButtons(self, self._on_action,
                                    actions=["ok", "+2", "dnf", "flag", "note", "delete"])
        self.buttons.label.grid_remove()
        self.buttons.grid(row=4, column=0, pady=(0, 2))
        self.selected_label = ctk.CTkLabel(self, text="", height=16, font=ctk.CTkFont(size=11),
                                           text_color="gray55")
        self.selected_label.grid(row=5, column=0, pady=(0, 6))

    # ------------------------------------------------------------------
    def refresh(self):
        db, mode = self.db, self.mode
        self._rows = db.solves(mode, "session", limit=HISTORY)
        self.picker.refresh()
        self.stats.update_stats(db.session_name(mode), db.stats(mode, "session"),
                                db.stats(mode))
        if self._selected not in {r[0] for r in self._rows}:
            self._selected = None

        for w in self.list.winfo_children():
            w.destroy()
        self._labels = {}
        bg     = self.list._parent_canvas.cget("bg")
        family = ctk.ThemeManager.theme["CTkFont"]["family"]
        size   = -_px(self, 12)
        if not self._rows:
            tk.Label(self.list, text="No solves in this session yet.", bg=bg, fg="gray55",
                     font=(family, size)).grid(row=0, column=0, columnspan=4, pady=8)
        count = db.stats(mode, "session")["count"]
        for i, row in enumerate(self._rows):
            sid, case, seconds, penalty, flagged, note, ts = row[:7]
            cells = [
                (str(count - i), "gray45", (family, size - 1), "w"),
                (case if self.show_case else ts[5:16], C_TEXT if self.show_case else "gray55",
                 (family, size), "w"),
                ("⚑" if flagged else "", C_STOPPED, (family, size), "center"),
                (fmt_solve(seconds, penalty), solve_color(penalty) or (C_STOPPED if i == 0 else C_TEXT),
                 ("Consolas", size), "e"),
            ]
            labels = []
            for col, (text, fg, font, anchor) in enumerate(cells):
                lbl = tk.Label(self.list, text=text, bg=bg, fg=fg, font=font, anchor=anchor)
                lbl.grid(row=i, column=col, sticky="ew", padx=(_px(self, 4), 0), ipady=1)
                lbl.bind("<Button-1>", lambda e, s=sid: self.select(s))
                labels.append(lbl)
            self._labels[sid] = labels
        self._paint_selection()

    def select(self, solve_id):
        """Pick a solve for the buttons; picking it again goes back to the newest."""
        self._selected = None if self._selected == solve_id else solve_id
        self._paint_selection()

    def selected_solve(self):
        rows = {r[0]: r for r in self._rows}
        if self._selected in rows:
            return rows[self._selected]
        return self._rows[0] if self._rows else None

    def _paint_selection(self):
        bg = self.list._parent_canvas.cget("bg")
        for sid, labels in self._labels.items():
            for lbl in labels:
                lbl.configure(bg=C_CURRENT if sid == self._selected else bg)
        solve = self.selected_solve()
        self.buttons.show(solve)
        if solve is None:
            self.selected_label.configure(text="")
        else:
            which = "Selected" if self._selected else "Newest"
            what = fmt_solve(solve[2], solve[3]) + (f"  {solve[1]}" if solve[1] else "")
            note = f"  •  ⚑ {solve[5]}" if solve[5] else ""
            self.selected_label.configure(text=f"{which}: {what}{note}")

    def _on_action(self, action):
        self.actions.run(self.selected_solve(), action)

    def _session_changed(self):
        """Another session was selected, made, renamed or deleted."""
        self._selected = None
        self._changed()

    def _changed(self):
        self.refresh()
        if self.on_change:
            self.on_change()


# ---------------------------------------------------------------------------
# Full Solve Screen
# ---------------------------------------------------------------------------
class FullSolveScreen(TimerScreenBase):

    def __init__(self, parent, root, db):
        super().__init__(parent, root, db)
        self._scramble = ""
        self._build_ui()
        self._new_scramble()
        self.session.refresh()
        self._refresh_times()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self, text="Full Solve", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, pady=(24, 8))

        # Scramble panel
        scramble_frame = ctk.CTkFrame(self, corner_radius=8)
        scramble_frame.grid(row=1, column=0, padx=30, pady=6, sticky="ew")
        scramble_frame.grid_columnconfigure(0, weight=1)

        self.scramble_label = ctk.CTkLabel(
            scramble_frame, text="",
            font=ctk.CTkFont(family="Consolas", size=15),
            wraplength=560, justify="center",
        )
        self.scramble_label.grid(row=0, column=0, padx=16, pady=14)

        # Timer
        self.timer_label = ctk.CTkLabel(
            self, text="0.00",
            font=ctk.CTkFont(family="Consolas", size=72, weight="bold"),
            text_color=C_IDLE,
        )
        self.timer_label.grid(row=2, column=0, pady=10)

        # Status
        self.status_label = ctk.CTkLabel(
            self, text="Press SPACE or Start to begin",
            font=ctk.CTkFont(size=12), text_color="gray55",
        )
        self.status_label.grid(row=3, column=0, pady=(0, 8))

        # Buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=4, column=0, pady=8)

        self.start_btn = ctk.CTkButton(
            btn_row, text="Start  [space]", width=150, height=42,
            font=ctk.CTkFont(size=14),
            command=self.timer_toggle,
        )
        self.start_btn.grid(row=0, column=0, padx=8)

        ctk.CTkButton(
            btn_row, text="New Scramble", width=130, height=42,
            fg_color="gray30", hover_color="gray40",
            command=self._new_scramble,
        ).grid(row=0, column=1, padx=8)

        ctk.CTkButton(
            btn_row, text="Delete Last", width=120, height=42,
            fg_color="gray30", hover_color="#6B0000",
            command=self._delete_last,
        ).grid(row=0, column=2, padx=8)

        # Penalty / flag for the newest solve
        self.last_bar = SolveButtons(self, self._last_action, actions=["ok", "+2", "dnf", "flag"])
        self.last_bar.grid(row=5, column=0, pady=(2, 2))

        # Result bar
        self.result_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=13), text_color="gray65",
        )
        self.result_label.grid(row=6, column=0, pady=(4, 24))

        # Right-hand column: the current session
        self.grid_columnconfigure(1, weight=2, minsize=SIDE_WIDTH)
        side = ctk.CTkFrame(self, fg_color=C_PANEL, corner_radius=8, width=SIDE_WIDTH)
        side.grid(row=0, column=1, rowspan=7, padx=(0, 16), pady=16, sticky="nsew")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(0, weight=1)
        self.session = SessionPanel(side, self.db, "full", "Full Solve",
                                    on_change=self._refresh_times)
        self.session.grid(row=0, column=0, padx=4, pady=8, sticky="nsew")

    def on_show(self):
        """Solves may have been changed on the Statistics screen."""
        self.session.refresh()
        self._refresh_times()

    # ------------------------------------------------------------------
    def _new_scramble(self):
        self._cancel_timer()
        self._reset_display()
        self._scramble = generate_scramble()
        self.scramble_label.configure(text=self._scramble)
        self.status_label.configure(text="Press SPACE or Start to begin")

    def _next(self):
        self._new_scramble()

    def _save_result(self, elapsed):
        self.db.add("full", elapsed, scramble=self._scramble)
        log.info("full solve: %s", fmt(elapsed))
        self.status_label.configure(text=f"Saved  {fmt(elapsed)}  —  press SPACE for next scramble")
        self.session.refresh()
        self._refresh_times()

    def _newest(self):
        rows = self.db.solves("full", "session", limit=1)
        return rows[0] if rows else None

    def _refresh_times(self):
        """Result bar (this session's latest 12) and the newest solve's buttons."""
        rows = self.db.solves("full", "session", limit=12)
        self.result_label.configure(text=result_bar_text([effective(r[2], r[3]) for r in rows]))
        newest = rows[0] if rows else None
        self.last_bar.show(newest, f"Last solve {fmt_solve(newest[2], newest[3])}:" if newest else "")

    def _last_action(self, action):
        self.session.actions.run(self._newest(), action)

    def _delete_last(self):
        if self.db.delete_last("full"):
            self.status_label.configure(text="Last time deleted.")
            self.session.refresh()
            self._refresh_times()


# ---------------------------------------------------------------------------
# Practice selection and statuses (shared by every screen)
# ---------------------------------------------------------------------------
def group_order(cases):
    """Group names in the order the cases are listed."""
    return list(dict.fromkeys(c["group"] for c in cases))


class SelectionStore:
    """
    The cases picked for practice and each case's learning status, per mode.
    Every change goes through here: it is saved, then every listener is told
    which mode changed so it can repaint.
    """

    SLOWEST_COUNT = 10

    def __init__(self, db):
        self.db        = db
        self.selected  = {m: db.get_selected(m) for m in CASES}   # mode -> set of names
        self.statuses  = {m: db.get_statuses(m) for m in CASES}   # mode -> {name: status}
        self.custom    = {m: db.get_custom_groups(m) for m in CASES}  # mode -> {group: names}
        self.active    = {m: None for m in CASES}   # custom group being edited, per mode
        self._listeners = []

    def listen(self, fn):
        """fn(mode) is called after every change."""
        self._listeners.append(fn)

    def _changed(self, mode):
        log.debug("%s selection now %d cases (editing group: %s)",
                  mode, len(self.selected[mode]), self.active[mode])
        for fn in self._listeners:
            fn(mode)

    def status(self, mode, name):
        return self.statuses[mode].get(name, "unlearned")

    def set(self, mode, names):
        selection = self.selected[mode]
        names = set(names)
        selection.clear()            # same set object: screens keep references to it
        selection.update(names)
        self.db.set_selected(mode, selection)
        self._changed(mode)

    def toggle(self, mode, name):
        self.set(mode, self.selected[mode] ^ {name})

    def toggle_group(self, mode, group):
        """Select the whole group, or clear it if it is already all selected."""
        names = {c["name"] for c in CASES[mode] if c["group"] == group}
        selection = self.selected[mode]
        self.set(mode, selection - names if names <= selection else selection | names)

    def mark_selected(self, mode, status):
        """Give every selected case the same status. Returns how many changed."""
        names = list(self.selected[mode])
        if not names:
            return 0
        for name in names:
            if status == "unlearned":
                self.statuses[mode].pop(name, None)
            else:
                self.statuses[mode][name] = status
        self.db.set_statuses(mode, names, status)
        log.info("%s: marked %d cases %s", mode, len(names), status)
        self._changed(mode)
        return len(names)

    # --- the user's own groups ---------------------------------------
    # A loaded group becomes the *active* group: the selection is then a working
    # copy of it, and nothing changes in the group until save_active().
    def save_group(self, mode, name, names):
        """Create (or overwrite) a custom group; it becomes the active group."""
        self.custom[mode][name] = set(names)
        self.active[mode] = name
        self.db.save_custom_group(mode, name, names)
        log.info("%s group %r saved with %d cases", mode, name, len(names))
        self._changed(mode)

    def delete_group(self, mode, name):
        self.custom[mode].pop(name, None)
        if self.active[mode] == name:
            self.active[mode] = None
        self.db.delete_custom_group(mode, name)
        log.info("%s group %r deleted", mode, name)
        self._changed(mode)

    def load_group(self, mode, name):
        """Make a custom group the selection and start editing it."""
        self.active[mode] = name
        self.set(mode, self.custom[mode].get(name, ()))

    def pending_changes(self, mode):
        """Cases added to or removed from the active group but not saved yet."""
        name = self.active[mode]
        if name is None:
            return 0
        return len(self.selected[mode] ^ self.custom[mode].get(name, set()))

    def save_active(self, mode):
        name = self.active[mode]
        if name is not None:
            self.save_group(mode, name, self.selected[mode])

    def revert_active(self, mode):
        name = self.active[mode]
        if name is not None:
            self.set(mode, self.custom[mode].get(name, ()))

    def close_active(self, mode):
        """Stop editing the group (the selection stays as it is)."""
        self.active[mode] = None
        self._changed(mode)

    def slowest(self, mode):
        """Names of the slowest cases by recent average (only cases with times)."""
        means = self.db.recent_means(mode)
        ranked = sorted((c["name"] for c in CASES[mode] if c["name"] in means),
                        key=lambda n: -means[n])
        return ranked[:self.SLOWEST_COUNT]

    def set_status(self, mode, name, status):
        if status == "unlearned":
            self.statuses[mode].pop(name, None)
        else:
            self.statuses[mode][name] = status
        self.db.set_status(mode, name, status)
        log.info("%s: %s marked %s", mode, name, status)
        self._changed(mode)


class SelectionTools(ctk.CTkFrame):
    """
    Buttons that act on the whole selection: select All / None / Slowest,
    mark every selected case Unlearned / Learning / Finished, and save the
    selection as a custom group. `compact` stacks them for the narrow side column.
    """

    def __init__(self, parent, store, mode, compact=False, on_edit=None):
        super().__init__(parent, fg_color="transparent")
        self.store    = store
        self.mode     = mode
        self._on_edit = on_edit
        names = [c["name"] for c in CASES[mode]]

        def button(text, fn, edits=True, width=60, **kw):
            return ctk.CTkButton(self, text=text, height=26, width=width,
                                 font=ctk.CTkFont(size=12), fg_color="gray30",
                                 hover_color="gray40",
                                 command=lambda: self._run(fn, edits), **kw)

        select = [button("All", lambda: store.set(mode, names)),
                  button("None", lambda: store.set(mode, [])),
                  button(f"Slowest {store.SLOWEST_COUNT}", self._slowest)]
        mark = [button(s.title(), lambda s=s: self._mark(s), edits=False,
                       text_color=STATUS_COLOR[s] if s != "unlearned" else None)
                for s in STATUSES]
        mark_label = ctk.CTkLabel(self, text="Mark selected as:", height=22,
                                  font=ctk.CTkFont(size=12), text_color="gray60")
        save = button("Save as group…", self._save_group, edits=False, width=110)
        self.count = ctk.CTkLabel(self, text="", height=24, font=ctk.CTkFont(size=12),
                                  text_color="gray60")

        if compact:
            for col in range(3):
                self.grid_columnconfigure(col, weight=1, uniform="tools")
            for i, b in enumerate(select):
                b.grid(row=0, column=i, padx=2, pady=2, sticky="ew")
            mark_label.grid(row=1, column=0, columnspan=3, padx=4, pady=(4, 0), sticky="w")
            for i, b in enumerate(mark):
                b.grid(row=2, column=i, padx=2, pady=2, sticky="ew")
            save.grid(row=3, column=0, columnspan=2, padx=2, pady=(4, 2), sticky="ew")
            self.count.grid(row=3, column=2, padx=4, pady=(4, 2))
        else:
            row = select + [mark_label] + mark + [save, self.count]
            for i, w in enumerate(row):
                pad = (14, 2) if w in (mark_label, save) else (2, 2)
                w.grid(row=0, column=i, padx=pad, pady=2)

        # replaceable in tests; the real ones open dialogs
        self.ask_name = lambda prompt: ctk.CTkInputDialog(
            text=prompt, title="Save group").get_input()
        self.refresh()

    def _run(self, fn, edits=True):
        message = fn()
        if edits and self._on_edit:
            self._on_edit()
        if message:
            self.count.configure(text=message)

    def _slowest(self):
        names = self.store.slowest(self.mode)
        if not names:
            return "no times yet"
        self.store.set(self.mode, names)

    def _mark(self, status):
        n = self.store.mark_selected(self.mode, status)
        return f"{n} marked" if n else "select cases first"

    def _save_group(self):
        selection = self.store.selected[self.mode]
        if not selection:
            return "select cases first"
        name = self.ask_name(f"Name for this group of {len(selection)} cases\n"
                             "(an existing name is replaced):")
        name = (name or "").strip()[:30]
        if not name:
            return None
        self.store.save_group(self.mode, name, selection)
        return "group saved"

    def refresh(self):
        self.count.configure(text=f"{len(self.store.selected[self.mode])} selected")


class MyGroups(ctk.CTkFrame):
    """The user's saved groups: click one to load it as the selection, ✕ deletes it."""

    def __init__(self, parent, store, mode, on_edit=None, per_row=2):
        super().__init__(parent, fg_color="transparent")
        self.store    = store
        self.mode     = mode
        self._on_edit = on_edit
        self._per_row = per_row
        # replaceable in tests; the real one opens a dialog
        self.confirm  = lambda msg: messagebox.askyesno("My groups", msg)
        self.refresh()

    def relayout(self, per_row):
        if per_row != self._per_row:
            self._per_row = per_row
            self.refresh()

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        groups = self.store.custom[self.mode]
        # reset every column: a narrower layout must not leave old columns taking space
        for col in range(max(self._per_row, 12)):
            used = col < self._per_row
            self.grid_columnconfigure(col, weight=1 if used else 0,
                                      uniform="mygroups" if used else "")
        ctk.CTkLabel(self, text="My groups", anchor="w", height=22,
                     font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=0, columnspan=self._per_row, padx=4, sticky="w")
        if not groups:
            ctk.CTkLabel(self, text="Select cases, then Save as group…", anchor="w", height=20,
                         font=ctk.CTkFont(size=11), text_color="gray55").grid(
                row=1, column=0, columnspan=self._per_row, padx=4, sticky="w")
            return
        active = self.store.active[self.mode]
        if active is not None:
            self._build_edit_bar(active).grid(
                row=1, column=0, columnspan=self._per_row, padx=2, pady=(0, 4), sticky="ew")
        for i, (name, members) in enumerate(sorted(groups.items(), key=lambda g: g[0].lower())):
            chip = ctk.CTkFrame(self, fg_color="gray25", corner_radius=6,
                                border_width=1,
                                border_color=C_SELECTED if name == active else "gray25")
            chip.grid(row=2 + i // self._per_row, column=i % self._per_row,
                      padx=2, pady=2, sticky="ew")
            chip.grid_columnconfigure(0, weight=1)
            ctk.CTkButton(chip, text=f"★ {name} ({len(members)})", anchor="w", height=24,
                          width=40, font=ctk.CTkFont(size=12), fg_color="transparent",
                          hover_color="gray35",
                          command=lambda n=name: self._load(n)).grid(
                row=0, column=0, padx=(2, 0), pady=2, sticky="ew")
            ctk.CTkButton(chip, text="✕", width=22, height=22, font=ctk.CTkFont(size=11),
                          fg_color="transparent", hover_color="#6B0000", text_color="gray60",
                          command=lambda n=name: self._delete(n)).grid(
                row=0, column=1, padx=(0, 2))

    def _build_edit_bar(self, name):
        """'Editing ★ name · 2 unsaved   [Save] [Revert] [Done]'."""
        pending = self.store.pending_changes(self.mode)
        bar = ctk.CTkFrame(self, fg_color="gray20", corner_radius=6)
        bar.grid_columnconfigure(0, weight=1)
        text = f"Editing ★ {name}" + (f"  •  {pending} unsaved" if pending else "  •  saved")
        ctk.CTkLabel(bar, text=text, anchor="w", height=24,
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=C_STOPPED if pending else C_SELECTED).grid(
            row=0, column=0, columnspan=3, padx=8, pady=(4, 0), sticky="w")
        buttons = [
            ("Save", lambda: self.store.save_active(self.mode), pending, "#1f6aa5"),
            ("Revert", lambda: self._revert(), pending, "gray30"),
            ("Done", lambda: self._done(), True, "gray30"),
        ]
        for col, (label, fn, enabled, color) in enumerate(buttons):
            ctk.CTkButton(bar, text=label, width=56, height=24, font=ctk.CTkFont(size=12),
                          fg_color=color, hover_color="gray40",
                          state="normal" if enabled else "disabled",
                          command=fn).grid(row=1, column=col, padx=(6 if col == 0 else 2, 2),
                                           pady=(2, 6), sticky="w")
        return bar

    def _revert(self):
        self.store.revert_active(self.mode)
        if self._on_edit:
            self._on_edit()

    def _done(self):
        if self.store.pending_changes(self.mode) and not self.confirm(
                f"Stop editing “{self.store.active[self.mode]}” without saving "
                f"{self.store.pending_changes(self.mode)} change(s)?"):
            return
        self.store.close_active(self.mode)

    def _load(self, name):
        active = self.store.active[self.mode]
        if active not in (None, name) and self.store.pending_changes(self.mode):
            if not self.confirm(f"Discard {self.store.pending_changes(self.mode)} unsaved "
                                f"change(s) to “{active}” and open “{name}”?"):
                return
        self.store.load_group(self.mode, name)
        if self._on_edit:
            self._on_edit()

    def _delete(self, name):
        if self.confirm(f"Delete the group “{name}”? The cases themselves are kept."):
            self.store.delete_group(self.mode, name)


class GroupHeader(ctk.CTkFrame):
    """'▾ Dot  (3/8)   ☑' — the tick selects or clears the group, the arrow folds it."""

    def __init__(self, parent, group, on_tick, on_fold=None, size=13):
        super().__init__(parent, fg_color="transparent")
        self.group = group
        self._open = True
        self.grid_columnconfigure(1, weight=1)
        font = ctk.CTkFont(size=size, weight="bold")

        self.arrow = None
        if on_fold:
            self.arrow = ctk.CTkLabel(self, text="▾", width=14, font=font, cursor="hand2")
            self.arrow.grid(row=0, column=0, padx=(2, 4))
        self.title = ctk.CTkLabel(self, text=group, anchor="w", height=22, font=font)
        self.title.grid(row=0, column=1, sticky="w")
        if on_fold:
            for w in (self.arrow, self.title):
                w.bind("<Button-1>", lambda e: self._fold(on_fold))

        self.tick = ctk.CTkLabel(self, text="☐", width=24, height=22, cursor="hand2",
                                 font=ctk.CTkFont(family="Segoe UI Symbol", size=size + 4))
        self.tick.grid(row=0, column=2, padx=4)
        self.tick.bind("<Button-1>", lambda e: on_tick(group))

    def _fold(self, on_fold):
        self._open = not self._open
        self.arrow.configure(text="▾" if self._open else "▸")
        on_fold(self.group, self._open)

    def show(self, picked, total):
        self.title.configure(text=f"{self.group}  ({picked}/{total})")
        self.tick.configure(
            text="☑" if picked == total else "☐" if picked == 0 else "◩",
            text_color=C_SELECTED if picked else "gray55")


class CasePicker(ctk.CTkScrollableFrame):
    """
    Mini pictures of every case, grouped by shape. Click toggles a case in the
    practice selection, double-click pins it, hovering reports the case.
    """

    PER_ROW = 4                # at the narrowest; more fit as the column widens

    def __init__(self, parent, store, mode, on_toggle, on_toggle_group, on_pin, on_hover,
                 on_edit=None):
        super().__init__(parent, fg_color="transparent")
        self.store   = store
        self.mode    = mode
        self.cases   = CASES[mode]
        self._tiles   = {}     # name -> (tile, diagram, status bar)
        self._headers = {}     # group -> GroupHeader
        self._bodies  = {}     # group -> frame holding the tiles
        self._members = {}     # group -> case names in order
        self._layout  = (self.PER_ROW, _px(self, 42))
        self._painted = {}     # name -> colours last applied (see refresh)
        self._reflow_job = None
        self.grid_columnconfigure(0, weight=1)

        self.my_groups = MyGroups(self, store, mode, on_edit=on_edit)
        self.my_groups.grid(row=0, column=0, sticky="ew", padx=2, pady=(2, 4))

        size = self._layout[1]
        bar_h = _px(self, 4)
        row = 1
        for group in group_order(self.cases):
            header = GroupHeader(self, group, on_tick=on_toggle_group,
                                 on_fold=self._fold, size=12)
            header.grid(row=row, column=0, sticky="ew", pady=(6, 0))
            body = ctk.CTkFrame(self, fg_color="transparent")
            body.grid(row=row + 1, column=0, sticky="w")
            self._headers[group], self._bodies[group] = header, body
            row += 2

            members = [c for c in self.cases if c["group"] == group]
            self._members[group] = [c["name"] for c in members]
            for i, case in enumerate(members):
                # plain tk frame: ~57 rounded ctk frames made the page slow to open
                tile = tk.Frame(body, bg=C_PANEL, highlightthickness=_px(self, 2),
                                highlightbackground=C_PANEL, highlightcolor=C_PANEL, bd=0)
                tile.grid(row=i // self.PER_ROW, column=i % self.PER_ROW, padx=1, pady=1)
                diagram = CaseDiagram(tile, case["alg"], size=size, bg=C_PANEL)
                diagram.grid(row=0, column=0, padx=4, pady=(4, 0))
                bar = tk.Canvas(tile, width=size, height=bar_h, bg=C_PANEL,
                                highlightthickness=0, bd=0)
                bar.grid(row=1, column=0, padx=4, pady=(1, 4))
                for w in (tile, diagram, bar):
                    w.bind("<Button-1>", lambda e, c=case: on_toggle(c))
                    w.bind("<Double-Button-1>", lambda e, c=case: on_pin(c))
                    w.bind("<Enter>", lambda e, c=case: on_hover(c))
                    w.bind("<Leave>", lambda e: on_hover(None))
                self._tiles[case["name"]] = (tile, diagram, bar)

        self._parent_canvas.bind("<Configure>", self._on_resize, add="+")

    # --- grow with the column -------------------------------------------
    def _on_resize(self, event):
        if self._reflow_job:
            self.after_cancel(self._reflow_job)
        self._reflow_job = self.after(120, lambda w=event.width: self._reflow(w))

    def _reflow(self, width):
        """More and bigger tiles per row as the column gets wider."""
        self._reflow_job = None
        avail = width - _px(self, 10)
        per_row = max(self.PER_ROW, avail // _px(self, 96))
        # tile = picture + 4px padding each side + 2px border each side + 1px grid gap
        size = max(_px(self, 40), min(_px(self, 100), avail // per_row - _px(self, 14)))
        if (per_row, size) == self._layout:
            return
        self._layout = (per_row, size)
        for names in self._members.values():
            for i, name in enumerate(names):
                tile, diagram, bar = self._tiles[name]
                tile.grid_configure(row=i // per_row, column=i % per_row)
                diagram.resize(size)
                bar.configure(width=size)
        self.my_groups.relayout(max(2, per_row // 3))

    def _fold(self, group, is_open):
        if is_open:
            self._bodies[group].grid()
        else:
            self._bodies[group].grid_remove()

    def refresh(self, current=None):
        selection = self.store.selected[self.mode]
        current_name = current["name"] if current else None
        for name, (tile, diagram, bar) in self._tiles.items():
            bg = C_CURRENT if name == current_name else C_PANEL
            status = self.store.status(self.mode, name)
            look = (bg, C_SELECTED if name in selection else bg,
                    bg if status == "unlearned" else STATUS_COLOR[status])
            if self._painted.get(name) == look:
                continue                # reconfiguring ctk widgets is slow; skip unchanged
            self._painted[name] = look
            tile.configure(bg=look[0], highlightbackground=look[1], highlightcolor=look[1])
            diagram.configure(bg=look[0])
            bar.configure(bg=look[2])
        for group, header in self._headers.items():
            members = self._members[group]
            header.show(sum(1 for n in members if n in selection), len(members))
        self.my_groups.refresh()


# ---------------------------------------------------------------------------
# OLL / PLL Practice Screen
# ---------------------------------------------------------------------------
class CaseTrainerScreen(TimerScreenBase):
    """
    Drills last-layer cases. Each round picks a case at random from the chosen
    source (all cases, the selected set, the slowest, a status or one group),
    or the pinned case; shows a scramble that sets it up, and records the time.
    The right-hand column holds the case picker and the history.
    """

    PICK_HINT = "Click: select  •  double-click: pin"

    def __init__(self, parent, root, db, store, mode, title):
        super().__init__(parent, root, db)
        self.store     = store
        self.mode      = mode                 # "oll" | "pll"
        self.title     = title
        self.cases     = CASES[mode]
        self.selection = store.selected[mode]
        self.groups    = group_order(self.cases)

        # "all" | "selected" | "slowest" | "status:<status>" | "group:<name>"
        self._source        = "all"
        self._source_keys   = {}              # menu label -> source key
        self._source_before = None            # source before a picker click (see _pin)
        self._pinned        = None            # a case to repeat instead of dealing
        self._current_case  = None
        self._scramble      = ""
        self._build_ui()
        self._sync_pickers()
        self._pick_next_case()
        self._refresh_history()
        # a hidden page repaints in on_show instead of on every change
        store.listen(lambda m: m == self.mode and self.winfo_ismapped()
                     and self.refresh_selection())

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        ctk.CTkLabel(self, text=self.title, font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, pady=(18, 6))

        # --- Where cases come from, odds ---
        filter_row = ctk.CTkFrame(self, fg_color="transparent")
        filter_row.grid(row=1, column=0, pady=4)

        ctk.CTkLabel(filter_row, text="From:", font=ctk.CTkFont(size=13)).grid(
            row=0, column=0, padx=(0, 6))
        self.source_var = ctk.StringVar()
        self.source_menu = ctk.CTkOptionMenu(
            filter_row, values=[""], variable=self.source_var,
            width=165, command=self._on_source_change,
        )
        self.source_menu.grid(row=0, column=1, padx=(0, 18))

        ctk.CTkLabel(filter_row, text="Odds:", font=ctk.CTkFont(size=13)).grid(
            row=0, column=2, padx=(0, 6))
        self.odds = ctk.CTkSegmentedButton(filter_row, values=["Balanced", "Realistic"])
        self.odds.set("Balanced")
        self.odds.grid(row=0, column=3)

        # --- Status of the current case, hint toggle ---
        opt_row = ctk.CTkFrame(self, fg_color="transparent")
        opt_row.grid(row=2, column=0, pady=4)

        ctk.CTkLabel(opt_row, text="This case:", font=ctk.CTkFont(size=13)).grid(
            row=0, column=0, padx=(0, 6))
        self.status_seg = ctk.CTkSegmentedButton(
            opt_row, values=[s.title() for s in STATUSES], command=self._on_status_change)
        self.status_seg.grid(row=0, column=1, padx=(0, 24))

        self.hint_switch = ctk.CTkSwitch(opt_row, text="Show algorithm",
                                         command=self._show_alg)
        self.hint_switch.select()
        self.hint_switch.grid(row=0, column=2)

        # --- Case panel (picture, name, algorithm, scramble) ---
        case_panel = ctk.CTkFrame(self, corner_radius=8)
        case_panel.grid(row=3, column=0, padx=20, pady=6, sticky="ew")
        self._build_case_panel(case_panel)

        # --- Timer ---
        self.timer_label = ctk.CTkLabel(
            self, text="0.00",
            font=ctk.CTkFont(family="Consolas", size=72, weight="bold"),
            text_color=C_IDLE,
        )
        self.timer_label.grid(row=4, column=0, pady=4)

        self.status_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=12), text_color="gray55",
        )
        self.status_label.grid(row=5, column=0, pady=(0, 4))

        # --- Buttons ---
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=6, column=0, pady=6)

        self.start_btn = ctk.CTkButton(
            btn_row, text="Start  [space]", width=150, height=42,
            font=ctk.CTkFont(size=14), command=self.timer_toggle,
        )
        self.start_btn.grid(row=0, column=0, padx=8)

        ctk.CTkButton(
            btn_row, text="Next Case", width=120, height=42,
            fg_color="gray30", hover_color="gray40",
            command=self._pick_next_case,
        ).grid(row=0, column=1, padx=8)

        ctk.CTkButton(
            btn_row, text="Delete Last", width=120, height=42,
            fg_color="gray30", hover_color="#6B0000",
            command=self._delete_last,
        ).grid(row=0, column=2, padx=8)

        self.last_bar = SolveButtons(self, self._last_action, actions=["ok", "+2", "dnf", "flag"])
        self.last_bar.grid(row=7, column=0, pady=(2, 2))

        self.result_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=13), text_color="gray65",
        )
        self.result_label.grid(row=8, column=0, pady=(4, 16))

        self._build_side()

    def _build_side(self):
        """Right-hand column: Cases (picker) and History tabs."""
        # the column takes a share of any extra width, so the picker grows with the window
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2, minsize=SIDE_WIDTH)
        side = ctk.CTkFrame(self, fg_color=C_PANEL, corner_radius=8, width=SIDE_WIDTH)
        side.grid(row=0, column=1, rowspan=9, padx=(0, 16), pady=(16, 16), sticky="nsew")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(1, weight=1)

        self.side_tabs = ctk.CTkSegmentedButton(side, values=["Cases", "History"],
                                                command=self._show_side)
        self.side_tabs.grid(row=0, column=0, padx=10, pady=(10, 4), sticky="ew")

        # Cases tab
        self.cases_tab = ctk.CTkFrame(side, fg_color="transparent")
        self.cases_tab.grid(row=1, column=0, sticky="nsew")
        self.cases_tab.grid_columnconfigure(0, weight=1)
        self.cases_tab.grid_rowconfigure(3, weight=1)

        self.tools = SelectionTools(self.cases_tab, self.store, self.mode, compact=True,
                                    on_edit=self._on_set_edited)
        self.tools.grid(row=0, column=0, padx=6, sticky="ew")

        self.hover_label = ctk.CTkLabel(self.cases_tab, text=self.PICK_HINT, height=18,
                                        font=ctk.CTkFont(size=11), text_color="gray55")
        self.hover_label.grid(row=1, column=0, pady=(2, 0))

        self.pin_bar = ctk.CTkFrame(self.cases_tab, fg_color="gray20", corner_radius=6)
        self.pin_bar.grid(row=2, column=0, padx=8, pady=(4, 0), sticky="ew")
        self.pin_bar.grid_columnconfigure(0, weight=1)
        self.pin_label = ctk.CTkLabel(self.pin_bar, text="", height=24,
                                      font=ctk.CTkFont(size=12, weight="bold"),
                                      text_color=C_STOPPED)
        self.pin_label.grid(row=0, column=0, padx=8, sticky="w")
        ctk.CTkButton(self.pin_bar, text="✕ Unpin", width=70, height=24,
                      font=ctk.CTkFont(size=12), fg_color="gray30", hover_color="gray40",
                      command=self.unpin).grid(row=0, column=1, padx=4, pady=3)
        self.pin_bar.grid_remove()

        self.picker = CasePicker(self.cases_tab, self.store, self.mode,
                                 on_toggle=self._toggle_case,
                                 on_toggle_group=self._toggle_group, on_pin=self._pin,
                                 on_hover=self._hover, on_edit=self._on_set_edited)
        self.picker.grid(row=3, column=0, padx=(2, 0), pady=(4, 8), sticky="nsew")

        # History tab
        self.history_tab = ctk.CTkFrame(side, fg_color="transparent")
        self.history_tab.grid(row=1, column=0, sticky="nsew")
        self.history_tab.grid_columnconfigure(0, weight=1)
        self.history_tab.grid_rowconfigure(0, weight=1)
        self.session = SessionPanel(self.history_tab, self.db, self.mode, self.title,
                                    show_case=True, on_change=self._on_times_changed)
        self.session.grid(row=0, column=0, sticky="nsew")

        self.side_tabs.set("Cases")
        self._show_side("Cases")

    def _show_side(self, tab):
        (self.cases_tab if tab == "Cases" else self.history_tab).grid()
        (self.history_tab if tab == "Cases" else self.cases_tab).grid_remove()

    # ------------------------------------------------------------------
    # Case picker
    # ------------------------------------------------------------------
    def _toggle_case(self, case):
        self._source_before = self._source
        self.store.toggle(self.mode, case["name"])
        self._on_set_edited()

    def _toggle_group(self, group):
        self.store.toggle_group(self.mode, group)
        self._on_set_edited()

    def _on_set_edited(self):
        """Editing the set from this page means: practise the set."""
        if self._source != "selected":
            self._source = "selected"
            self._sync_pickers()

    def _pin(self, case):
        # the first click of the double-click toggled the case; put it back
        source = self._source_before
        self.store.toggle(self.mode, case["name"])
        if source:
            self._source = source
            self._sync_pickers()
        self.select_case(case)

    def _hover(self, case):
        if case is None:
            self.hover_label.configure(text=self.PICK_HINT, text_color="gray55")
        else:
            status = self.store.status(self.mode, case["name"])
            self.hover_label.configure(
                text=f"{case['name']}  •  {case['group']}  •  {status}",
                text_color=("gray10", "#DCE4EE"))

    def select_case(self, case):
        """Practise one case over and over (picker or gallery double-click)."""
        self._pinned = case
        self.pin_label.configure(text=f"Pinned: {case['name']}")
        self.pin_bar.grid()
        self._load_case(case)

    def unpin(self):
        self._pinned = None
        self.pin_bar.grid_remove()
        self._pick_next_case()

    def refresh_selection(self):
        """Repaint after the selection or a status changed (here or elsewhere)."""
        self._sync_pickers()
        self.tools.refresh()
        self.picker.refresh(self._current_case)
        if self._current_case:
            self.status_seg.set(self._status(self._current_case).title())

    # ------------------------------------------------------------------
    # Where cases are drawn from
    # ------------------------------------------------------------------
    def _status(self, case):
        return self.store.status(self.mode, case["name"])

    def _source_options(self):
        """(key, menu label) for every place cases can be drawn from."""
        opts = [("all", "All cases"), ("selected", f"Selected ({len(self.selection)})"),
                ("slowest", f"Slowest {self.store.SLOWEST_COUNT}")]
        for status in STATUSES:
            n = sum(1 for c in self.cases if self._status(c) == status)
            opts.append((f"status:{status}", f"{status.title()} ({n})"))
        for name, members in sorted(self.store.custom[self.mode].items(),
                                    key=lambda g: g[0].lower()):
            opts.append((f"custom:{name}", f"★ {name} ({len(members)})"))
        opts += [(f"group:{g}", g) for g in self.groups]
        return opts

    def _pool(self):
        kind, _, arg = self._source.partition(":")
        if kind == "all":
            return self.cases
        if kind == "selected":
            return [c for c in self.cases if c["name"] in self.selection]
        if kind == "slowest":
            # slowest recent average among the selected cases (all if none selected)
            base = [c for c in self.cases if c["name"] in self.selection] or self.cases
            means = self.db.recent_means(self.mode)
            timed = sorted((c for c in base if c["name"] in means),
                           key=lambda c: -means[c["name"]])
            return timed[:self.store.SLOWEST_COUNT]
        if kind == "status":
            return [c for c in self.cases if self._status(c) == arg]
        if kind == "custom":
            members = self.store.custom[self.mode].get(arg, set())
            return [c for c in self.cases if c["name"] in members]
        return [c for c in self.cases if c["group"] == arg]

    def _on_source_change(self, label):
        self.set_source(self._source_keys.get(label, "all"))

    def set_source(self, source):
        """Switch the pool cases are drawn from, unpin, and deal a new case."""
        self._source = source
        self._pinned = None
        self.pin_bar.grid_remove()
        self._sync_pickers()
        self._pick_next_case()

    def _sync_pickers(self):
        opts = self._source_options()
        self._source_keys = {label: key for key, label in opts}
        self.source_menu.configure(values=[label for _, label in opts])
        self.source_var.set(dict(opts).get(self._source, "All cases"))

    def on_show(self):
        """Called when the screen is opened: selection or statuses may have changed."""
        self.refresh_selection()
        if self._pinned is None and self._source != "all":
            if self._current_case is None or self._current_case not in self._pool():
                self._pick_next_case()
        self._refresh_history()

    def _on_status_change(self, value):
        if self._current_case:
            self.store.set_status(self.mode, self._current_case["name"], value.lower())

    def _show_alg(self):
        if self.hint_switch.get():
            self.case_alg_label.configure(
                text=self._current_case["alg"] if self._current_case else "",
                text_color="#ffcc00")
        else:
            self.case_alg_label.configure(text="algorithm hidden", text_color="gray45")

    # ------------------------------------------------------------------
    def _pick_next_case(self):
        self._cancel_timer()
        note = None
        case = self._pinned
        if case is None:
            pool = self._pool()
            if not pool:
                pool = self.cases
                note = {
                    "selected": "Nothing selected yet - click cases in the picker.",
                    "slowest":  "No times yet to find the slowest cases.",
                    "status":   "No cases have that status yet.",
                    "custom":   "That group no longer exists.",
                }.get(self._source.partition(":")[0], "No cases here.") + " Using all cases."
            # don't deal the same case twice in a row when there is a choice
            choices = [c for c in pool if c is not self._current_case] or pool
            if self.odds.get() == "Realistic":
                case = random.choices(
                    choices, weights=[case_weight(c["alg"]) for c in choices])[0]
            else:
                case = random.choice(choices)
        self._load_case(case, note)

    def _load_case(self, case, note=None):
        self._cancel_timer()
        self._reset_display()
        self._current_case = case
        self._scramble     = setup_scramble(case)
        self.case_name_label.configure(text=case["name"])
        self.case_group_label.configure(text=case["group"])
        self._show_alg()
        self.status_seg.set(self._status(case).title())
        self.case_scramble_label.configure(text=self._scramble)
        self.case_diagram.set_scramble(self._scramble)
        self.status_label.configure(
            text=note or "Scramble from solved (yellow top, green front), then press SPACE")
        self.picker.refresh(case)
        self._refresh_result_bar()

    def _next(self):
        self._pick_next_case()

    def _save_result(self, elapsed):
        if not self._current_case:
            return
        self.db.add(self.mode, elapsed,
                    case_name=self._current_case["name"], scramble=self._scramble)
        log.info("%s attempt: %s %s", self.mode, self._current_case["name"], fmt(elapsed))
        self.status_label.configure(text=f"Saved  {fmt(elapsed)}  —  press SPACE for next case")
        self._refresh_history()

    def _refresh_result_bar(self):
        """This case's latest 12 times, and the newest solve's penalty / flag buttons."""
        rows = self.db.solves(self.mode, "session", limit=1)
        newest = rows[0] if rows else None
        self.last_bar.show(newest, f"Last solve {fmt_solve(newest[2], newest[3])}:" if newest else "")
        if not self._current_case:
            return
        times = [t for t, _ in self.db.get(self.mode, case_name=self._current_case["name"], limit=12)]
        self.result_label.configure(text=result_bar_text(times) or "No times for this case yet.")

    def _refresh_history(self):
        self.session.refresh()
        self._refresh_result_bar()

    def _on_times_changed(self):
        """A solve's penalty / flag changed, one was deleted, or a new session began."""
        self._refresh_result_bar()

    def _last_action(self, action):
        rows = self.db.solves(self.mode, "session", limit=1)
        self.session.actions.run(rows[0] if rows else None, action)

    def _delete_last(self):
        """Removes the newest attempt in this mode (the top row of the history)."""
        if self.db.delete_last(self.mode):
            self.status_label.configure(text="Last time deleted.")
            self._refresh_history()


# ---------------------------------------------------------------------------
# Case Gallery Screen  (a picture of every OLL and PLL case; pick a practice set)
# ---------------------------------------------------------------------------
class CasesScreen(ctk.CTkFrame):

    COLUMNS = 4

    def __init__(self, parent, root, db, store, on_open_case, on_practise):
        super().__init__(parent, fg_color="transparent")
        self.root          = root
        self.db            = db
        self.store         = store
        self._on_open_case = on_open_case    # on_open_case(mode, case)
        self._on_practise  = on_practise     # on_practise(mode)
        self._cards        = {}              # (mode, case name) -> (card, name label, status label)
        self._headers      = {}              # (mode, group) -> GroupHeader
        self._tools        = {}
        self._practise_btn = {}
        self._layouts      = {}              # mode -> scroll frame, sections, column count
        self._reflow_jobs  = {}
        self._painted      = {}              # (mode, name) -> (selected, status) last shown
        self._build_ui()
        # a hidden gallery repaints in on_show instead of on every change
        store.listen(lambda m: self.winfo_ismapped() and self._refresh(m))

    def on_show(self):
        self._refresh("oll")
        self._refresh("pll")

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, padx=20, pady=(20, 4), sticky="ew")
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(hdr, text="Case Gallery", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, sticky="w")
        ctk.CTkLabel(hdr, text="Click to select  •  double-click to practise one case  •  "
                               "click the status to change it",
                     font=ctk.CTkFont(size=12), text_color="gray55").grid(row=0, column=1)

        tabs = ctk.CTkTabview(self)
        tabs.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="nsew")

        for mode in ("oll", "pll"):
            cases = CASES[mode]
            tab_name = f"{mode.upper()} ({len(cases)})"
            tabs.add(tab_name)
            tab = tabs.tab(tab_name)
            tab.grid_columnconfigure(0, weight=1)
            tab.grid_rowconfigure(1, weight=1)

            self._build_toolbar(tab, mode).grid(row=0, column=0, sticky="ew", padx=6, pady=(2, 4))

            sf = ctk.CTkScrollableFrame(tab)
            sf.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)

            my_groups = MyGroups(sf, self.store, mode, per_row=4)
            sections = []
            for group in group_order(cases):
                header = GroupHeader(sf, group,
                                     on_tick=lambda g, m=mode: self.store.toggle_group(m, g))
                self._headers[(mode, group)] = header
                cards = [self._build_card(sf, mode, c) for c in cases if c["group"] == group]
                sections.append((header, cards))
            self._layouts[mode] = {"frame": sf, "my_groups": my_groups,
                                   "sections": sections, "columns": 0}
            self._layout(mode, self.COLUMNS)
            sf._parent_canvas.bind(
                "<Configure>", lambda e, m=mode: self._on_resize(m, e.width), add="+")
            self._refresh(mode)

    # --- columns follow the window width -------------------------------
    def _on_resize(self, mode, width):
        job = self._reflow_jobs.pop(mode, None)
        if job:
            self.after_cancel(job)
        cols = max(3, (width - 20) // _px(self, 185))
        self._reflow_jobs[mode] = self.after(120, lambda: self._layout(mode, cols))

    def _layout(self, mode, cols):
        lay = self._layouts[mode]
        if cols == lay["columns"]:
            return
        sf, old = lay["frame"], lay["columns"]
        for col in range(max(cols, old)):
            sf.grid_columnconfigure(col, weight=1 if col < cols else 0,
                                    uniform="cards" if col < cols else "")
        lay["columns"] = cols
        lay["my_groups"].grid(row=0, column=0, columnspan=cols, sticky="ew", padx=6, pady=(2, 0))
        lay["my_groups"].relayout(cols)
        row = 1
        for header, cards in lay["sections"]:
            header.grid(row=row, column=0, columnspan=cols, sticky="ew", padx=6, pady=(10, 0))
            row += 1
            for i, card in enumerate(cards):
                card.grid(row=row + i // cols, column=i % cols, padx=5, pady=5, sticky="nsew")
            row += (len(cards) + cols - 1) // cols

    def _build_toolbar(self, parent, mode):
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid_columnconfigure(0, weight=1)

        tools = SelectionTools(bar, self.store, mode)
        tools.grid(row=0, column=0, sticky="w")
        self._tools[mode] = tools

        btn = ctk.CTkButton(bar, text="", width=180, height=30,
                            command=lambda: self._on_practise(mode))
        btn.grid(row=0, column=1, padx=(8, 0))
        self._practise_btn[mode] = btn
        return bar

    def _build_card(self, parent, mode, case):
        card = ctk.CTkFrame(parent, fg_color=C_PANEL, corner_radius=8,
                            border_width=2, border_color=C_PANEL)
        card.grid_columnconfigure(0, weight=1)

        diagram = CaseDiagram(card, case["alg"], size=_px(self, 100), bg=C_PANEL)
        diagram.grid(row=0, column=0, pady=(12, 4))

        name = ctk.CTkLabel(card, text=case["name"], font=ctk.CTkFont(size=14, weight="bold"))
        name.grid(row=1, column=0, padx=8)

        group = ctk.CTkLabel(card, text=case["group"], height=18,
                             font=ctk.CTkFont(size=11), text_color="gray55")
        group.grid(row=2, column=0, padx=8)

        alg = ctk.CTkLabel(card, text=case["alg"], wraplength=132, justify="center",
                           font=ctk.CTkFont(family="Courier New", size=11),
                           text_color="#ffcc00")
        alg.grid(row=3, column=0, padx=8, pady=(2, 4))

        status = ctk.CTkLabel(card, text="", height=20, cursor="hand2",
                              font=ctk.CTkFont(size=11, weight="bold"))
        status.grid(row=4, column=0, pady=(0, 8))
        status.bind("<Button-1>", lambda e, c=case: self._cycle_status(mode, c))

        for widget in (card, diagram, name, group, alg):
            widget.bind("<Button-1>",
                        lambda e, c=case: self.store.toggle(mode, c["name"]))
            widget.bind("<Double-Button-1>", lambda e, c=case: self._open(mode, c))
        self._cards[(mode, case["name"])] = (card, name, status)
        return card

    # ------------------------------------------------------------------
    def _cycle_status(self, mode, case):
        """Unlearned -> Learning -> Finished -> Unlearned."""
        current = self.store.status(mode, case["name"])
        self.store.set_status(mode, case["name"],
                              STATUSES[(STATUSES.index(current) + 1) % len(STATUSES)])

    def _open(self, mode, case):
        # the first click of the double-click toggled the card; put it back
        self.store.toggle(mode, case["name"])
        self._on_open_case(mode, case)

    def _refresh(self, mode):
        selection = self.store.selected[mode]
        for (m, case_name), (card, name, status) in self._cards.items():
            if m != mode:
                continue
            look = (case_name in selection, self.store.status(mode, case_name))
            if self._painted.get((m, case_name)) == look:
                continue                # reconfiguring ctk widgets is slow; skip unchanged
            self._painted[(m, case_name)] = look
            picked, s = look
            card.configure(border_color=C_SELECTED if picked else C_PANEL)
            name.configure(text_color=C_SELECTED if picked else ("gray10", "#DCE4EE"))
            status.configure(text=s.upper(), text_color=STATUS_COLOR[s])
        for (m, group), header in self._headers.items():
            if m == mode:
                members = [c["name"] for c in CASES[mode] if c["group"] == group]
                header.show(sum(1 for n in members if n in selection), len(members))
        self._tools[mode].refresh()
        self._layouts[mode]["my_groups"].refresh()
        self._practise_btn[mode].configure(
            text=f"Practise selected ({len(selection)})",
            state="normal" if selection else "disabled")


# ---------------------------------------------------------------------------
# Statistics Screen
# ---------------------------------------------------------------------------
class StatsScreen(ctk.CTkFrame):
    """
    Solves tab: for Full Solve, OLL or PLL, the session and all-time stats and
    every solve (this session or all time, optionally flagged only) with its
    ao5 / ao12; click a row, then +2 / DNF / flag / note / delete.
    OLL / PLL Progress tabs: per-case count, best and average.
    """

    LIMIT = 200                       # rows listed at most (the stats cover every solve)
    MODES = {"Full Solve": "full", "OLL": "oll", "PLL": "pll"}
    SCOPES = {"This session": "session", "All time": "all"}

    def __init__(self, parent, root, db):
        super().__init__(parent, fg_color="transparent")
        self.root = root
        self.db   = db
        self._scroll   = {}
        self._mode     = "full"
        self._scope    = "session"
        self._rows     = []           # dicts from Database.solve_table, newest first
        self._selected = None         # solve id picked in the table
        self._row_labels = {}         # solve id -> its row's labels
        self.actions   = SolveActions(db, self._after_action)
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header row
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, padx=20, pady=(20, 4), sticky="ew")
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(hdr, text="Statistics", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, sticky="w")
        ctk.CTkButton(
            hdr, text="Refresh", width=90, height=30,
            fg_color="gray30", hover_color="gray40",
            command=self.refresh,
        ).grid(row=0, column=1)

        # Tab view
        self.tabs = ctk.CTkTabview(self)
        self.tabs.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="nsew")

        for tab_name in ("Solves", "OLL Progress", "PLL Progress"):
            self.tabs.add(tab_name)
            tab = self.tabs.tab(tab_name)
            tab.grid_columnconfigure(0, weight=1)
            row = 0
            if tab_name == "Solves":
                self._build_solves_controls(tab)
                row = 4
            tab.grid_rowconfigure(row, weight=1)
            sf = ctk.CTkScrollableFrame(tab)
            sf.grid(row=row, column=0, sticky="nsew", padx=4, pady=4)
            self._scroll[tab_name] = sf

    def _build_solves_controls(self, tab):
        bar = ctk.CTkFrame(tab, fg_color="transparent")
        bar.grid(row=0, column=0, padx=4, pady=(2, 4), sticky="w")
        self.mode_seg = ctk.CTkSegmentedButton(bar, values=list(self.MODES),
                                               command=lambda v: self._set(mode=self.MODES[v]))
        self.mode_seg.set("Full Solve")
        self.mode_seg.grid(row=0, column=0, padx=(0, 16))
        self.scope_seg = ctk.CTkSegmentedButton(bar, values=list(self.SCOPES),
                                                command=lambda v: self._set(scope=self.SCOPES[v]))
        self.scope_seg.set("This session")
        self.scope_seg.grid(row=0, column=1, padx=(0, 16))
        self.flagged_only = ctk.CTkCheckBox(bar, text="Flagged only", width=110,
                                            command=lambda: self._set())
        self.flagged_only.grid(row=0, column=2)
        self.session_picker = SessionPicker(bar, self.db, self._mode, "Full Solve",
                                            on_change=self._set)
        self.session_picker.grid(row=1, column=0, columnspan=3, pady=(6, 0), sticky="w")

        self.stats_block = StatsBlock(tab, bg=tab.cget("fg_color")[1]
                                      if isinstance(tab.cget("fg_color"), (list, tuple))
                                      else tab.cget("fg_color"))
        self.stats_block.grid(row=1, column=0, padx=8, pady=(2, 4), sticky="w")

        self.buttons = SolveButtons(tab, lambda a: self.actions.run(self._selected_tuple(), a))
        self.buttons.grid(row=2, column=0, padx=4, pady=(2, 0), sticky="w")
        self.table_note = ctk.CTkLabel(tab, text="", height=16, font=ctk.CTkFont(size=11),
                                       text_color="gray55")
        self.table_note.grid(row=3, column=0, padx=8, sticky="w")

    def _set(self, mode=None, scope=None):
        if mode:
            self._mode = mode
        if scope:
            self._scope = scope
        self._selected = None
        self._build_solves()

    def refresh(self):
        self._build_solves()
        self._build_case_table(self._scroll["OLL Progress"], "oll", OLL_CASES)
        self._build_case_table(self._scroll["PLL Progress"], "pll", PLL_CASES)

    def _after_action(self):
        self._build_solves()
        if self._mode != "full":
            name = f"{self._mode.upper()} Progress"
            self._build_case_table(self._scroll[name], self._mode, CASES[self._mode])

    # ------------------------------------------------------------------
    @staticmethod
    def _clear(frame):
        for w in frame.winfo_children():
            w.destroy()

    # Table cells are plain tk labels: hundreds of CTkLabels took over a second
    # to create. They copy the scroll frame's background and ctk's font.
    def _cell(self, parent, text, row, col, width, color=None, bold=False, mono=False):
        if not hasattr(self, "_cell_style"):
            family = ctk.ThemeManager.theme["CTkFont"]["family"]
            self._cell_style = {
                "bg": parent._parent_canvas.cget("bg"),
                "font": (family, -_px(self, 13)),
                "bold": (family, -_px(self, 13), "bold"),
                "mono": ("Consolas", -_px(self, 13)),
            }
        st = self._cell_style
        lbl = tk.Label(parent, text=text, anchor="w", bd=0, bg=st["bg"], fg=color or C_TEXT,
                       font=st["bold"] if bold else st["mono"] if mono else st["font"])
        lbl.grid(row=row, column=col, padx=_px(self, 3), pady=_px(self, 3) if bold else _px(self, 2),
                 sticky="we")
        parent.grid_columnconfigure(col, minsize=_px(self, width))
        return lbl

    def _header_cell(self, parent, text, col, width):
        self._cell(parent, text, 0, col, width, bold=True)

    def _data_cell(self, parent, text, row, col, width, color=None, mono=False):
        return self._cell(parent, text, row, col, width, color=color, mono=mono)

    # ------------------------------------------------------------------
    def _build_solves(self):
        db, mode, scope = self.db, self._mode, self._scope
        titles = {v: k for k, v in self.MODES.items()}
        if self.session_picker.mode != mode:
            self.session_picker.set_mode(mode, titles[mode])
        else:
            self.session_picker.refresh()
        self.stats_block.update_stats(db.session_name(mode), db.stats(mode, "session"),
                                      db.stats(mode))
        flagged = bool(self.flagged_only.get())
        self._rows, total = db.solve_table(mode, scope, flagged_only=flagged, limit=self.LIMIT)
        where = f"“{db.session_name(mode)}”" if scope == "session" else "all"
        shown = f"Latest {self.LIMIT} shown; " if len(self._rows) >= self.LIMIT else ""
        self.table_note.configure(text=f"{shown}{total} solve(s) in {where}.  "
                                       "Click a row to pick it for the buttons above.")

        parent = self._scroll["Solves"]
        self._clear(parent)
        self._row_labels = {}
        if not self._rows:
            ctk.CTkLabel(parent, text="No solves here yet.",
                         text_color="gray55").grid(row=0, column=0, padx=20, pady=24)
            self._paint_selection()
            return

        case_col = mode != "full"
        headers = ["#", "Case", "Time", "ao5", "ao12", "Flag / note", "Date"]
        widths  = [44,  90,     82,     70,    70,     220,           150]
        if not case_col:
            del headers[1], widths[1]
        for col, (h, w) in enumerate(zip(headers, widths)):
            self._header_cell(parent, h, col, w)

        best = db.stats(mode, scope)["best"]
        for i, r in enumerate(self._rows, start=1):
            time_color = solve_color(r["penalty"]) or (C_RUNNING if r["time"] == best else None)
            vals = [(str(r["n"]), None, False)]
            if case_col:
                vals.append((r["case"] or "?", None, False))
            note = f"⚑ {r['note'] or ''}" if r["flagged"] else ""
            if len(note) > 34:
                note = note[:33] + "…"
            vals += [(fmt_solve(r["seconds"], r["penalty"]), time_color, True),
                     (fmt(r["ao5"]), None, True), (fmt(r["ao12"]), None, True),
                     (note, C_STOPPED, False), (r["ts"], "gray60", False)]
            labels = []
            for col, ((text, color, mono), w) in enumerate(zip(vals, widths)):
                lbl = self._data_cell(parent, text, i, col, w, color, mono)
                lbl.bind("<Button-1>", lambda e, sid=r["id"]: self.select(sid))
                labels.append(lbl)
            self._row_labels[r["id"]] = labels
        self._paint_selection()

    def select(self, solve_id):
        self._selected = None if self._selected == solve_id else solve_id
        self._paint_selection()

    def _selected_tuple(self):
        """The picked row as a Database.solves() tuple (what SolveActions takes)."""
        for r in self._rows:
            if r["id"] == self._selected:
                return (r["id"], r["case"], r["seconds"], r["penalty"], r["flagged"],
                        r["note"], r["ts"], r["session"])
        return None

    def _paint_selection(self):
        bg = self._scroll["Solves"]._parent_canvas.cget("bg")
        for sid, labels in self._row_labels.items():
            for lbl in labels:
                lbl.configure(bg=C_CURRENT if sid == self._selected else bg)
        solve = self._selected_tuple()
        label = (f"#{next(r['n'] for r in self._rows if r['id'] == self._selected)}  "
                 f"{fmt_solve(solve[2], solve[3])}:" if solve else "Pick a solve:")
        self.buttons.show(solve, label)

    def _build_case_table(self, parent, mode, cases):
        self._clear(parent)
        summary = {r[0]: r for r in self.db.case_summary(mode)}

        headers = ["Case",  "Group",  "Algorithm",  "N",  "Best", "Avg"]
        widths  = [90,      115,      330,          44,   76,     76]
        for col, (h, w) in enumerate(zip(headers, widths)):
            self._header_cell(parent, h, col, w)

        # best and average leave out DNFs (None when a case has only DNFs)
        for row_i, case in enumerate(cases, start=1):
            row  = summary.get(case["name"])
            n    = str(row[1]) if row else "—"
            best = fmt(row[2]) if row else "—"
            avg  = fmt(row[3]) if row else "—"
            # Truncate very long algorithms for the table
            alg  = case["alg"] if len(case["alg"]) <= 44 else case["alg"][:43] + "…"
            vals   = [case["name"], case["group"], alg, n, best, avg]
            colors = [None, None, None, None,
                      C_STOPPED if row and row[2] is not None else None, None]
            for col, (v, w, c) in enumerate(zip(vals, widths, colors)):
                self._data_cell(parent, v, row_i, col, w, c)


# ---------------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------------
class CubeTimerApp:

    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("Cube Timer")
        self.root.geometry("1120x720")
        self.root.minsize(980, 640)

        db_path  = Path(__file__).parent / "cube_times.db"
        self.db  = Database(db_path)

        self._active_screen = None
        self._screens       = {}
        self._nav_btns      = {}

        start = time.perf_counter()
        self._build_sidebar()
        self._build_content()
        self._build_screens()

        self.show_screen("full")

        self.root.bind("<KeyPress-space>", self._dispatch_space, add="+")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        # errors inside button/key callbacks would otherwise only reach stderr
        self.root.report_callback_exception = self._report_callback_exception
        log.info("started in %.2fs (database %s)", time.perf_counter() - start, db_path)

    # ------------------------------------------------------------------
    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self.root, width=175, corner_radius=0)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        ctk.CTkLabel(
            sidebar, text="CUBE TIMER",
            font=ctk.CTkFont(size=17, weight="bold"),
        ).pack(pady=(30, 6))

        ctk.CTkLabel(sidebar, text="─" * 18, text_color="gray35").pack(pady=(0, 10))

        nav_items = [
            ("full",  "Full Solve"),
            ("oll",   "OLL Practice"),
            ("pll",   "PLL Practice"),
            ("cases", "Case Gallery"),
            ("stats", "Statistics"),
        ]
        for key, label in nav_items:
            btn = ctk.CTkButton(
                sidebar, text=label,
                font=ctk.CTkFont(size=13),
                fg_color="transparent", hover_color="gray25",
                anchor="w", height=38,
                command=lambda k=key: self.show_screen(k),
            )
            btn.pack(fill="x", padx=10, pady=3)
            self._nav_btns[key] = btn

        ctk.CTkLabel(sidebar, text="v1.0", text_color="gray40",
                     font=ctk.CTkFont(size=11)).pack(side="bottom", pady=14)

    def _build_content(self):
        self.content = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
        self.content.pack(side="left", fill="both", expand=True)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

    def _build_screens(self):
        # Practice selection and case statuses: one store, every screen listens to it.
        self.store = SelectionStore(self.db)

        # Screens are built the first time they are opened (see screen()); building
        # them all up front made startup take seconds.
        self._factories = {
            "full":  lambda: FullSolveScreen(self.content, self.root, self.db),
            "oll":   lambda: CaseTrainerScreen(self.content, self.root, self.db, self.store,
                                               "oll", "OLL Practice"),
            "pll":   lambda: CaseTrainerScreen(self.content, self.root, self.db, self.store,
                                               "pll", "PLL Practice"),
            "cases": lambda: CasesScreen(self.content, self.root, self.db, self.store,
                                         self._open_case, self._practise_selected),
            "stats": lambda: StatsScreen(self.content, self.root, self.db),
        }

    def screen(self, name):
        """The screen called `name`, built on first use."""
        if name not in self._screens:
            start = time.perf_counter()
            screen = self._factories[name]()
            screen.grid(row=0, column=0, sticky="nsew")
            screen.grid_remove()
            self._screens[name] = screen
            log.info("built %s screen in %.2fs", name, time.perf_counter() - start)
        return self._screens[name]

    def _open_case(self, mode, case):
        """Gallery double-click: open the practice screen on that one case."""
        self.show_screen(mode)
        self.screen(mode).select_case(case)

    def _practise_selected(self, mode):
        """Gallery button: drill random cases from the selected set."""
        self.show_screen(mode)
        self.screen(mode).set_source("selected")

    # ------------------------------------------------------------------
    def show_screen(self, name: str):
        if self._active_screen and hasattr(self._active_screen, "_cancel_timer"):
            self._active_screen._cancel_timer()

        target = self.screen(name)
        for screen in self._screens.values():
            screen.grid_remove()
        target.grid()
        self._active_screen = target

        for key, btn in self._nav_btns.items():
            btn.configure(fg_color="gray25" if key == name else "transparent")

        if hasattr(self._active_screen, "on_show"):
            self._active_screen.on_show()
        if name == "stats":
            target.refresh()

    def _dispatch_space(self, event):
        if isinstance(event.widget, ctk.CTkButton):
            return
        if hasattr(self._active_screen, "timer_toggle"):
            self._active_screen.timer_toggle(event)

    @staticmethod
    def _report_callback_exception(exc_type, exc, tb):
        log.error("Error in UI callback", exc_info=(exc_type, exc, tb))
        traceback.print_exception(exc_type, exc, tb)

    def _on_close(self):
        log.info("closing")
        self.db.close()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
def main():
    setup_logging()
    app = CubeTimerApp()
    app.run()


if __name__ == "__main__":
    main()
