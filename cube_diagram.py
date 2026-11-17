#!/usr/bin/env python3
"""
Cube case diagrams - top-down pictures of OLL and PLL cases.

Each picture is worked out from the case's own algorithm: the inverse of the
algorithm is applied to a solved cube (yellow on top, green in front), and the
resulting last layer is drawn. So the picture always shows the case exactly as
it looks at the moment the listed algorithm is started.

Run this file directly to check every algorithm in cube_timer.py.
"""

import tkinter as tk
from functools import lru_cache

YELLOW = "#f6d90b"
UP = (0, 1, 0)

# Axes: x points right, y points up, z points to the front.
FACE_COLORS = {
    (0, 1, 0):  YELLOW,      # U
    (0, -1, 0): "#f2f2f2",   # D  white
    (0, 0, 1):  "#1faa4b",   # F  green
    (0, 0, -1): "#2f6fe0",   # B  blue
    (1, 0, 0):  "#f08a1c",   # R  orange
    (-1, 0, 0): "#d6312b",   # L  red
}

C_UNORIENTED = "#4a4a4a"
C_OUTLINE    = "#151515"
C_ARROW      = "#1b1b1b"     # corner arrows
C_ARROW_EDGE = "#7a1fa2"     # edge arrows

# move letter -> (axis, layers turned, +1 if clockwise seen from the + side)
_MOVES = {
    "R": (0, (1,), 1),  "L": (0, (-1,), -1), "M": (0, (0,), -1),
    "r": (0, (0, 1), 1), "l": (0, (-1, 0), -1), "x": (0, (-1, 0, 1), 1),
    "U": (1, (1,), 1),  "D": (1, (-1,), -1), "E": (1, (0,), -1),
    "u": (1, (0, 1), 1), "d": (1, (-1, 0), -1), "y": (1, (-1, 0, 1), 1),
    "F": (2, (1,), 1),  "B": (2, (-1,), -1), "S": (2, (0,), 1),
    "f": (2, (0, 1), 1), "b": (2, (-1, 0), -1), "z": (2, (-1, 0, 1), 1),
}
_SUFFIX = {"": 1, "2": 2, "'": 3, "2'": 2}


# ---------------------------------------------------------------------------
# Cube simulation
# ---------------------------------------------------------------------------
def _turn(v, axis):
    """Quarter turn of a vector, clockwise as seen from the + end of the axis."""
    x, y, z = v
    if axis == 0:
        return (x, z, -y)
    if axis == 1:
        return (-z, y, x)
    return (y, -x, z)


def _solved():
    """Stickers as (position, facing, colour, home position)."""
    stickers = []
    for x in (-1, 0, 1):
        for y in (-1, 0, 1):
            for z in (-1, 0, 1):
                pos = (x, y, z)
                for axis in range(3):
                    if pos[axis]:
                        facing = tuple(pos[axis] if i == axis else 0 for i in range(3))
                        stickers.append((pos, facing, FACE_COLORS[facing], pos))
    return stickers


def _parse(alg):
    """Algorithm text -> list of (axis, layers, clockwise quarter turns)."""
    moves = []
    for tok in alg.split():
        axis, layers, direction = _MOVES[tok[0]]
        n = _SUFFIX[tok[1:]]
        moves.append((axis, layers, n if direction == 1 else 4 - n))
    return moves


def _apply(stickers, moves):
    for axis, layers, turns in moves:
        out = []
        for pos, facing, color, home in stickers:
            if pos[axis] in layers:
                for _ in range(turns):
                    pos = _turn(pos, axis)
                    facing = _turn(facing, axis)
            out.append((pos, facing, color, home))
        stickers = out
    return stickers


@lru_cache(maxsize=None)
def case_state(alg):
    """The cube that the given algorithm solves."""
    inverse = [(axis, layers, 4 - turns) for axis, layers, turns in reversed(_parse(alg))]
    return tuple(_apply(_solved(), inverse))


def is_last_layer_case(alg):
    """True if the algorithm only disturbs the top layer (yellow stays on top)."""
    state = case_state(alg)
    centres = {facing: color for pos, facing, color, _ in state
               if sum(map(abs, pos)) == 1}
    if centres.get(UP) != YELLOW:
        return False
    return all(color == centres[facing]
               for pos, facing, color, _ in state if pos[1] <= 0)


@lru_cache(maxsize=None)
def case_weight(alg):
    """
    How often the case comes up in real solves, relative to other cases of its
    kind: the number of different-looking last layers it covers, counting every
    turn of the top layer before and after. A symmetric case covers fewer (PLL:
    H/Na/Nb 4, E/Z 8, the rest 16; for OLL only the yellow pattern counts:
    OLL 20 1, OLL 1/21/55/56/57 2, the rest 4).
    """
    inverse = [(axis, layers, 4 - turns) for axis, layers, turns in reversed(_parse(alg))]
    pll = all(c == YELLOW for c in case_diagram(alg)[0].values())
    looks = set()
    for a in range(4):
        for b in range(4):
            state = _apply(_solved(), [(1, (1,), a)] + inverse + [(1, (1,), b)])
            top = [(pos, facing, color) for pos, facing, color, _ in state if pos[1] == 1]
            if pll:
                looks.add(frozenset(top))
            else:
                looks.add(frozenset((pos, facing) for pos, facing, c in top if c == YELLOW))
    return len(looks)


