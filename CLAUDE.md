# CLAUDE.md

Guidance for Claude Code when working in this project.

## What this is

A Rubik's Cube practice timer in Python: full solves plus OLL (57 cases) and PLL (21 cases) drills, with times stored in SQLite. Three front ends share one data layer: a web app (FastAPI + plain JS), a customtkinter GUI and a terminal app. Runs on Windows; no build step, no package structure, no git repository.

## Commands

```
pip install -r requirements.txt   # rich, customtkinter, fastapi, uvicorn
python cube_web.py                # web app (opens the browser; --no-browser, --port N, --window)
python cube_timer_gui.py          # GUI
python make_shortcut.py           # desktop shortcut to the GUI (--start-menu, --remove)
python cube_timer.py              # terminal app (interactive, blocks on input)
python cube_diagram.py            # validate every OLL/PLL algorithm
python make_scrambles.py [n]      # regenerate case_scrambles.json (n per case, default 10; ~90 s)
```

There is no test suite. `python cube_diagram.py` is the only check that runs automatically: run it after touching any algorithm or the simulator. It must print `All OLL and PLL algorithms check out.`

**Checks before committing.** The `commit` skill (`.claude/skills/commit/`) runs the right checks for whatever changed, commits with a message in the project's format, then pushes to `origin` (never force-pushing): `python .claude/skills/commit/scripts/run_checks.py` (`--all` runs every check, `--list` only previews). It has scripted checks for the terminal app, the GUI, the web API and the web page in headless Chrome, and each uses a temporary copy of the database. Commit and push finished, tested work through it. Stage files by name, and never stage `cube_times.db`: it is tracked, but it holds the user's times.

**Post-turn hook.** `.claude/settings.json` registers a Stop hook, `.claude/hooks/post_turn.py`, which runs after every turn:
- removes stray `pytest-cache-files-*` folders;
- byte-compiles every script and runs `cube_diagram.py`, when a `.py` file changed;
- asks once per change for README.md / CLAUDE.md to be updated, when code is newer than them.

A failed check or stale docs returns `{"decision": "block"}`, so the turn continues. It never blocks twice in a row. Runs are logged to `.claude/hook.log`, and state is kept in `.claude/hook_state.json`; both are git-ignored. If it asks for docs and nothing user- or maintainer-facing changed, say so; it will not ask again for that change.

## Layout

- `cube_timer.py` — the data layer and the CLI in one file: `OLL_CASES`, `PLL_CASES`, `generate_scramble`, `invert_alg`, `case_scramble`, `setup_scramble`, `DNF`, `effective`, `fmt`, `fmt_solve`, `calc_ao`, `best_ao`, `solve_stats`, `Database`, then the `rich`-based terminal modes.
- `make_scrambles.py` — standalone pure-Python Kociemba two-phase solver (cubie model, move/pruning tables cached as a pickle in the system temp folder) that writes `case_scrambles.json`. Not imported by the app.
- `case_scrambles.json` — `{"scrambles": {case name: [scramble, ...]}}`, generated; safe to regenerate.
- `cube_timer_gui.py` — customtkinter app. Imports the data layer from `cube_timer.py`. `CubeTimerApp` owns a sidebar and one frame per screen, shown and hidden with `grid()` / `grid_remove()`.
- `make_shortcut.py` — makes the Windows shortcut `Cube Timer.lnk`. The target is the running Python's `pythonw.exe` with `cube_timer_gui.py` as its argument, so there's no console and no bundle to rebuild. It goes on the Desktop (via `[Environment]::GetFolderPath`, which follows OneDrive) and, with `--start-menu`, in Programs. The shortcut is made through PowerShell's `WScript.Shell` COM object, with no pywin32. The script checks that this Python can import `customtkinter` and `rich` first. `write_icon()` draws `cube_timer.ico` in pure Python: PNG images at 16 to 256 px inside an ICO, no Pillow.
- **Running under pythonw.** The shortcut runs the GUI with no console, so the GUI's third-party imports are wrapped. A missing package (including `rich`, whose absence makes `cube_timer` exit) shows a `_cannot_start` dialog with the pip command. `main()` sets the Windows AppUserModelID `CubeTimer.Desktop` so the app gets its own taskbar button, and `CubeTimerApp` sets `cube_timer.ico` as the window icon (`ICON_FILE`), which also stops customtkinter from replacing it with its own.
- `cube_io.py` — export (`export_csv`, `export_backup`, `export_cstimer`) and import (`import_any` → `import_backup` / `import_cstimer`, after `backup_before_import` copies the file to `cube_times.before-import-*.db`). Imports merge: sessions matched by (mode, name) or made with `Database.create_session` (not selected), attempts deduplicated on (mode, seconds to the ms, ts) and inserted with `Database.add_imported`, then one commit. csTimer sessions named `OLL – …` / `PLL – …` go back to that mode, with the case taken from the comment. Bad files raise `ImportProblem` with a message for the user. Used by both front ends.
- `cube_web.py` — FastAPI server for the web app. `create_app(db_path)` builds it (tests pass a temporary database path); `main()` runs uvicorn on 127.0.0.1 from port 8765 up.
- `web/` — the web page: `index.html`, `style.css`, `js/*.js` ES modules. No framework, no build step, no npm (Node here is 16).
- `cube_diagram.py` — sticker-level cube simulator and `CaseDiagram`, a plain `tk.Canvas` that draws a case. Depends only on tkinter.
- `cube_times.db` — the user's recorded times. **User data: never delete, reset or overwrite it.** Tests that record times should use a temporary database path.

