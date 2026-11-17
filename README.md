# Cube Timer

A Rubik's Cube practice timer for full solves and last-layer drills. It covers all 57 OLL cases and all 21 PLL cases, shows a picture of each case, and keeps every time in a local SQLite database so you can track progress.

There are two front ends that share the same data:

- **GUI** (`cube_timer_gui.py`) — a dark-themed desktop window.
- **CLI** (`cube_timer.py`) — a terminal version.

## Setup

Requires Python 3 (developed on 3.11) with Tk, which ships with the standard Windows installer.

```
pip install -r requirements.txt
```

This installs `rich` (terminal output) and `customtkinter` (GUI).

## Running

```
python cube_timer_gui.py     # desktop app
python cube_timer.py         # terminal app
```

## GUI

| Page | What it does |
| --- | --- |
| Full Solve | Shows a 20-move scramble and times the solve. Displays last, best, ao5 and ao12. |
| OLL Practice | Deals a random case with a real scramble, its picture and (optionally) its algorithm, and times it. Draw from all cases, your selected set, your slowest cases, a learning status or one group; or pin a specific case. A history column lists recent attempts. |
| PLL Practice | Same as OLL Practice, for the 21 PLL cases. |
| Case Gallery | A picture of every OLL and PLL case with its name, group, algorithm and learning status. Click cases to build a practice set. |
| Statistics | Recent full solves with rolling averages, and count / best / average for every OLL and PLL case. |

**Space** starts the timer, stops it, then moves on to the next scramble or case. Each time is saved when the timer stops; **Delete Last** removes the most recent one.

### Practising a set of cases

1. Open **Case Gallery** and click the cases you want; selected cases get a green border. **Select all**, **Clear** and **Add cases…** (by group or by status) change many at once. The selection is saved and is separate for OLL and PLL.
2. Press **Practise selected (n)**. The practice page switches to *From: Selected (n)* and deals random cases from that set, never the same one twice in a row.
3. Apply the scramble to a solved cube held yellow on top, green in front, then solve the case and stop the timer.

**From** also offers:

- **Slowest 10** — the ten cases with the slowest average over their last five times, taken from your selection (or all cases if nothing is selected).
- **Unlearned / Learning / Finished** — every case with that status.
- A group, such as *T-shape* or *Adj + Corners*.

**Odds:** *Balanced* gives every case the same chance. *Realistic* deals them as often as they come up in real solves (e.g. H Perm 1/72, T Perm 1/18; OLL 20 1/216).

**Statuses:** mark each case *Unlearned*, *Learning* or *Finished*, either with the **This case** buttons on the practice page or by clicking the status under a card in the gallery (it cycles). Statuses are saved.

**Show algorithm** hides the algorithm so you have to recall it; the picture stays.

### Scrambles

Scrambles are real ones, like jperm.net's: short solver-made sequences of face turns (about 15 moves) that put the case on the cube without giving the algorithm away. OLL scrambles also leave a random PLL, as a real solve would. The case arrives at a random angle, so you may need to turn the top layer before the algorithm applies; the picture shows the cube exactly as it sits after scrambling.

The scrambles are stored in `case_scrambles.json` (about ten per case, plus a random top-layer turn each time). To make a fresh set:

```
python make_scrambles.py        # 10 per case; pass a number for more, e.g. 20
```

It takes about a minute and a half. If the file is missing, the app falls back to reversing the algorithm.

Double-click a case in the gallery to practise just that one. Every attempt is saved with its case and scramble. The **History** column shows the latest 40 attempts in that mode with their mean, and **Delete Last** removes the newest one.

### Reading the case pictures

Every picture is a top-down view of the last layer, held with yellow on top and green in front. In the gallery it shows the case as it looks at the moment you start the listed algorithm.

- **OLL:** yellow squares are stickers already facing up. A yellow bar beside the grid is a yellow sticker facing that side.
- **PLL:** the bars around the grid show the side colours. Arrows show where pieces need to go: black for corners, purple for edges, double-headed for a two-piece swap.

## CLI

Pick a mode from the menu. In a timing screen, press **Enter** to start, **Enter** again to stop, or type `q` then **Enter** to cancel. After each attempt a prompt offers the next case, stats, picking a case by number, an OLL group filter, and deleting the last time.

## Data

Times, your selected practice sets and case statuses are stored in `cube_times.db`, created next to the scripts on first run. Both front ends read and write the same file. The terminal app does not use the selected sets, statuses or scrambles. Delete it to start over; copy it to back up your history.

Averages (ao5, ao12, …) drop the best and worst time of the most recent *n* and average the rest.

## Files

| File | Contents |
| --- | --- |
| `cube_timer.py` | OLL and PLL case lists, scramble generator, database, averages, and the terminal app. |
| `cube_timer_gui.py` | The desktop app. |
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