def _arrows(state):
    """Where each top-layer piece has to travel: [((x, z), (x, z), is_swap)]."""
    pieces = [(pos, home) for pos, facing, _, home in state
              if facing == UP and pos[1] == 1 and (pos[0] or pos[2])]
    def moved_pieces(k):
        """Pieces out of place when 'home' is turned k quarter turns."""
        moved = []
        for pos, home in pieces:
            dest = home
            for _ in range(k):
                dest = _turn(dest, 1)
            if dest != pos:
                moved.append(((pos[0], pos[2]), (dest[0], dest[2])))
        return moved

    def rank(moved):
        """Fewest pieces moved, then shortest cycles, then fewest corners."""
        step = dict(moved)
        longest = 0
        for start in step:
            n, p = 1, step[start]
            while p != start:
                n, p = n + 1, step[p]
            longest = max(longest, n)
        corners = sum(1 for a, _ in moved if a[0] and a[1])
        return (len(moved), longest, corners)

    # A turn of the whole top layer does not change the case, so of the four
    # ways to read the permutation, show the simplest one.
    best = min((moved_pieces(k) for k in range(4)), key=rank)
    arrows = []
    for a, b in best:
        if (b, a) in best:
            if a < b:
                arrows.append((a, b, True))
        else:
            arrows.append((a, b, False))
    return arrows


def scramble_state(scramble):
    """The cube after applying a scramble to a solved cube."""
    return tuple(_apply(_solved(), _parse(scramble)))


def case_diagram(alg):
    """Diagram data for the case that `alg` solves (see state_diagram)."""
    return state_diagram(case_state(alg))


def state_diagram(state):
    """
    Returns (top, sides, arrows, permutation_only).
    top   : {(x, z): colour} for the 9 stickers facing up
    sides : {(x, z, nx, nz): colour} for the 12 side stickers of the top layer
    """
    top, sides = {}, {}
    for pos, facing, color, _ in state:
        if pos[1] != 1:
            continue
        if facing == UP:
            top[(pos[0], pos[2])] = color
        else:
            sides[(pos[0], pos[2], facing[0], facing[2])] = color
    permutation_only = all(c == YELLOW for c in top.values())
    arrows = _arrows(state) if permutation_only else []
    return top, sides, arrows, permutation_only


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------
class CaseDiagram(tk.Canvas):
    """
    Top-down picture of a last-layer case.

    OLL cases: yellow stickers are shown where they currently are - on top, or
    as a bar on the side they face. PLL cases (top already all yellow): the
    side colours are shown, with arrows for the pieces that swap or cycle.
    """

    def __init__(self, parent, alg=None, size=110, bg="#2b2b2b"):
        super().__init__(parent, width=size, height=size, bg=bg,
                         highlightthickness=0, bd=0)
        self._size = size
        if alg:
            self.set_case(alg)

    def set_case(self, alg):
        """Show the case that `alg` solves, as it looks when the algorithm starts."""
        self._draw(case_diagram(alg))

    def set_scramble(self, scramble):
        """Show the top layer exactly as it looks after applying a scramble."""
        self._draw(state_diagram(scramble_state(scramble)))

    def _draw(self, diagram):
        self.delete("all")
        top, sides, arrows, permutation_only = diagram

        s      = self._size
        pad    = s * 0.03
        strip  = s * 0.085
        origin = pad + strip + s * 0.03
        cell   = (s - 2 * origin) / 3
        inset  = max(1.0, s * 0.012)

        # Top face
        for (x, z), color in top.items():
            x0 = origin + (x + 1) * cell
            y0 = origin + (z + 1) * cell
            self.create_rectangle(
                x0 + inset, y0 + inset, x0 + cell - inset, y0 + cell - inset,
                fill=YELLOW if color == YELLOW else C_UNORIENTED,
                outline=C_OUTLINE,
            )

        # Side stickers of the top layer
        for (x, z, nx, nz), color in sides.items():
            if not permutation_only and color != YELLOW:
                continue
            if nz:
                x0 = origin + (x + 1) * cell + inset
                x1 = x0 + cell - 2 * inset
                y0 = pad if nz < 0 else s - pad - strip
                y1 = y0 + strip
            else:
                y0 = origin + (z + 1) * cell + inset
                y1 = y0 + cell - 2 * inset
                x0 = pad if nx < 0 else s - pad - strip
                x1 = x0 + strip
            self.create_rectangle(x0, y0, x1, y1, fill=color, outline=C_OUTLINE)

        # Arrows (PLL only)
        for (ax, az), (bx, bz), is_swap in arrows:
            x0, y0 = origin + (ax + 1.5) * cell, origin + (az + 1.5) * cell
            x1, y1 = origin + (bx + 1.5) * cell, origin + (bz + 1.5) * cell
            length = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
            trim = 0.26 * cell / length
            dx, dy = (x1 - x0) * trim, (y1 - y0) * trim
            self.create_line(
                x0 + dx, y0 + dy, x1 - dx, y1 - dy,
                # corners and edges get different colours so cycles stay readable
                fill=C_ARROW if ax and az else C_ARROW_EDGE,
                width=max(2, round(s * 0.022)),
                arrow=tk.BOTH if is_swap else tk.LAST,
                arrowshape=(s * 0.07, s * 0.085, s * 0.03),
                capstyle=tk.ROUND,
            )


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from cube_timer import OLL_CASES, PLL_CASES

    bad = []
    for kind, cases in (("OLL", OLL_CASES), ("PLL", PLL_CASES)):
        for case in cases:
            ok = is_last_layer_case(case["alg"])
            if ok and kind == "PLL":
                ok = case_diagram(case["alg"])[3]
            if not ok:
                bad.append(f"{case['name']}: {case['alg']}")
    if bad:
        print("Algorithms that are not valid last-layer cases:")
        print("\n".join("  " + b for b in bad))
    else:
        print("All OLL and PLL algorithms check out.")