## Things to know before editing

**Sessions, penalties and flags.** Each `times` row also has `penalty` (NULL, `'+2'` or `'dnf'`), `flagged` (0/1), `note` and `session`. Each mode has named sessions in table `session_list` (mode, number, name) and a selected one in `sessions.current`: `current_session`, `session_name`, `list_sessions` (number, name, count, last ts), `new_session(mode, name)` (numbered after every existing one, then selected), `select_session`, `rename_session`, `delete_session` (drops its attempts; refuses the last session; reselects the newest). `_add_session_names` names old sessions *Session N*. `list_sessions` commits straight away: Python's sqlite3 opens a write transaction even for an ignored `INSERT OR IGNORE`, and leaving it open blocks the other app and makes `conn.backup` wait forever. `add` stamps the selected session and returns the new id; `delete_last` stays inside the selected session. `Database._add_solve_columns` adds the columns to an older file with `ALTER TABLE`, after copying it once to `cube_times.before-sessions.db` (git-ignored). Keep `seconds` raw and apply the penalty when reading: `effective(seconds, penalty)` gives the time with +2 added, or `DNF` (`math.inf`) for a DNF. `calc_ao` trims 5% each side (at least one), so a DNF is the worst time and two in an ao5 make it `inf`; `fmt(inf)` is `"DNF"` and `fmt(None)` is `"—"`. `get`, `recent`, `recent_means` and `case_summary` apply penalties (the last two leave DNFs out). `solves(mode, scope)` returns raw tuples `(id, case_name, seconds, penalty, flagged, note, ts, session)`, newest first; `solve_table` adds the rolling ao5 / ao12 for the Statistics table, and `stats(mode, scope)` is `solve_stats` over a scope (`"session"` or `"all"`). Change solves only with `set_penalty`, `set_flag` (unflagging drops the note) and `delete_solve`.

**Settings.** Table `settings` (key, JSON value) holds the timer settings shared by both apps: `DEFAULT_SETTINGS` in `cube_timer.py` lists every key, `SETTING_CHOICES` the allowed values, and `check_setting` validates them. Read with `Database.get_settings()` (saved values over the defaults) and write with `set_setting`. `Database.add` takes a `penalty` for attempts that overran WCA inspection.

**Case names are database keys.** Times are stored with `case_name` set to the case's `name` (e.g. `"OLL 21"`, `"T Perm"`). Renaming a case orphans its history.

**Importing `cube_timer` requires `rich`.** The module exits at import time if `rich` is missing, and the GUI imports from it.

**Case pictures are derived, not stored.** `case_state(alg)` applies the inverse of the algorithm to a solved cube (yellow up, green front); the widget draws the resulting top layer. There are no image files and Pillow is not installed. A case is drawn as PLL (side colours and arrows) when its top face is all yellow, otherwise as OLL.

**Simulator conventions.** Axes: x right, y up, z front. `_turn(v, axis)` is a quarter turn clockwise seen from the positive end. `_MOVES` maps each letter to (axis, layers, direction) and supports face turns, wide turns (`r l u d f b`), slices (`M E S`) and rotations (`x y z`) with `'` and `2` suffixes. A new move letter must be added there.

**PLL arrows ignore a final turn of the top layer.** Several listed algorithms finish one U turn from solved, so `_arrows` tries all four alignments and keeps the simplest (fewest pieces moved, then shortest cycles, then fewest corners).

**Timer screens share a base class.** `FullSolveScreen` and `CaseTrainerScreen` extend `TimerScreenBase`, which runs the idle → [inspecting] → [holding → ready] → running → stopped machine (a port of `web/js/timer.js`) and builds the case panel (`_build_case_panel`). Space goes to `timer_press` / `timer_release`, the Start button to `timer_toggle` (never holds). `timer_options(settings, mode)` turns the saved settings into `{inspection, wca, hold}` at the start of each attempt; `self.clock` (default `time.perf_counter`) can be replaced in tests, so inspection doesn't need real waiting. WCA penalties apply only to Full Solve (`wca`); a DNF from inspection is saved at once as 0 s with penalty `dnf`. Subclasses supply `timer_label`, `start_btn`, `mode`, `_next()` and `_save_result(elapsed, penalty)`. `TimerOptions` is the row of inspection / hold switches under each timer; screens call its `refresh()` in `on_show`, since hold to start is shared. One `CaseTrainerScreen` class serves both OLL and PLL practice, parametrised by mode.

