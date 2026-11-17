#!/usr/bin/env python3
"""
Cube Timer GUI - Rubik's Cube Practice Timer
Modern GUI built with customtkinter.
Shares the same SQLite database (cube_times.db) as the CLI version.

Requirements: pip install customtkinter rich
"""

import random
import time
from pathlib import Path

import customtkinter as ctk

from cube_timer import (
    OLL_CASES,
    PLL_CASES,
    Database,
    calc_ao,
    fmt,
    generate_scramble,
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

STATUSES = ["unlearned", "learning", "finished"]
STATUS_COLOR = {"unlearned": "gray50", "learning": "#ff9f1c", "finished": "#3fa7ff"}

FONT_TIMER  = ("Consolas",   72, "bold")
FONT_MONO   = ("Consolas",   14)
FONT_BOLD   = None           # filled in after ctk root exists (CTkFont needs root)
FONT_ALG    = ("Courier New", 14)
FONT_SMALL  = ("Segoe UI",   11)
FONT_NAV    = ("Segoe UI",   13)
FONT_TITLE  = ("Segoe UI",   20, "bold")


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
# Full Solve Screen
# ---------------------------------------------------------------------------
class FullSolveScreen(TimerScreenBase):

    def __init__(self, parent, root, db):
        super().__init__(parent, root, db)
        self._scramble = ""
        self._build_ui()
        self._new_scramble()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self, text="Full Solve", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, pady=(24, 8))

        # Scramble panel
        scramble_frame = ctk.CTkFrame(self, corner_radius=8)
        scramble_frame.grid(row=1, column=0, padx=40, pady=6, sticky="ew")
        scramble_frame.grid_columnconfigure(0, weight=1)

        self.scramble_label = ctk.CTkLabel(
            scramble_frame, text="",
            font=ctk.CTkFont(family="Consolas", size=15),
            wraplength=620, justify="center",
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

        # Result bar
        self.result_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=13), text_color="gray65",
        )
        self.result_label.grid(row=5, column=0, pady=(4, 24))

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
        self.status_label.configure(text=f"Saved  {fmt(elapsed)}  —  press SPACE for next scramble")
        self._refresh_result_bar()

    def _refresh_result_bar(self):
        rows = self.db.get("full", limit=12)
        if not rows:
            return
        times = [r[0] for r in rows]
        parts = [f"Last: {fmt(times[0])}",
                 f"Best: {fmt(min(times))}"]
        a5  = calc_ao(times, 5)
        a12 = calc_ao(times, 12)
        if a5:  parts.append(f"ao5: {fmt(a5)}")
        if a12: parts.append(f"ao12: {fmt(a12)}")
        self.result_label.configure(text="   │   ".join(parts))

    def _delete_last(self):
        if self.db.delete_last("full"):
            self.status_label.configure(text="Last time deleted.")
            self._refresh_result_bar()


