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

**Post-turn hook.** `.claude/settings.json` registers a Stop hook, `.claude/hooks/post_turn.py`, which runs after every turn:
- removes stray `pytest-cache-files-*` folders;
- byte-compiles every script and runs `cube_diagram.py`, when a `.py` file changed;
- asks once per change for README.md / CLAUDE.md to be updated, when code is newer than them.

A failed check or stale docs returns `{"decision": "block"}`, so the turn continues. It never blocks twice in a row. Runs are logged to `.claude/hook.log`, and state is kept in `.claude/hook_state.json`; both are git-ignored. If it asks for docs and nothing user- or maintainer-facing changed, say so; it will not ask again for that change.

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

**Screens are built lazily.** `CubeTimerApp.screen(name)` builds a screen on first use from `_factories`; only Full Solve exists at startup (about 0.6 s, against 5 s when everything was built up front). Use `app.screen(name)`, not `app._screens[name]`, for a screen that may not exist yet. Store listeners skip hidden screens (`winfo_ismapped()`), which repaint in `on_show`.

**Keep repaints cheap.** Reconfiguring customtkinter widgets is slow. The picker and gallery remember what each tile last showed (`_painted`) and touch only tiles that changed. Picker tiles and Statistics cells are plain `tk` widgets (customtkinter versions made pages take seconds to open), so they need explicit colours and fonts and `_px` scaling.

**Logging.** `setup_logging()` (called from `main()` only, so scripted tests do not write the log) sends the `cube_timer.*` loggers to a rotating `cube_timer.log`, at INFO, or DEBUG with `CUBE_TIMER_DEBUG=1`. Uncaught errors, including ones inside Tk callbacks (`report_callback_exception`), are logged. Log user-visible state changes at INFO and per-click noise at DEBUG.

**Selection and statuses go through `SelectionStore`.** `CubeTimerApp.store` holds `selected[mode]` (set of case names, table `selected_cases`) and `statuses[mode]` (`{name: "learning" | "finished"}`; unlearned cases are absent, table `case_status`). It also holds `custom[mode]` (`{group name: set of case names}`, table `custom_groups`, the user's saved groups). Change all of these only through its methods: `set`, `toggle`, `toggle_group`, `set_status`, `mark_selected` (bulk status for the selection), `save_group`, `delete_group`, `load_group`. A loaded group becomes `active[mode]`. From then on the selection is a working copy, and the group changes only via `save_active`; `pending_changes`, `revert_active` and `close_active` complete the edit cycle shown in `MyGroups`' edit bar. Each saves to the database and calls every `store.listen(fn)` listener with the mode, which is how the gallery, both trainers' pickers, the toolbars and the From counts stay in sync. The sets are mutated in place, never rebound. Screens with an `on_show()` method also get it called from `show_screen`.

**Selection widgets.**
- `SelectionTools`: All / None / Slowest 10, "Mark selected as" status buttons, Save as group… and the count. `compact=True` stacks it for the side column. `ask_name` can be replaced in tests.
- `MyGroups`: saved-group chips; click loads, ✕ deletes after `confirm`, which can be replaced in tests.
- `GroupHeader`: `Dot (3/8)` plus a ☑/☐/◩ group tick and an optional fold arrow.
- `CasePicker`: scrollable mini `CaseDiagram` tiles per group, with `MyGroups` on top.

These are shared by the trainer's side column and the gallery, and groups appear in case-list order (`group_order`). The trainer's side column (min `SIDE_WIDTH`, grid weight 2 against the main column's 3) has Cases / History tabs.

**Layouts follow the window.** `CasePicker._reflow` and `CasesScreen._layout` re-grid on `<Configure>` of the scroll frame's `_parent_canvas`, debounced with `after(120)`: more tiles or columns per row, and picker tiles resized with `CaseDiagram.resize`. When changing a grid's column count, reset the weight/uniform of columns that are no longer used, or they keep taking space.

The From menu also lists custom groups as `custom:<name>` sources.

**Trainer sources and pinning.** `CaseTrainerScreen._source` is a key: `all`, `selected`, `slowest`, `status:<status>` or `group:<name>`. `_source_options()` gives (key, label) pairs and `_source_keys` maps labels back. Editing the set from the trainer (tile click, group tick, tools) switches the source to `selected` via `_on_set_edited`. `_pinned` (a case, or None) overrides random dealing: it is set by double-click (`_pin`, which undoes the first click's toggle and restores the previous source) or by `select_case` from the gallery, and cleared by `unpin` or by changing the source. *Slowest* uses `Database.recent_means` (mean of the last 5 per case). *Realistic* odds weight cases by `case_weight(alg)` in `cube_diagram.py`.

**Scrambles.** The trainers call `setup_scramble(case)`: a random entry from `case_scrambles.json` plus a random U turn, falling back to `case_scramble(alg)` (inverse algorithm with random U turns) when the case has none. Generated scrambles are verified at creation by comparing facelet strings with the target; OLL targets include a random PLL. On the practice screens the picture comes from `CaseDiagram.set_scramble`, so it matches the scrambled cube; the gallery uses `set_case(alg)`. The scramble is stored with each attempt in `times.scramble`.

**Some algorithms contain rotations** (e.g. V Perm has a `y`). A check that the cube is solved by comparing each sticker with its home position fails for those; compare colours relative to the centres (as `make_scrambles.facelets` does) instead.

**Clicks on cases.** In the gallery and the picker, a click toggles selection and a double-click pins/opens that case. Tk delivers the first click of a double-click as a normal click, so `_open` / `_pin` toggle the case back. In scripted tests, `event_generate('<Double-Button-1>')` is not allowed, so call the handler directly. Bindings on a CTkLabel sit on its inner `_label`, so generate events on that.

**Plain canvases need manual handling inside customtkinter.** `CaseDiagram` is not scaled by customtkinter, so size it with `_px(widget, size)`, and give it an explicit background matching its parent (`C_PANEL`).

**Space bar is bound on the root window** and dispatched to the active screen's `timer_toggle`. Screens without that method ignore it.

## Verifying GUI changes

The GUI can be driven without user input: build `CubeTimerApp()`, call `app.show_screen(name)` and `app.root.update()` in a loop, then `app._on_close()`. When the test records times or changes the selection, first point `cube_timer_gui.Database` at a temporary copy of the database. Pillow is not available for screenshots; capturing the window region with PowerShell's `System.Drawing` `CopyFromScreen` works.