**Session widgets (GUI).** `SessionPanel` (Full Solve's right-hand column and the trainers' History tab) shows a `SessionPicker` (option menu of named sessions + New / Rename / Delete; `ask_name`, `confirm` and `tell` can be replaced in tests; Statistics has one too, retargeted with `set_mode`), a `StatsBlock` (plain tk labels) and the session's history. A click selects a solve for its `SolveButtons`; with nothing selected they act on the newest solve. Both timer screens also have a `last_bar` (`SolveButtons`) under the timer. Every change goes through `SolveActions.run(solve, action)`, which takes a `Database.solves()` tuple. Its `ask_note` and `confirm` can be replaced in tests. `StatsScreen`'s Solves tab (mode / scope / flagged-only, and Table / Chart) uses the same pieces; `ProgressChart` (a plain `tk.Canvas`, a port of `chart.js`, redrawn on `<Configure>` after `after(120)`, items tagged `dot` / `ring` / `dnf` / `ao5` / `ao12` / `pb` / `hover`, `show_point(i)` for tests) replaces the table in Chart view; its table cells are plain tk labels, and selecting a row only recolours that row's labels.

**Screens are built lazily.** `CubeTimerApp.screen(name)` builds a screen on first use from `_factories`; only Full Solve exists at startup (about 0.6 s, against 5 s when everything was built up front). Use `app.screen(name)`, not `app._screens[name]`, for a screen that may not exist yet. Store listeners skip hidden screens (`winfo_ismapped()`), which repaint in `on_show`.

**Keep repaints cheap.** Reconfiguring customtkinter widgets is slow. The picker and gallery remember what each tile last showed (`_painted`) and touch only tiles that changed. Picker tiles and Statistics cells are plain `tk` widgets (customtkinter versions made pages take seconds to open), so they need explicit colours and fonts and `_px` scaling.

**Logging.** `setup_logging()` in `cube_timer.py` (called from the GUI's and the web app's `main()` only, so scripted tests do not write the log) sends the `cube_timer.*` loggers to a rotating `cube_timer.log`, at INFO, or DEBUG with `CUBE_TIMER_DEBUG=1`. Uncaught errors, including ones inside Tk callbacks (`report_callback_exception`), are logged. Log user-visible state changes at INFO and per-click noise at DEBUG.

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

**Space bar is bound on the root window**: `<KeyPress-space>` and `<KeyRelease-space>` go to the active screen's `timer_press` / `timer_release`. Windows repeats KeyPress while a key is held, so `CubeTimerApp._space_down` drops the repeats. Screens without those methods ignore Space.

## Verifying GUI changes

The GUI can be driven without user input: build `CubeTimerApp()`, call `app.show_screen(name)` and `app.root.update()` in a loop, then `app._on_close()`. When the test records times or changes the selection, first point `cube_timer_gui.Database` at a temporary copy of the database. Pillow is not available for screenshots; capturing the window region with PowerShell's `System.Drawing` `CopyFromScreen` works.

## Web app

**Server (`cube_web.py`).** It reuses the data layer and the simulator unchanged. Points to know:
- **Threads.** Every endpoint is `async def`, so all run on the event-loop thread. The `Database` is opened in the lifespan handler on that same thread, because sqlite connections can't cross threads. Don't add sync (`def`) endpoints that touch `db`.
- **Bootstrap.** `GET /` inlines the bootstrap JSON into `index.html` at `<!--BOOT-->`. That JSON holds the cases with pictures (`diagram_json`) and weights, the selection, statuses and groups, recent attempts, and the last 12 times per case, so the first paint needs no extra request.
- **Pictures.** Case pictures are computed once in `create_app` (about 0.4 s).
- **Endpoints:** `/api/deal/{mode}/{case}` (setup scramble and its picture), `/api/times`, `/api/times/last/{mode}`, `/api/times/{mode}`, `/api/solves/{mode}` (Statistics rows and chart; `case` narrows to one case), `/api/solves/{id}/penalty`, `/api/solves/{id}/flag`, `DELETE /api/solves/{id}`, `POST /api/session/{mode}` (new named session), `PUT` / `PATCH` / `DELETE /api/session/{mode}/{n}` (select / rename / delete), `/api/stats/{mode}`, `GET` / `PUT /api/settings`, `/api/export/csv` / `backup` / `cstimer` (attachments), `POST /api/import` (`{data, mode}`, at most 20 MB), `/api/summary/{mode}`, `/api/selected/{mode}`, `/api/status/{mode}`, `/api/groups/{mode}/{name}`, `/api/state`, `/api/log`. The docs are at `/api/docs`.
- **Static files** are served with ETags and `no-cache`, so edits show up on reload.
- **Dependency check.** `check_dependencies()` runs at import, before fastapi is imported. It exits with a message naming any missing or too-old package (`MIN_VERSIONS`). Keep `MIN_VERSIONS` in step with `requirements.txt`. The user has an old virtualenv with fastapi 0.70 and pydantic 1.8; pydantic 1.8 crashes on import under Python 3.11.