# ---------------------------------------------------------------------------
# OLL / PLL Practice Screen
# ---------------------------------------------------------------------------
class CaseTrainerScreen(TimerScreenBase):
    """
    Drills last-layer cases. Each round picks a case at random from the chosen
    source (all cases, the set selected in the Case Gallery, or one group),
    shows a scramble that sets it up, and records the time against the case.
    """

    SLOWEST_COUNT = 10

    def __init__(self, parent, root, db, mode, title, selection, statuses):
        super().__init__(parent, root, db)
        self.mode      = mode                 # "oll" | "pll"
        self.title     = title
        self.cases     = CASES[mode]
        self.selection = selection            # shared set of names, edited in the gallery
        self.statuses  = statuses             # shared {name: status}, unlearned left out
        self.groups    = sorted({c["group"] for c in self.cases})

        # "all" | "selected" | "slowest" | "status:<status>" | "group:<name>"
        self._source       = "all"
        self._source_keys  = {}               # menu label -> source key
        self._current_case = None
        self._scramble     = ""
        self._build_ui()
        self._sync_pickers()
        self._pick_next_case()
        self._refresh_history()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        ctk.CTkLabel(self, text=self.title, font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, pady=(18, 6))

        # --- Source / case pickers ---
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

        ctk.CTkLabel(filter_row, text="Case:", font=ctk.CTkFont(size=13)).grid(
            row=0, column=2, padx=(0, 6))
        self.case_var = ctk.StringVar(value="Random")
        self.case_combo = ctk.CTkComboBox(
            filter_row, variable=self.case_var,
            values=["Random"] + [c["name"] for c in self.cases],
            width=150, command=self._on_case_change,
        )
        self.case_combo.grid(row=0, column=3, padx=(0, 18))

        ctk.CTkLabel(filter_row, text="Odds:", font=ctk.CTkFont(size=13)).grid(
            row=0, column=4, padx=(0, 6))
        self.odds = ctk.CTkSegmentedButton(filter_row, values=["Balanced", "Realistic"])
        self.odds.set("Balanced")
        self.odds.grid(row=0, column=5)

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

        self.result_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=13), text_color="gray65",
        )
        self.result_label.grid(row=7, column=0, pady=(4, 16))

        # --- History (latest attempts across all cases in this mode) ---
        side = ctk.CTkFrame(self, fg_color=C_PANEL, corner_radius=8, width=200)
        side.grid(row=0, column=1, rowspan=8, padx=(0, 16), pady=(20, 16), sticky="ns")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(side, text="History", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, pady=(12, 0))
        self.history_summary = ctk.CTkLabel(
            side, text="", height=18, font=ctk.CTkFont(size=11), text_color="gray55")
        self.history_summary.grid(row=1, column=0, pady=(0, 4))
        self.history_frame = ctk.CTkScrollableFrame(side, fg_color="transparent")
        self.history_frame.grid(row=2, column=0, padx=2, pady=(0, 8), sticky="nsew")
        self.history_frame.grid_columnconfigure(0, weight=1)

    # ------------------------------------------------------------------
    # Where cases are drawn from
    # ------------------------------------------------------------------
    def _status(self, case):
        return self.statuses.get(case["name"], "unlearned")

    def _source_options(self):
        """(key, menu label) for every place cases can be drawn from."""
        opts = [("all", "All cases"), ("selected", f"Selected ({len(self.selection)})"),
                ("slowest", f"Slowest {self.SLOWEST_COUNT}")]
        for status in STATUSES:
            n = sum(1 for c in self.cases if self._status(c) == status)
            opts.append((f"status:{status}", f"{status.title()} ({n})"))
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
            return timed[:self.SLOWEST_COUNT]
        if kind == "status":
            return [c for c in self.cases if self._status(c) == arg]
        return [c for c in self.cases if c["group"] == arg]

    def _on_source_change(self, label):
        self.set_source(self._source_keys.get(label, "all"))

    def set_source(self, source):
        """Switch the pool cases are drawn from and deal a new case."""
        self._source = source
        self._sync_pickers()
        self.case_var.set("Random")
        self._pick_next_case()

    def _sync_pickers(self):
        opts = self._source_options()
        self._source_keys = {label: key for key, label in opts}
        self.source_menu.configure(values=[label for _, label in opts])
        self.source_var.set(dict(opts).get(self._source, "All cases"))
        self.case_combo.configure(
            values=["Random"] + [c["name"] for c in (self._pool() or self.cases)])

    def on_show(self):
        """Called when the screen is opened: selection or statuses may have changed."""
        self._sync_pickers()
        if self.case_var.get() == "Random" and self._source != "all":
            if self._current_case is None or self._current_case not in self._pool():
                self._pick_next_case()
        if self._current_case:
            self.status_seg.set(self._status(self._current_case).title())
        self._refresh_history()

    def _on_status_change(self, value):
        if not self._current_case:
            return
        status = value.lower()
        name = self._current_case["name"]
        if status == "unlearned":
            self.statuses.pop(name, None)
        else:
            self.statuses[name] = status
        self.db.set_status(self.mode, name, status)
        self._sync_pickers()

    def _show_alg(self):
        if self.hint_switch.get():
            self.case_alg_label.configure(
                text=self._current_case["alg"] if self._current_case else "",
                text_color="#ffcc00")
        else:
            self.case_alg_label.configure(text="algorithm hidden", text_color="gray45")

    def select_case(self, case):
        """Practise one specific case (used by the case gallery)."""
        self._source = "all"
        self._sync_pickers()
        self.case_var.set(case["name"])
        self._load_case(case)

    # ------------------------------------------------------------------
    def _on_case_change(self, value):
        if value == "Random":
            return
        matches = [c for c in self.cases if c["name"] == value]
        if matches:
            self._load_case(matches[0])

    def _pick_next_case(self):
        self._cancel_timer()
        note = None
        sel  = self.case_var.get()
        case = None if sel == "Random" else next(
            (c for c in self.cases if c["name"] == sel), None)
        if case is None:
            pool = self._pool()
            if not pool:
                pool = self.cases
                note = {
                    "selected": "Nothing selected yet - pick cases in the Case Gallery.",
                    "slowest":  "No times yet to find the slowest cases.",
                    "status":   "No cases have that status yet.",
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
        self._refresh_result_bar()

    def _next(self):
        self._pick_next_case()

    def _save_result(self, elapsed):
        if not self._current_case:
            return
        self.db.add(self.mode, elapsed,
                    case_name=self._current_case["name"], scramble=self._scramble)
        self.status_label.configure(text=f"Saved  {fmt(elapsed)}  —  press SPACE for next case")
        self._refresh_result_bar()
        self._refresh_history()

    def _refresh_result_bar(self):
        if not self._current_case:
            return
        rows = self.db.get(self.mode, case_name=self._current_case["name"], limit=12)
        if not rows:
            self.result_label.configure(text="No times for this case yet.")
            return
        times = [r[0] for r in rows]
        parts = [f"Last: {fmt(times[0])}", f"Best: {fmt(min(times))}"]
        a5  = calc_ao(times, 5)
        a12 = calc_ao(times, 12)
        if a5:  parts.append(f"ao5: {fmt(a5)}")
        if a12: parts.append(f"ao12: {fmt(a12)}")
        self.result_label.configure(text="   │   ".join(parts))

    def _refresh_history(self):
        for w in self.history_frame.winfo_children():
            w.destroy()
        rows = self.db.recent(self.mode, limit=40)
        if not rows:
            self.history_summary.configure(text="No times yet")
            return
        times = [r[1] for r in rows]
        self.history_summary.configure(
            text=f"last {len(times)}   mean {fmt(sum(times) / len(times))}")
        for i, (name, seconds, _ts) in enumerate(rows):
            ctk.CTkLabel(self.history_frame, text=name or "?", anchor="w", height=22,
                         font=ctk.CTkFont(size=12)).grid(row=i, column=0, sticky="w", padx=(4, 0))
            ctk.CTkLabel(self.history_frame, text=fmt(seconds), anchor="e", height=22,
                         font=ctk.CTkFont(family="Consolas", size=12),
                         text_color=C_STOPPED if i == 0 else None).grid(
                row=i, column=1, sticky="e", padx=(6, 4))

    def _delete_last(self):
        """Removes the newest attempt in this mode (the top row of the history)."""
        if self.db.delete_last(self.mode):
            self.status_label.configure(text="Last time deleted.")
            self._refresh_result_bar()
            self._refresh_history()


# ---------------------------------------------------------------------------
# Case Gallery Screen  (a picture of every OLL and PLL case; pick a practice set)
# ---------------------------------------------------------------------------
class CasesScreen(ctk.CTkFrame):

    COLUMNS   = 4
    ADD_GROUP = "Add cases…"

    def __init__(self, parent, root, db, selections, statuses, on_open_case, on_practise):
        super().__init__(parent, fg_color="transparent")
        self.root          = root
        self.db            = db
        self.selections    = selections      # {"oll": set of names, "pll": set of names}
        self.statuses      = statuses        # {"oll": {name: status}, "pll": {...}}
        self._on_open_case = on_open_case    # on_open_case(mode, case)
        self._on_practise  = on_practise     # on_practise(mode)
        self._cards        = {}              # (mode, case name) -> (card, name label, status label)
        self._practise_btn = {}
        self._build_ui()

    def on_show(self):
        """Statuses can be changed on the practice screens too."""
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
            for col in range(self.COLUMNS):
                sf.grid_columnconfigure(col, weight=1, uniform="cards")
            for i, case in enumerate(cases):
                self._build_card(sf, mode, case).grid(
                    row=i // self.COLUMNS, column=i % self.COLUMNS,
                    padx=5, pady=5, sticky="nsew")
            self._refresh(mode)

    def _build_toolbar(self, parent, mode):
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid_columnconfigure(3, weight=1)
        names = [c["name"] for c in CASES[mode]]

        ctk.CTkButton(bar, text="Select all", width=90, height=30,
                      fg_color="gray30", hover_color="gray40",
                      command=lambda: self._set(mode, names)).grid(row=0, column=0, padx=(0, 6))
        ctk.CTkButton(bar, text="Clear", width=70, height=30,
                      fg_color="gray30", hover_color="gray40",
                      command=lambda: self._set(mode, [])).grid(row=0, column=1, padx=(0, 6))

        group_var = ctk.StringVar(value=self.ADD_GROUP)
        status_items = {f"{s.title()} cases": s for s in STATUSES}

        def add_group(item):
            group_var.set(self.ADD_GROUP)
            if item in status_items:
                statuses = self.statuses[mode]
                names = {c["name"] for c in CASES[mode]
                         if statuses.get(c["name"], "unlearned") == status_items[item]}
            else:
                names = {c["name"] for c in CASES[mode] if c["group"] == item}
            self._set(mode, self.selections[mode] | names)

        ctk.CTkOptionMenu(bar, variable=group_var, width=150, height=30,
                          values=list(status_items) + sorted({c["group"] for c in CASES[mode]}),
                          command=add_group).grid(row=0, column=2)

        btn = ctk.CTkButton(bar, text="", width=190, height=30,
                            command=lambda: self._on_practise(mode))
        btn.grid(row=0, column=4)
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
            widget.bind("<Button-1>", lambda e, c=case: self._toggle(mode, c))
            widget.bind("<Double-Button-1>", lambda e, c=case: self._open(mode, c))
        self._cards[(mode, case["name"])] = (card, name, status)
        return card

    # ------------------------------------------------------------------
    def _cycle_status(self, mode, case):
        """Unlearned -> Learning -> Finished -> Unlearned."""
        statuses = self.statuses[mode]
        current = statuses.get(case["name"], "unlearned")
        status = STATUSES[(STATUSES.index(current) + 1) % len(STATUSES)]
        if status == "unlearned":
            statuses.pop(case["name"], None)
        else:
            statuses[case["name"]] = status
        self.db.set_status(mode, case["name"], status)
        self._refresh(mode)

    def _toggle(self, mode, case):
        self._set(mode, self.selections[mode] ^ {case["name"]})

    def _open(self, mode, case):
        # the first click of the double-click toggled the card; put it back
        self._toggle(mode, case)
        self._on_open_case(mode, case)

    def _set(self, mode, names):
        """Replace the selection for a mode, save it, and repaint the cards."""
        selection = self.selections[mode]
        names = set(names)
        selection.clear()            # keep the same set object: the trainers share it
        selection.update(names)
        self.db.set_selected(mode, selection)
        self._refresh(mode)

    def _refresh(self, mode):
        selection = self.selections[mode]
        statuses = self.statuses[mode]
        for (m, case_name), (card, name, status) in self._cards.items():
            if m != mode:
                continue
            picked = case_name in selection
            card.configure(border_color=C_SELECTED if picked else C_PANEL)
            name.configure(text_color=C_SELECTED if picked else ("gray10", "#DCE4EE"))
            s = statuses.get(case_name, "unlearned")
            if status.cget("text") != s.upper():
                status.configure(text=s.upper(), text_color=STATUS_COLOR[s])
        self._practise_btn[mode].configure(
            text=f"Practise selected ({len(selection)})",
            state="normal" if selection else "disabled")


# ---------------------------------------------------------------------------
# Statistics Screen
# ---------------------------------------------------------------------------
class StatsScreen(ctk.CTkFrame):

    def __init__(self, parent, root, db):
        super().__init__(parent, fg_color="transparent")
        self.root = root
        self.db   = db
        self._scroll = {}
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

        for tab_name in ("Full Solve", "OLL Progress", "PLL Progress"):
            self.tabs.add(tab_name)
            tab = self.tabs.tab(tab_name)
            tab.grid_columnconfigure(0, weight=1)
            tab.grid_rowconfigure(0, weight=1)
            sf = ctk.CTkScrollableFrame(tab)
            sf.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
            self._scroll[tab_name] = sf

    def refresh(self):
        self._build_session_table(self._scroll["Full Solve"],    "full")
        self._build_case_table(self._scroll["OLL Progress"], "oll", OLL_CASES)
        self._build_case_table(self._scroll["PLL Progress"], "pll", PLL_CASES)

    # ------------------------------------------------------------------
    @staticmethod
    def _clear(frame):
        for w in frame.winfo_children():
            w.destroy()

    def _header_cell(self, parent, text, col, width):
        ctk.CTkLabel(
            parent, text=text, width=width, anchor="w",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=0, column=col, padx=3, pady=(4, 2), sticky="w")

    def _data_cell(self, parent, text, row, col, width, color=None):
        ctk.CTkLabel(
            parent, text=text, width=width, anchor="w",
            text_color=color,
        ).grid(row=row, column=col, padx=3, pady=1, sticky="w")

    # ------------------------------------------------------------------
    def _build_session_table(self, parent, mode):
        self._clear(parent)
        rows = self.db.get(mode, limit=50)

        if not rows:
            ctk.CTkLabel(parent, text="No times recorded yet.",
                         text_color="gray55").grid(row=0, column=0, padx=20, pady=24)
            return

        headers = ["#",   "Time", "ao5",  "ao12", "Timestamp"]
        widths  = [44,    82,     82,     82,     170]
        for col, (h, w) in enumerate(zip(headers, widths)):
            self._header_cell(parent, h, col, w)

        all_t = [r[0] for r in rows]
        best  = min(all_t)
        for i, (t, ts) in enumerate(rows):
            a5  = calc_ao(all_t[i:], 5)
            a12 = calc_ao(all_t[i:], 12)
            vals   = [str(len(rows) - i), fmt(t),
                      fmt(a5) if a5 else "—", fmt(a12) if a12 else "—", ts]
            colors = [None, C_RUNNING if t == best else None, None, None, None]
            for col, (v, w, c) in enumerate(zip(vals, widths, colors)):
                self._data_cell(parent, v, i + 1, col, w, c)

        # Summary
        mean = sum(all_t) / len(all_t)
        a5   = calc_ao(all_t, 5)
        a12  = calc_ao(all_t, 12)
        summary = (f"Count: {len(all_t)}   Best: {fmt(best)}   Mean: {fmt(mean)}"
                   + (f"   ao5: {fmt(a5)}"  if a5  else "")
                   + (f"   ao12: {fmt(a12)}" if a12 else ""))
        ctk.CTkLabel(parent, text=summary, text_color="gray60",
                     font=ctk.CTkFont(size=12)).grid(
            row=len(rows) + 1, column=0, columnspan=5,
            padx=4, pady=(10, 4), sticky="w")

    def _build_case_table(self, parent, mode, cases):
        self._clear(parent)
        summary = {r[0]: r for r in self.db.case_summary(mode)}

        headers = ["Case",  "Group",  "Algorithm",  "N",  "Best", "Avg"]
        widths  = [90,      115,      330,          44,   76,     76]
        for col, (h, w) in enumerate(zip(headers, widths)):
            self._header_cell(parent, h, col, w)

        for row_i, case in enumerate(cases, start=1):
            row  = summary.get(case["name"])
            n    = str(row[1]) if row else "—"
            best = fmt(row[2]) if row else "—"
            avg  = fmt(row[3]) if row else "—"
            # Truncate very long algorithms for the table
            alg  = case["alg"] if len(case["alg"]) <= 44 else case["alg"][:43] + "…"
            vals   = [case["name"], case["group"], alg, n, best, avg]
            colors = [None, None, None, None,
                      C_STOPPED if row else None, None]
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
        self.root.geometry("1060x700")
        self.root.minsize(920, 620)

        db_path  = Path(__file__).parent / "cube_times.db"
        self.db  = Database(db_path)

        self._active_screen = None
        self._screens       = {}
        self._nav_btns      = {}

        self._build_sidebar()
        self._build_content()
        self._build_screens()

        self.show_screen("full")

        self.root.bind("<KeyPress-space>", self._dispatch_space, add="+")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

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
        # Cases picked for practice; the gallery edits these sets, the trainers read them.
        self.selections = {mode: self.db.get_selected(mode) for mode in ("oll", "pll")}
        # Learning / finished marks per case; shared the same way.
        self.statuses = {mode: self.db.get_statuses(mode) for mode in ("oll", "pll")}

        self._screens = {
            "full":  FullSolveScreen(self.content, self.root, self.db),
            "oll":   CaseTrainerScreen(self.content, self.root, self.db, "oll", "OLL Practice",
                                       self.selections["oll"], self.statuses["oll"]),
            "pll":   CaseTrainerScreen(self.content, self.root, self.db, "pll", "PLL Practice",
                                       self.selections["pll"], self.statuses["pll"]),
            "cases": CasesScreen(self.content, self.root, self.db, self.selections,
                                 self.statuses, self._open_case, self._practise_selected),
            "stats": StatsScreen(self.content, self.root, self.db),
        }
        for screen in self._screens.values():
            screen.grid(row=0, column=0, sticky="nsew")
            screen.grid_remove()

    def _open_case(self, mode, case):
        """Gallery double-click: open the practice screen on that one case."""
        self.show_screen(mode)
        self._screens[mode].select_case(case)

    def _practise_selected(self, mode):
        """Gallery button: drill random cases from the selected set."""
        self.show_screen(mode)
        self._screens[mode].set_source("selected")

    # ------------------------------------------------------------------
    def show_screen(self, name: str):
        if self._active_screen and hasattr(self._active_screen, "_cancel_timer"):
            self._active_screen._cancel_timer()

        for screen in self._screens.values():
            screen.grid_remove()
        self._screens[name].grid()
        self._active_screen = self._screens[name]

        for key, btn in self._nav_btns.items():
            btn.configure(fg_color="gray25" if key == name else "transparent")

        if hasattr(self._active_screen, "on_show"):
            self._active_screen.on_show()
        if name == "stats":
            self._screens["stats"].refresh()

    def _dispatch_space(self, event):
        if isinstance(event.widget, ctk.CTkButton):
            return
        if hasattr(self._active_screen, "timer_toggle"):
            self._active_screen.timer_toggle(event)

    def _on_close(self):
        self.db.close()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
def main():
    app = CubeTimerApp()
    app.run()


if __name__ == "__main__":
    main()
