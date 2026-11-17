# Cube Timer

A Rubik's Cube practice timer for full solves and last-layer drills. It covers all 57 OLL cases and all 21 PLL cases, shows a picture of each case, and keeps every time in a local SQLite database so you can track progress.

There are three front ends that share the same data:

- **Web app** (`cube_web.py`) — runs in your browser. The fastest one: every page opens instantly.
- **GUI** (`cube_timer_gui.py`) — the original desktop window (customtkinter). Same features as the web app.
- **CLI** (`cube_timer.py`) — a terminal version.

## Setup

Requires Python 3 (developed on 3.11) with Tk, which ships with the standard Windows installer.

```
pip install -r requirements.txt
```

This installs `rich` (terminal output), `customtkinter` (GUI), and `fastapi` with `uvicorn` (web app).

## Running

```
python cube_web.py           # web app: opens in your default browser
python cube_timer_gui.py     # desktop app
python cube_timer.py         # terminal app
```

The web app runs a small server on your own computer (`http://127.0.0.1:8765/`, or the next free port) and opens the page. Stop it with **Ctrl+C** in its terminal. Options:

- `--no-browser`: just start the server and print its address.
- `--port N`: use a particular port.
- `--window`: open the app in its own window instead of a browser tab. This needs `pip install pywebview`.

### Web app or desktop app?

They have the same pages and features and use the same database. Use one at a time: each keeps your selection and groups in memory while it runs.

The web app is much faster. Its pages are built in a few milliseconds, against 0.2–2.6 s in the desktop app, and switching pages takes one frame. Moving to the next case is instant, because the next scramble is fetched while you solve. Case pictures stay sharp at any size, and the layout adapts to any window width, down to a phone.

Two small differences in the web app:

- The timer starts the moment **Space** goes down, using the key press's own timestamp.
- **Save as group…** and the delete and discard confirmations use the browser's own dialogs.

## Web app and GUI

| Page | What it does |
| --- | --- |
| Full Solve | Shows a 20-move scramble and times the solve. Displays last, best, ao5 and ao12. |
| OLL Practice | Deals a random case with a real scramble, its picture and (optionally) its algorithm, and times it. Draw from all cases, your selected set, your slowest cases, a learning status or one group; or pin a specific case. The right-hand column switches between a **case picker** (mini pictures to build your set) and your **history**. |
| PLL Practice | Same as OLL Practice, for the 21 PLL cases. |
| Case Gallery | A large picture of every OLL and PLL case, grouped by shape, with its name, algorithm and learning status. Click cases to build a practice set. |
| Statistics | Recent full solves with rolling averages, and count / best / average for every OLL and PLL case. |

**Space** starts the timer, stops it, then moves on to the next scramble or case. Each time is saved when the timer stops; **Delete Last** removes the most recent one.

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

The **History** tab lists the latest 40 attempts in that mode with their mean.

**Show algorithm** hides the algorithm so you have to recall it; the picture stays.

### Scrambles

Scrambles are real ones, like jperm.net's: short solver-made sequences of face turns (about 15 moves) that put the case on the cube without giving the algorithm away. OLL scrambles also leave a random PLL, as a real solve would. The case arrives at a random angle, so you may need to turn the top layer before the algorithm applies; the picture shows the cube exactly as it sits after scrambling.

The scrambles are stored in `case_scrambles.json` (about ten per case, plus a random top-layer turn each time). To make a fresh set:

```
python make_scrambles.py        # 10 per case; pass a number for more, e.g. 20
```

It takes about a minute and a half. If the file is missing, the app falls back to reversing the algorithm.

Every attempt is saved with its case and scramble; **Delete Last** removes the newest one in that mode.

### Reading the case pictures

Every picture is a top-down view of the last layer, held with yellow on top and green in front. In the gallery it shows the case as it looks at the moment you start the listed algorithm.

- **OLL:** yellow squares are stickers already facing up. A yellow bar beside the grid is a yellow sticker facing that side.
- **PLL:** the bars around the grid show the side colours. Arrows show where pieces need to go: black for corners, purple for edges, double-headed for a two-piece swap.

## CLI

Pick a mode from the menu. In a timing screen, press **Enter** to start, **Enter** again to stop, or type `q` then **Enter** to cancel. After each attempt a prompt offers the next case, stats, picking a case by number, an OLL group filter, and deleting the last time.

## Data

Times, your selected practice sets, case statuses and your own groups are stored in `cube_times.db`, created next to the scripts on first run. Both front ends read and write the same file. The terminal app does not use the selected sets, statuses or scrambles. Delete it to start over; copy it to back up your history.

The apps write a log to `cube_timer.log` (next to the scripts, rotated at 512 KB): startup time, each saved attempt, status and group changes, and any errors (for the web app, also errors in the browser page). Set the environment variable `CUBE_TIMER_DEBUG=1` before starting it to also log every selection change. The log is not committed to git.

Averages (ao5, ao12, …) drop the best and worst time of the most recent *n* and average the rest.

## Files

| File | Contents |
| --- | --- |
| `cube_timer.py` | OLL and PLL case lists, scramble generator, database, averages, and the terminal app. |
| `cube_timer_gui.py` | The desktop app. |
| `cube_web.py` | The web app's server: serves `web/` and a JSON API over the database. |
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
