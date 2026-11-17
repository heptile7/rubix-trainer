# CLAUDE.md

Guidance for Claude Code when working in this project.

## What this is

A Rubik's Cube practice timer in Python: full solves plus OLL (57 cases) and PLL (21 cases) drills, with times stored in SQLite. Two front ends share one data layer. Runs on Windows; no build step, no package structure, no git repository.

## Commands

```
pip install -r requirements.txt   # rich, customtkinter
python cube_timer_gui.py          # GUI
python cube_timer.py              # terminal app (interactive, blocks on input)
python cube_diagram.py            # validate every OLL/PLL algorithm
python make_scrambles.py [n]      # regenerate case_scrambles.json (n per case, default 10; ~90 s)
```

There is no test suite. `python cube_diagram.py` is the only automated check: run it after touching any algorithm or the simulator. It must print `All OLL and PLL algorithms check out.`

## Layout

- `cube_timer.py` — the data layer and the CLI in one file: `OLL_CASES`, `PLL_CASES`, `generate_scramble`, `invert_alg`, `case_scramble`, `setup_scramble`, `fmt`, `calc_ao`, `Database`, then the `rich`-based terminal modes.
- `make_scrambles.py` — standalone pure-Python Kociemba two-phase solver (cubie model, move/pruning tables cached as a pickle in the system temp folder) that writes `case_scrambles.json`. Not imported by the app.
- `case_scrambles.json` — `{"scrambles": {case name: [scramble, ...]}}`, generated; safe to regenerate.
- `cube_timer_gui.py` — customtkinter app. Imports the data layer from `cube_timer.py`. `CubeTimerApp` owns a sidebar and one frame per screen, shown and hidden with `grid()` / `grid_remove()`.
- `cube_diagram.py` — sticker-level cube simulator and `CaseDiagram`, a plain `tk.Canvas` that draws a case. Depends only on tkinter.
- `cube_times.db` — the user's recorded times. **User data: never delete, reset or overwrite it.** Tests that record times should use a temporary database path.

## Things to know before editing

**Case names are database keys.** Times are stored with `case_name` set to the case's `name` (e.g. `"OLL 21"`, `"T Perm"`). Renaming a case orphans its history.

**Importing `cube_timer` requires `rich`.** The module exits at import time if `rich` is missing, and the GUI imports from it.

**Case pictures are derived, not stored.** `case_state(alg)` applies the inverse of the algorithm to a solved cube (yellow up, green front); the widget draws the resulting top layer. There are no image files and Pillow is not installed. A case is drawn as PLL (side colours and arrows) when its top face is all yellow, otherwise as OLL.

**Simulator conventions.** Axes: x right, y up, z front. `_turn(v, axis)` is a quarter turn clockwise seen from the positive end. `_MOVES` maps each letter to (axis, layers, direction) and supports face turns, wide turns (`r l u d f b`), slices (`M E S`) and rotations (`x y z`) with `'` and `2` suffixes. A new move letter must be added there.

**PLL arrows ignore a final turn of the top layer.** Several listed algorithms finish one U turn from solved, so `_arrows` tries all four alignments and keeps the simplest (fewest pieces moved, then shortest cycles, then fewest corners).

**Timer screens share a base class.** `FullSolveScreen` and `CaseTrainerScreen` extend `TimerScreenBase`, which runs the idle → running → stopped state machine and builds the case panel (`_build_case_panel`). Subclasses supply `timer_label`, `start_btn`, `_next()` and `_save_result()`. One `CaseTrainerScreen` class serves both OLL and PLL practice, parametrised by mode.

**The practice selection is a shared set.** `CubeTimerApp.selections` maps `"oll"` / `"pll"` to a set of case names, loaded from the `selected_cases` table. The gallery (`CasesScreen`) mutates those sets in place and saves them; the trainers hold the same objects. Never rebind them to a new set. Screens with an `on_show()` method get it called from `show_screen`.

**Statuses.** `CubeTimerApp.statuses` maps mode to a `{case name: "learning" | "finished"}` dict (unlearned cases are absent), loaded from the `case_status` table and shared like the selection sets: mutate in place, never rebind. Both the gallery (status chip, click cycles) and the trainer (`status_seg`) write it.

**Trainer sources.** `CaseTrainerScreen._source` is a key: `all`, `selected`, `slowest`, `status:<status>` or `group:<name>`; `_source_options()` gives (key, label) pairs and `_source_keys` maps labels back. *Slowest* uses `Database.recent_means` (mean of the last 5 per case). *Realistic* odds weight cases by `case_weight(alg)` in `cube_diagram.py`.

**Scrambles.** The trainers call `setup_scramble(case)`: a random entry from `case_scrambles.json` plus a random U turn, falling back to `case_scramble(alg)` (inverse algorithm with random U turns) when the case has none. Generated scrambles are verified at creation by comparing facelet strings with the target; OLL targets include a random PLL. On the practice screens the picture comes from `CaseDiagram.set_scramble`, so it matches the scrambled cube; the gallery uses `set_case(alg)`. The scramble is stored with each attempt in `times.scramble`.

**Some algorithms contain rotations** (e.g. V Perm has a `y`). A check that the cube is solved by comparing each sticker with its home position fails for those; compare colours relative to the centres (as `make_scrambles.facelets` does) instead.

**Gallery clicks.** A click toggles selection and a double-click opens that case. Tk delivers the first click of a double-click as a normal click, so `_open` toggles the card back.

**Plain canvases need manual handling inside customtkinter.** `CaseDiagram` is not scaled by customtkinter, so size it with `_px(widget, size)`, and give it an explicit background matching its parent (`C_PANEL`).

**Space bar is bound on the root window** and dispatched to the active screen's `timer_toggle`. Screens without that method ignore it.

## Verifying GUI changes

The GUI can be driven without user input: build `CubeTimerApp()`, call `app.show_screen(name)` and `app.root.update()` in a loop, then `app._on_close()`. When the test records times or changes the selection, first point `cube_timer_gui.Database` at a temporary copy of the database. Pillow is not available for screenshots; capturing the window region with PowerShell's `System.Drawing` `CopyFromScreen` works.
