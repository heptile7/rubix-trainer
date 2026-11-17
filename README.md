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
| OLL Practice | Deals a random case with a setup scramble, its picture and its algorithm, and times it. Draw from all cases, your selected set, or one group; or pin a specific case. A history column lists recent attempts. |
| PLL Practice | Same as OLL Practice, for the 21 PLL cases. |
| Case Gallery | A picture of every OLL and PLL case with its name, group and algorithm. Click cases to build a practice set. |
| Statistics | Recent full solves with rolling averages, and count / best / average for every OLL and PLL case. |

**Space** starts the timer, stops it, then moves on to the next scramble or case. Each time is saved when the timer stops; **Delete Last** removes the most recent one.

### Practising a set of cases

1. Open **Case Gallery** and click the cases you want; selected cases get a green border. **Select all**, **Clear** and **Add group…** change many at once. The selection is saved and is separate for OLL and PLL.
2. Press **Practise selected (n)**. The practice page switches to *From: Selected (n)* and deals random cases from that set, never the same one twice in a row.
3. Apply the scramble to a solved cube held yellow on top, green in front, then time the algorithm. The cube ends up solved again (give or take a turn of the top layer), ready for the next scramble.

Each scramble adds a random turn of the top layer before and after, so the case arrives at a random angle. On the practice pages the picture is drawn from the scramble, so it shows the cube exactly as it sits after scrambling; you may need to turn the top layer before the listed algorithm applies.

Double-click a case in the gallery to practise just that one. Every attempt is saved with its case and scramble. The **History** column shows the latest 40 attempts in that mode with their mean, and **Delete Last** removes the newest one.

### Reading the case pictures

Every picture is a top-down view of the last layer, held with yellow on top and green in front. In the gallery it shows the case as it looks at the moment you start the listed algorithm.

- **OLL:** yellow squares are stickers already facing up. A yellow bar beside the grid is a yellow sticker facing that side.
- **PLL:** the bars around the grid show the side colours. Arrows show where pieces need to go: black for corners, purple for edges, double-headed for a two-piece swap.

## CLI

Pick a mode from the menu. In a timing screen, press **Enter** to start, **Enter** again to stop, or type `q` then **Enter** to cancel. After each attempt a prompt offers the next case, stats, picking a case by number, an OLL group filter, and deleting the last time.

## Data

Times and your selected practice sets are stored in `cube_times.db`, created next to the scripts on first run. Both front ends read and write the same file. The terminal app does not use the selected sets or setup scrambles. Delete it to start over; copy it to back up your history.

Averages (ao5, ao12, …) drop the best and worst time of the most recent *n* and average the rest.

## Files

| File | Contents |
| --- | --- |
| `cube_timer.py` | OLL and PLL case lists, scramble generator, database, averages, and the terminal app. |
| `cube_timer_gui.py` | The desktop app. |
| `cube_diagram.py` | Cube simulator and the widget that draws case pictures. |
| `requirements.txt` | Python dependencies. |

## Changing an algorithm

The algorithms live in `OLL_CASES` and `PLL_CASES` at the top of `cube_timer.py`. Pictures are generated from them, so editing an algorithm updates its picture automatically. After editing, check that every algorithm is still a valid last-layer case:

```
python cube_diagram.py
```

It prints `All OLL and PLL algorithms check out.` or lists the ones that are wrong.