**Client (`web/js`).**
- `store.js` ports `SelectionStore`, with the same methods in camelCase. It changes memory first, then saves through `api.js`, which queues writes so they keep their order. If a write fails, the client reloads `/api/state`.
- `diagram.js` ports `CaseDiagram._draw` to SVG on a 100-unit viewBox. Keep the two in step when changing how pictures look.
- `util.js` ports `fmt`, `calc_ao` and `generate_scramble`. Full Solve scrambles are made in the browser.
- `timer.js` is the timer machine: `press(at)` / `release(at)` for Space, `toggle(at)` for the Start button, with inspection and hold to start. It reads `options()` (`store.timerOptions(mode)`) at the start of each attempt. Tests move `_inspStart` back instead of waiting 15 s. `options.js` is the switch row under each timer; settings live in `store.settings` and change through `store.setSetting` (saved with `PUT /api/settings`; `store.onSettings` listeners repaint every row).
- Screens: `full.js`, `trainer.js` (OLL and PLL), `gallery.js`, `stats.js`. Shared widgets (`selectionTools`, `myGroups`, `groupHeader`, `casePicker`) are in `widgets.js`.
- `chart.js` (`progressChart`) draws the Statistics Chart view as SVG: one path per series (dots, +2 rings, DNF crosses, ao5, ao12), PB ring, session hairlines in All time, crosshair tooltip on hover and arrow keys. It takes `api.solves` rows (newest first) with `limit=5000` and an optional `case`. Line colours `#3987e5` / `#d95926` were checked with the dataviz validator on both dark surfaces; gridlines and session lines are solid hairlines. `screens.stats.chart.points` is the solve count, for tests.
- `solves.js` holds the session widgets: `sessionPicker` (a `<select>` of named sessions + New / Rename / Delete; also on Statistics, one per mode), `statsBlock`, `sessionPanel` (used by Full Solve and the trainers' History tab), `lastSolveBar` and `solveAction` (+2 / DNF / OK / flag / note / delete, with `prompt` / `confirm`). `store.recent[mode]` holds the current session's solves as objects `{id, case, seconds, penalty, flagged, note, ts}` (`id` is null until the server has saved it), and `store.stats[mode]` is `{session_no, session_name, sessions: [{n, name, count, last}], session, all}`. Every change to times goes through `store.applyTimes`, which calls the `store.onTimes(fn)` listeners. JSON has no infinity, so the server sends DNF times and averages as the string `"DNF"` (`jsonable`); `fmt` accepts it. `util.js` has `eff` and `fmtSolve` (ports of `effective` and `fmt_solve`).

**Rules for speed:**
- Build DOM once; on store changes only flip classes and text. Use one delegated listener per list, not one per tile.
- `app.js` builds the opened screen first and the others in `requestIdleCallback`. Screens are shown and hidden with the `.shown` class.
- The trainer picks the next case and fetches its scramble (`prepareNext`) as soon as the current one is shown. `pickNextCase` reuses that prefetch while the source, pin and odds are unchanged and the case is still in the pool.

**Clicks.** A browser sends click, click, dblclick. Tiles and cards ignore the second click (`e.detail > 1`), and the dblclick handler undoes the first click's toggle, as in the Tk app.

**Space** is handled on `keydown` (`Timer.press`, ignoring `e.repeat`) and `keyup` (`Timer.release`), using `e.timeStamp`, and its default action is prevented so a focused button isn't pressed. A `<select>` or checkbox is blurred after a change so it doesn't keep focus and take the next Space press. Hold to start is on by default, so a scripted check must hold Space (`keyboard.down`, wait 400 ms, `keyboard.up`) to start the clock.

**Testing the web app.** `fastapi.testclient.TestClient(create_app(tmp_db))` covers the API. Inside `with TestClient(...)` the lifespan runs and the database opens. For the page, run `uvicorn.Server` on `create_app(tmp_db)` in a thread and drive it with Playwright using `channel="chrome"`, the installed Chrome. `httpx` and `playwright` are test-only and not in requirements. `window.cubeApp` exposes `store`, `screens`, `show` and `timings`, and each trainer screen has a `state` getter (`source`, `pinned`, `current`, `scramble`).
