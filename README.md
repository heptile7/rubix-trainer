# Cube Timer

A Rubik's Cube practice timer for full solves and last-layer drills. It covers all 57 OLL cases and all 21 PLL cases, shows a picture of each case, and keeps every time in a local SQLite database so you can track progress.

You can run it in three ways. All three read and write the same database, `cube_times.db`, so your times follow you whichever you use.

| | Web app (recommended) | Desktop app | Terminal app |
| --- | --- | --- | --- |
| Start it with | `python cube_web.py` | `python cube_timer_gui.py` | `python cube_timer.py` |
| What you get | A page in your browser, or in its own window | A desktop window | Menus and a timer in the terminal |
| Features | Everything | Everything | Full solves with scrambles, OLL / PLL drills, stats. The drills show the algorithm only (you set the case up yourself): no pictures, setup scrambles, selections, statuses or groups. |
| Speed | Pages open in a few milliseconds | Pages take 0.2–2.6 s to open the first time | Instant (text only) |
| Needs | `fastapi`, `uvicorn`, `rich`, Tk | `customtkinter`, `rich`, Tk | `rich` |
| Stop it with | **Ctrl+C** in the terminal (or close the window, with `--window`) | Close the window | `q` at the main menu, or **Ctrl+C** |

## Setup

Requires Python 3.10 or later (developed on 3.11) with Tk, which ships with the standard Windows installer.

```
pip install -r requirements.txt
```

This installs `rich` (terminal output), `customtkinter` (desktop app), and `fastapi`, `uvicorn` and `pydantic` (web app). For the web app in its own window, also run `pip install pywebview`.

Install into the same Python you run the app with. If you use a virtualenv, activate it first, or run `path	oenv\Scripts\python.exe -m pip install --upgrade -r requirements.txt`.

**If the web app won't start:** it checks its packages first. When one is missing or too old, it names it, for example `fastapi: 0.70.1 is too old`. It also prints the exact command to fix it for the Python you used. Very old versions crash under Python 3.11, with errors such as `ValueError: 'not' is not a valid parameter name` from pydantic 1.8. Upgrading fixes that.

## Running

### Web app: `cube_web.py`

```
python cube_web.py                 # serve and open in your default browser
python cube_web.py --window        # serve and open in its own window (needs pywebview)
python cube_web.py --no-browser    # serve only; open the printed address yourself
python cube_web.py --port 9000     # use a particular port (combine with any of the above)
```

**How it runs:**

1. It starts a small web server on your own computer, on `http://127.0.0.1:8765/`, or the next free port if 8765 is taken. The terminal prints the address.
2. It works out every case picture once, which takes about 0.4 s.
3. It opens the address in your default browser. With `--window`, it opens a desktop window instead, using the Edge WebView2 that comes with Windows 10 and 11. With `--no-browser`, it opens nothing.
4. The page talks to the server for everything it saves: times, selections, statuses and groups. The terminal window has to stay open while you use the app.

**Things to know:**

- **Closing the tab doesn't stop the server.** Open the address again to carry on, or press **Ctrl+C** in the terminal to stop it. With `--window`, closing the window stops the server too.
- **Only this computer can open it.** The server listens on `127.0.0.1`, so other devices on your network can't reach it.
- **With `--port N`, the port has to be free.** If something else is using it, the server fails to start. Without `--port`, it picks a free one itself.
- **Start it once.** Starting it a second time runs a second server on the next port, over the same database. See *Use one at a time* below.
- **`--window` needs `pywebview`.** Without it, `--window` stops with a message telling you to install it.

### Desktop app: `cube_timer_gui.py`

```
python cube_timer_gui.py
```

This opens a window with the same pages and features as the web app, drawn with customtkinter. There's no server: the window reads and writes the database directly. Only the Full Solve page is built at startup, which takes about 0.6 s. The other pages are built the first time you open them, which takes up to 2.6 s for the Case Gallery.

**Start it from your desktop.** Run this once:

```
python make_shortcut.py               # puts a "Cube Timer" icon on your desktop
python make_shortcut.py --start-menu  # also adds it to the Start menu, so you can search for it
python make_shortcut.py --remove      # removes the shortcut(s)
```

Double-click the icon to open the desktop app. About 2 seconds later the window is up.

- **No console.** It runs `cube_timer_gui.py` with `pythonw.exe`, so no console window opens.
- **Always up to date.** It runs the latest code every time, so there's nothing to rebuild after the code changes.
- **Your usual data.** It uses your usual `cube_times.db`.
- **Small.** The shortcut is about 2 KB. A bundled `.exe` would take 30–40 MB and start slower.
- **Its own icon.** The window and taskbar button show a cube icon (`cube_timer.ico`, drawn by the script), not Python's.

Run the script with the Python that has the packages from `requirements.txt`; the shortcut uses that Python. The script checks first, and stops with the install command if a package is missing. If the app still can't start later, for example after a package was uninstalled, it shows a dialog saying what's missing. Since there's no console, it can't print the error anywhere else. If Python moves (for example after you install a new version), run `python make_shortcut.py` again.

### Terminal app: `cube_timer.py`

```
python cube_timer.py
```

This shows a menu: **1** Full Solve, **2** OLL Practice, **3** PLL Practice, **4** Statistics, **q** Quit. In a timing screen, press **Enter** to start, **Enter** again to stop, or type `q` then **Enter** to cancel. See [CLI](#cli) below.

### Use one at a time

The web app and the desktop app each load your selection, statuses and groups when they start, and keep them in memory. If both run at once, changes made in one don't appear in the other, and the last one to save wins. Times are safe either way, because every attempt is added as its own row. Close one before you start the other.

### Web app or desktop app?

They have the same pages and features, so choose the web app unless you prefer a classic window. It is much faster:

- Its pages are built in a few milliseconds, and switching pages takes one frame.
- Moving to the next case is instant, because the next scramble is fetched while you solve.
- Case pictures stay sharp at any size, and the layout fits any window width.

Two small differences in the web app:

- The timer starts the moment **Space** goes down, using the key press's own timestamp.
- **Save as group…** and the delete and discard confirmations use the browser's own dialogs.

## Web app and GUI

| Page | What it does |
| --- | --- |
| Full Solve | Shows a 20-move scramble and times the solve. Displays last, best, ao5 and ao12. The right-hand column shows the current **session**: its stats next to your all-time stats, and its solves. |
| OLL Practice | Deals a random case with a real scramble, its picture and (optionally) its algorithm, and times it. Draw from all cases, your selected set, your slowest cases, a learning status or one group; or pin a specific case. The right-hand column switches between a **case picker** (mini pictures to build your set) and your **history** (the current session). |
| PLL Practice | Same as OLL Practice, for the 21 PLL cases. |
| Case Gallery | A large picture of every OLL and PLL case, grouped by shape, with its name, algorithm and learning status. Click cases to build a practice set. |
| Statistics | For Full Solve, OLL or PLL: session and all-time stats, and every solve with its ao5 / ao12, for this session or all time, optionally flagged solves only. Each row has +2 / DNF / flag / delete. A **Chart** view plots your progress. Also count / best / average for every OLL and PLL case. |

**Space** starts the timer and stops it. Stopping saves the time and deals the next scramble or case straight away, so you can go on solving with no extra key press. The time you just did stays on the clock, in yellow, until you start the next one. **Delete Last** removes the most recent solve.

**Previous solve.** The card to the left of the clock shows the solve you just did: its time, the case (OLL / PLL), and the scramble it was timed on, so you can check that you scrambled it right. Under them, **OK / +2 / DNF / ⚑ Flag** correct it or mark it for later. The card stays until your next solve replaces it, and it's hidden while the session has no solves. In a narrow window the clock moves right to make room for it; on a phone-sized screen it goes under the clock.

### Progress chart

In **Statistics**, choose **Chart** (web app) or **Chart** next to *Table* (desktop app). It plots every solve of the selected session, or of **All time**, from first to latest:

- grey dots are single solves; a hollow ring is a +2, and an × along the top is a DNF;
- the blue line is your ao5 and the orange line your ao12 (a DNF average leaves a gap);
- a ring marks your best single (**PB**);
- in *All time*, a thin vertical line with the session's name shows where each session starts, so you can compare cubes.

Move the mouse over the chart (or, in the web app, focus it and use the arrow keys) to read a solve's time, ao5, ao12, note and date. For OLL / PLL, a menu narrows the chart to one case. The Solves table shows the same values without hovering.

### Inspection and hold to start

The switches under the timer change how a solve starts. They are saved and shared by the web app and the desktop app.

- **Hold to start** (on by default): hold Space; the timer turns **red**, then **green** once you've held it long enough (0.3 s, 0.55 s or 1 s). Release to start the clock. Letting go while it's still red does nothing. Space stops the clock the moment you press it.
- **Inspection** on Full Solve is WCA inspection: press and release Space to start a 15-second countdown, look over the cube, then start the solve as usual. Starting between 15 and 17 s adds **+2**; after 17 s the attempt is a **DNF**. *Call 8 / 12 s* (web app) says "eight seconds" and "twelve seconds".
- **Inspection** on OLL / PLL practice is a plain countdown (5, 8, 12 or 15 s) for recognising the case. It never adds a penalty.
- The **Start** button never needs holding; with inspection on, it starts the countdown first.

### Sessions, penalties and flags

Full Solve, OLL and PLL each keep their own list of named **sessions**, for example one per cube (*GAN 12*, *MoYu OH*). The menu at the top of the session column picks the session that new solves go into; its history and stats show below, next to the **all-time** stats of every session together. **New…** creates a session (asking for a name), **Rename…** renames the selected one, and **Delete…** deletes it with its solves (after asking; the last session can't be deleted). Statistics has the same menu. **Delete Last** only removes solves from the selected session. The stats are: number of solves (and DNFs), best, worst, mean, the current ao5 / ao12 / ao50 / ao100, and the best ao5 and ao12.

- **Beside the clock**, the *Previous solve* card has **OK / +2 / DNF / ⚑ Flag** for the attempt you just did, with its time, case and scramble.
- **In the history**, click any solve to fix it: **+2** adds two seconds, **DNF** marks it as not finished, **OK** clears the penalty, **✕** deletes it (for a mis-start or any solve that shouldn't count). Click the same button again to undo a penalty.
- **⚑ Flag** marks a solve for later, with an optional note such as *lucky PLL skip*. Flagged solves show ⚑ in the history; **Note…** changes the note, **Unflag** removes the flag and note. In Statistics, **Flagged only** lists them.

A +2 counts as the time plus two seconds everywhere. A DNF is left out of best, worst and mean, and counts as the slowest time in an average: one DNF in an ao5 is dropped with the slowest time, two make the ao5 a DNF.

### Practising a set of cases

You can build the set right on the practice page, in the **Cases** tab of the right-hand column, or in the **Case Gallery** with bigger pictures. Both show the same selection, which is saved and separate for OLL and PLL.

1. Click case pictures to select or unselect them; selected cases get a green border. Cases are grouped by shape, and each group header shows how many are picked (`Dot (3/8)`). The box at its right selects or clears the whole group (☑ all, ☐ none, half-filled for some). On the practice page, click a group name to fold it away.
2. The buttons above change many at once: **All**, **None** and **Slowest 10** (your 10 slowest cases by recent average). **Mark selected as: Unlearned / Learning / Finished** gives every selected case that status in one go.
3. **Save as group…** names the current selection and keeps it under **My groups** (in the picker and the gallery). Groups also appear in the **From** menu as ★ entries, so you can practise one directly. ✕ deletes a group (the cases themselves are kept).

   **Editing a group:** click it to open it. It becomes the selection and an *Editing ★ name* bar appears. Select or unselect cases freely; the group itself does not change until you press **Save**. The bar shows how many changes are unsaved, **Revert** throws them away, and **Done** stops editing (asking first if anything is unsaved). Opening another group with unsaved changes also asks first.
4. On the practice page, changing the set switches *From* to *Selected (n)*. In the gallery, press **Practise selected (n)**. Random cases are then dealt from the set, never the same one twice in a row.
5. Apply the scramble to a solved cube held yellow on top, green in front, then solve the case and stop the timer.

The picker column and the gallery grow with the window: maximise it for bigger pictures and more per row.

**Pin one case:** double-click its picture, in the picker or the gallery, to practise it over and over. A *Pinned* bar appears above the picker; **✕ Unpin** goes back to random cases. On the practice page, the case being practised has a lighter tile. Hovering over a tile shows the case's name, group and status, and a coloured strip under the tile marks learning (orange) or finished (blue).

**From** also offers:

- **Slowest 10** — the ten cases with the slowest average over their last five times, taken from your selection (or all cases if nothing is selected).
- **Unlearned / Learning / Finished** — every case with that status.
- A group, such as *T-shape* or *Adj + Corners*.

**Odds:** *Balanced* gives every case the same chance. *Realistic* deals them as often as they come up in real solves (e.g. H Perm 1/72, T Perm 1/18; OLL 20 1/216).

**Statuses:** mark each case *Unlearned*, *Learning* or *Finished*, either with the **This case** buttons on the practice page or by clicking the status under a card in the gallery (it cycles). Statuses are saved.

The **History** tab shows the selected session in that mode: the session menu, its stats, and its latest 100 attempts (see *Sessions, penalties and flags*).

**Show algorithm** hides the algorithm so you have to recall it; the picture stays.

### Scrambles

Scrambles are real ones, like jperm.net's: short solver-made sequences of face turns (about 15 moves) that put the case on the cube without giving the algorithm away. OLL scrambles also leave a random PLL, as a real solve would. The case arrives at a random angle, so you may need to turn the top layer before the algorithm applies; the picture shows the cube exactly as it sits after scrambling.

The scrambles are stored in `case_scrambles.json` (about ten per case, plus a random top-layer turn each time). To make a fresh set:

```
python make_scrambles.py        # 10 per case; pass a number for more, e.g. 20
```

It takes about a minute and a half. If the file is missing, the app falls back to reversing the algorithm.

Every attempt is saved with its case and scramble; **Delete Last** removes the newest one in that mode.

### Export and import

In **Statistics**, **Export** saves your solves (the web app downloads the file; the desktop app asks where to save it and picks the format from the file type):

- **CSV** — one row per solve (mode, session, case, time with the penalty applied, raw time, penalty, flag, note, scramble, date), for Excel or Google Sheets.
- **Cube Timer backup** (`.json`) — everything: named sessions, every solve with its penalty, flag and note, your practice selections, case statuses and groups. Use it to back up or move to another computer.
- **csTimer file** (`.txt`) — opens in csTimer with *Import from file*. Each session becomes a csTimer session; OLL / PLL sessions are named *OLL – name* and keep the case in each solve's comment.

**Import…** reads a Cube Timer backup or a csTimer export (CSV can't be imported). It **merges** and never replaces: sessions are matched by name, or created, and solves you already have (same time and date) are skipped, so importing the same file twice adds nothing. csTimer sessions go into Full Solve; a csTimer comment becomes a flagged note. Sessions this app exported from OLL / PLL go back there with their cases. Before importing, the database is copied to `cube_times.before-import-<date-time>.db`.

### Reading the case pictures

Every picture is a top-down view of the last layer, held with yellow on top and green in front. In the gallery it shows the case as it looks at the moment you start the listed algorithm.

- **OLL:** yellow squares are stickers already facing up. A yellow bar beside the grid is a yellow sticker facing that side.
- **PLL:** the bars around the grid show the side colours. Arrows show where pieces need to go: black for corners, purple for edges, double-headed for a two-piece swap.

## CLI

Pick a mode from the menu. Full Solve shows a scramble. OLL and PLL practice show a random case's name and algorithm; set the case up on your cube yourself, then time the algorithm. In a timing screen, press **Enter** to start, **Enter** again to stop, or type `q` then **Enter** to cancel. After each attempt a prompt offers the next case, stats, picking a case by number, an OLL group filter, and deleting the last time.

## Data

Times (with their penalty, flag, note and session), your selected practice sets, case statuses and your own groups are stored in `cube_times.db`, created next to the scripts on first run. All three apps read and write the same file (see *Use one at a time* above). The terminal app records times only; it does not use the selected sets, statuses, groups, case scrambles or sessions, but its averages do apply +2 and DNF. Delete it to start over; copy it to back up your history.

The first time a newer version opens an older `cube_times.db`, it adds the penalty / flag / note / session columns. Before doing so it saves a copy of the old file as `cube_times.before-sessions.db`; your existing times all go into session 1. Sessions that existed before names were added are called *Session N*; rename them as you like.

The apps write a log to `cube_timer.log` (next to the scripts, rotated at 512 KB): startup time, each saved attempt, status and group changes, and any errors (for the web app, also errors in the browser page). Set the environment variable `CUBE_TIMER_DEBUG=1` before starting it to also log every selection change. The log is not committed to git.

Averages (ao5, ao12, …) drop the best and worst 5% of the most recent *n* times (at least one each side: one for ao5 and ao12, three for ao50, five for ao100) and average the rest, as WCA and csTimer do.

## Files

| File | Contents |
| --- | --- |
| `cube_timer.py` | OLL and PLL case lists, scramble generator, database, averages, and the terminal app. |
| `cube_timer_gui.py` | The desktop app. |
| `make_shortcut.py` | Makes the desktop (and Start menu) shortcut for the desktop app, and draws `cube_timer.ico`. |
| `cube_timer.ico` | The app's icon: the shortcut, window and taskbar button use it. |
| `cube_web.py` | The web app's server: serves `web/` and a JSON API over the database. |
| `cube_io.py` | Export to CSV, a JSON backup and csTimer's format, and import of backups and csTimer files. |
| `web/` | The web app's page: `index.html`, `style.css` and plain JavaScript modules in `web/js/` (no build step). |
| `cube_diagram.py` | Cube simulator, the widget that draws case pictures, and case frequencies. |
| `make_scrambles.py` | Two-phase cube solver that generates `case_scrambles.json`. |
| `case_scrambles.json` | Solver-made scrambles for every case. |
| `requirements.txt` | Python dependencies. |

## Changing an algorithm

The algorithms live in `OLL_CASES` and `PLL_CASES` at the top of `cube_timer.py`. Pictures are generated from them, so editing an algorithm updates its picture automatically. After editing, check that every algorithm is still a valid last-layer case:

```
python cube_diagram.py
```

It prints `All OLL and PLL algorithms check out.` or lists the ones that are wrong. If you rename a case, run `python make_scrambles.py` again, since scrambles are stored by case name.
