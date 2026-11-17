#!/usr/bin/env python3
"""
Builds case_scrambles.json: solver-made setup scrambles for every OLL and PLL case.

A scramble made by reversing the algorithm gives the answer away and leaves the
rest of the last layer solved, which never happens in a real solve. Instead,
each target position is built the way it arises in a solve (an OLL case comes
with a random PLL still to do, every case at a random angle) and then solved
with Kociemba's two-phase method. The reversed solution is the scramble.

    python make_scrambles.py            # 10 scrambles per case
    python make_scrambles.py 20         # 20 per case

The first run builds lookup tables (about a minute) and caches them in the
system temp folder. Needs only the standard library plus this project.
"""

import itertools
import json
import os
import pickle
import random
import sys
import tempfile
import time
from multiprocessing import Pool
from pathlib import Path

from cube_diagram import _apply, _parse, _solved

HERE = Path(__file__).parent
OUT_FILE = HERE / "case_scrambles.json"
TABLE_FILE = Path(tempfile.gettempdir()) / "cube_timer_twophase_v1.pickle"

# ---------------------------------------------------------------------------
# Cubie model (Kociemba's conventions)
# ---------------------------------------------------------------------------
URF, UFL, ULB, UBR, DFR, DLF, DBL, DRB = range(8)
UR, UF, UL, UB, DR, DF, DL, DB, FR, FL, BL, BR = range(12)

_BASIC = {
    "U": ((UBR, URF, UFL, ULB, DFR, DLF, DBL, DRB), (0,) * 8,
          (UB, UR, UF, UL, DR, DF, DL, DB, FR, FL, BL, BR), (0,) * 12),
    "R": ((DFR, UFL, ULB, URF, DRB, DLF, DBL, UBR), (2, 0, 0, 1, 1, 0, 0, 2),
          (FR, UF, UL, UB, BR, DF, DL, DB, DR, FL, BL, UR), (0,) * 12),
    "F": ((UFL, DLF, ULB, UBR, URF, DFR, DBL, DRB), (1, 2, 0, 0, 2, 1, 0, 0),
          (UR, FL, UL, UB, DR, FR, DL, DB, UF, DF, BL, BR),
          (0, 1, 0, 0, 0, 1, 0, 0, 1, 1, 0, 0)),
    "D": ((URF, UFL, ULB, UBR, DLF, DBL, DRB, DFR), (0,) * 8,
          (UR, UF, UL, UB, DF, DL, DB, DR, FR, FL, BL, BR), (0,) * 12),
    "L": ((URF, ULB, DBL, UBR, DFR, UFL, DLF, DRB), (0, 1, 2, 0, 0, 2, 1, 0),
          (UR, UF, BL, UB, DR, DF, FL, DB, FR, UL, DL, BR), (0,) * 12),
    "B": ((URF, UFL, UBR, DRB, DFR, DLF, ULB, DBL), (0, 0, 1, 2, 0, 0, 2, 1),
          (UR, UF, UL, BR, DR, DF, DL, BL, FR, FL, UB, DB),
          (0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 1)),
}
FACES = "URFDLB"
SOLVED_CUBIE = (tuple(range(8)), (0,) * 8, tuple(range(12)), (0,) * 12)


def mul(a, b):
    """State a followed by move (or state) b."""
    acp, aco, aep, aeo = a
    bcp, bco, bep, beo = b
    return (tuple(acp[j] for j in bcp),
            tuple((aco[bcp[i]] + bco[i]) % 3 for i in range(8)),
            tuple(aep[j] for j in bep),
            tuple((aeo[bep[i]] + beo[i]) % 2 for i in range(12)))


MOVES, MOVE_NAMES = [], []
for _f in FACES:
    _m = _BASIC[_f]
    _m2 = mul(_m, _m)
    MOVES += [_m, _m2, mul(_m2, _m)]
    MOVE_NAMES += [_f, _f + "2", _f + "'"]

P2 = [0, 1, 2, 4, 7, 9, 10, 11, 13, 16]     # U U2 U' R2 F2 D D2 D' L2 B2
P1_LAST_OK = {3, 5, 6, 8, 12, 14, 15, 17}   # quarter turns of R F L B

# ---------------------------------------------------------------------------
# Sticker state (cube_diagram) -> facelet string -> cubies
# ---------------------------------------------------------------------------
FACE_DIR = {"U": (0, 1, 0), "R": (1, 0, 0), "F": (0, 0, 1),
            "D": (0, -1, 0), "L": (-1, 0, 0), "B": (0, 0, -1)}


def _facelet_pos(face, r, c):
    return {"U": (c - 1, 1, r - 1), "R": (1, 1 - r, 1 - c), "F": (c - 1, 1 - r, 1),
            "D": (c - 1, -1, 1 - r), "L": (-1, 1 - r, c - 1), "B": (1 - c, 1 - r, -1)}[face]


def facelets(state):
    """54-letter facelet string (URFDLB order), colours named after the centres."""
    colour = {(pos, facing): col for pos, facing, col, _ in state}
    face_of = {colour[(d, d)]: f for f, d in FACE_DIR.items()}
    return "".join(face_of[colour[(_facelet_pos(f, r, c), FACE_DIR[f])]]
                   for f in FACES for r in range(3) for c in range(3))


CORNER_FACELETS = [(8, 9, 20), (6, 18, 38), (0, 36, 47), (2, 45, 11),
                   (29, 26, 15), (27, 44, 24), (33, 53, 42), (35, 17, 51)]
EDGE_FACELETS = [(5, 10), (7, 19), (3, 37), (1, 46), (32, 16), (28, 25),
                 (30, 43), (34, 52), (23, 12), (21, 41), (50, 39), (48, 14)]
CORNER_COLOURS = ["URF", "UFL", "ULB", "UBR", "DFR", "DLF", "DBL", "DRB"]
EDGE_COLOURS = ["UR", "UF", "UL", "UB", "DR", "DF", "DL", "DB", "FR", "FL", "BL", "BR"]


def to_cubie(f):
    cp, co, ep, eo = [0] * 8, [0] * 8, [0] * 12, [0] * 12
    for i, fl in enumerate(CORNER_FACELETS):
        ori = next(o for o in range(3) if f[fl[o]] in "UD")
        c1, c2 = f[fl[(ori + 1) % 3]], f[fl[(ori + 2) % 3]]
        cp[i] = next(j for j, cc in enumerate(CORNER_COLOURS) if cc[1] == c1 and cc[2] == c2)
        co[i] = ori
    for i, (a, b) in enumerate(EDGE_FACELETS):
        for j, ec in enumerate(EDGE_COLOURS):
            if (f[a], f[b]) == (ec[0], ec[1]):
                ep[i], eo[i] = j, 0
            elif (f[a], f[b]) == (ec[1], ec[0]):
                ep[i], eo[i] = j, 1
    return tuple(cp), tuple(co), tuple(ep), tuple(eo)


# ---------------------------------------------------------------------------
# Coordinates, move tables and pruning tables
# ---------------------------------------------------------------------------
SLICE_COMBOS = list(itertools.combinations(range(12), 4))
SLICE_INDEX = {c: i for i, c in enumerate(SLICE_COMBOS)}
SLICE_SOLVED = SLICE_INDEX[(8, 9, 10, 11)]
PERM8 = list(itertools.permutations(range(8)))
PERM8_INDEX = {p: i for i, p in enumerate(PERM8)}
PERM4 = list(itertools.permutations(range(8, 12)))
PERM4_INDEX = {p: i for i, p in enumerate(PERM4)}


def twist_of(co):
    t = 0
    for v in co[:7]:
        t = t * 3 + v
    return t


def flip_of(eo):
    t = 0
    for v in eo[:11]:
        t = t * 2 + v
    return t


def slice_of(ep):
    return SLICE_INDEX[tuple(i for i in range(12) if ep[i] >= 8)]


def _digits(n, base, count):
    out = []
    for _ in range(count):
        n, d = divmod(n, base)
        out.append(d)
    out.reverse()
    out.append((-sum(out)) % base)
    return out


def _bfs(n2, mv1, mv2, moves, start, size):
    table = bytearray([255]) * size
    table[start] = 0
    frontier, depth = [start], 0
    while frontier:
        nxt = []
        for idx in frontier:
            a, b = divmod(idx, n2)
            ra, rb = mv1[a], mv2[b]
            for m in moves:
                j = ra[m] * n2 + rb[m]
                if table[j] == 255:
                    table[j] = depth + 1
                    nxt.append(j)
        frontier, depth = nxt, depth + 1
    return table


def build_tables():
    twist_mv = []
    for t in range(2187):
        co = _digits(t, 3, 7)
        twist_mv.append([twist_of([(co[m[0][i]] + m[1][i]) % 3 for i in range(8)])
                         for m in MOVES])
    flip_mv = []
    for t in range(2048):
        eo = _digits(t, 2, 11)
        flip_mv.append([flip_of([(eo[m[2][i]] + m[3][i]) % 2 for i in range(12)])
                        for m in MOVES])
    slice_mv = []
    for c in SLICE_COMBOS:
        cs = set(c)
        slice_mv.append([SLICE_INDEX[tuple(i for i in range(12) if m[2][i] in cs)]
                         for m in MOVES])
    # phase 2 tables are indexed by position in P2
    cp_mv = [[PERM8_INDEX[tuple(p[j] for j in MOVES[m][0])] for m in P2] for p in PERM8]
    ud_mv = [[PERM8_INDEX[tuple(p[MOVES[m][2][i]] for i in range(8))] for m in P2]
             for p in PERM8]
    sp_mv = [[PERM4_INDEX[tuple(p[MOVES[m][2][8 + j] - 8] for j in range(4))] for m in P2]
             for p in PERM4]
    all18, all10 = range(18), range(10)
    return {
        "twist_mv": twist_mv, "flip_mv": flip_mv, "slice_mv": slice_mv,
        "cp_mv": cp_mv, "ud_mv": ud_mv, "sp_mv": sp_mv,
        "p_ts": _bfs(495, twist_mv, slice_mv, all18, SLICE_SOLVED, 2187 * 495),
        "p_fs": _bfs(495, flip_mv, slice_mv, all18, SLICE_SOLVED, 2048 * 495),
        "p_cs": _bfs(24, cp_mv, sp_mv, all10, 0, 40320 * 24),
        "p_us": _bfs(24, ud_mv, sp_mv, all10, 0, 40320 * 24),
    }


def load_tables():
    if TABLE_FILE.exists():
        try:
            with open(TABLE_FILE, "rb") as fh:
                return pickle.load(fh)
        except Exception:
            pass
    tables = build_tables()
    with open(TABLE_FILE, "wb") as fh:
        pickle.dump(tables, fh, protocol=pickle.HIGHEST_PROTOCOL)
    return tables


# ---------------------------------------------------------------------------
# Two-phase search
# ---------------------------------------------------------------------------
class _Done(Exception):
    pass


def solve(cube, T, max_len=22, extra_time=1.5):
    """Short face-turn solution of a cubie state (list of move indices)."""
    twist_mv, flip_mv, slice_mv = T["twist_mv"], T["flip_mv"], T["slice_mv"]
    cp_mv, ud_mv, sp_mv = T["cp_mv"], T["ud_mv"], T["sp_mv"]
    p_ts, p_fs, p_cs, p_us = T["p_ts"], T["p_fs"], T["p_cs"], T["p_us"]

    best = [None]
    limit = [max_len]
    deadline = [None]
    path, p2path = [], []

    def p2(c, u, s, depth, last):
        if depth == 0:
            return c == 0 and u == 0 and s == 0
        if max(p_cs[c * 24 + s], p_us[u * 24 + s]) > depth:
            return False
        rc, ru, rs = cp_mv[c], ud_mv[u], sp_mv[s]
        for k, m in enumerate(P2):
            face = m // 3
            if face == last or face == last - 3:
                continue
            p2path.append(m)
            if p2(rc[k], ru[k], rs[k], depth - 1, face):
                return True
            p2path.pop()
        return False

    def start_phase2():
        state = cube
        for m in path:
            state = mul(state, MOVES[m])
        cp, _, ep, _ = state
        c, u, s = PERM8_INDEX[cp], PERM8_INDEX[ep[:8]], PERM4_INDEX[ep[8:]]
        h = max(p_cs[c * 24 + s], p_us[u * 24 + s])
        last = path[-1] // 3 if path else -9
        for d2 in range(h, limit[0] - len(path) + 1):
            del p2path[:]
            if p2(c, u, s, d2, last):
                best[0] = path + p2path
                limit[0] = len(best[0]) - 1
                if deadline[0] is None:
                    deadline[0] = time.time() + extra_time
                return
        if deadline[0] and time.time() > deadline[0]:
            raise _Done

    def p1(t, f, s, depth, last):
        if depth == 0:
            if t == 0 and f == 0 and s == SLICE_SOLVED and (not path or path[-1] in P1_LAST_OK):
                start_phase2()
            return
        if max(p_ts[t * 495 + s], p_fs[f * 495 + s]) > depth:
            return
        rt, rf, rsl = twist_mv[t], flip_mv[f], slice_mv[s]
        for m in range(18):
            face = m // 3
            if face == last or face == last - 3:
                continue
            path.append(m)
            p1(rt[m], rf[m], rsl[m], depth - 1, face)
            path.pop()

    _, co, ep, eo = cube
    t, f, s = twist_of(co), flip_of(eo), slice_of(ep)
    try:
        d1 = 0
        while d1 <= limit[0]:
            p1(t, f, s, d1, -9)
            d1 += 1
    except _Done:
        pass
    return best[0]


# ---------------------------------------------------------------------------
# Generating scrambles
# ---------------------------------------------------------------------------
_AUF = ["", "U", "U2", "U'"]
_T = None


def _init_worker():
    global _T
    _T = load_tables()


def _invert(tokens):
    out = []
    for tok in reversed(tokens):
        if "2" in tok:
            out.append(tok.rstrip("'"))
        elif tok.endswith("'"):
            out.append(tok[:-1])
        else:
            out.append(tok + "'")
    return out


def make_scramble(setup):
    """Solver scramble reaching the same position as the given setup moves."""
    target = facelets(_apply(_solved(), _parse(setup)))
    sol = solve(to_cubie(target), _T)
    scramble = " ".join(_invert([MOVE_NAMES[m] for m in sol]))
    if facelets(_apply(_solved(), _parse(scramble))) != target:
        raise RuntimeError(f"scramble check failed for setup {setup!r}")
    return scramble


def _setups(kind, case, count, pll_algs, rng):
    """Setup move sequences putting the case on the cube the way a solve would."""
    inv_case = " ".join(_invert(case["alg"].split()))
    seen, out = set(), []
    for _ in range(count * 20):
        if len(out) == count:
            break
        a, b = rng.choice(_AUF), rng.choice(_AUF)
        if kind == "PLL":
            setup = f"{a} {inv_case} {b}"
        else:
            # what is left after this OLL: a random PLL (or none) at a random angle
            pll = rng.choice(pll_algs + [""])
            c = rng.choice(_AUF)
            setup = f"{c} {' '.join(_invert(pll.split()))} {a} {inv_case} {b}"
        key = facelets(_apply(_solved(), _parse(setup)))
        if key not in seen:
            seen.add(key)
            out.append(setup)
    return out


def _job(item):
    name, setup = item
    return name, make_scramble(setup)


def main():
    from cube_timer import OLL_CASES, PLL_CASES

    per_case = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    rng = random.Random()
    pll_algs = [c["alg"] for c in PLL_CASES]
    jobs = []
    for kind, cases in (("OLL", OLL_CASES), ("PLL", PLL_CASES)):
        for case in cases:
            for setup in _setups(kind, case, per_case, pll_algs, rng):
                jobs.append((case["name"], setup))

    print(f"Preparing solver tables ({TABLE_FILE}) ...", flush=True)
    start = time.time()
    load_tables()
    print(f"  ready in {time.time() - start:.0f}s. Solving {len(jobs)} positions ...", flush=True)

    result = {}
    start = time.time()
    with Pool(max(1, (os.cpu_count() or 2) - 1), initializer=_init_worker) as pool:
        for i, (name, scramble) in enumerate(pool.imap_unordered(_job, jobs), 1):
            result.setdefault(name, []).append(scramble)
            if i % 50 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)}  ({time.time() - start:.0f}s)", flush=True)

    lengths = [len(s.split()) for v in result.values() for s in v]
    OUT_FILE.write_text(json.dumps(
        {"note": "Made by make_scrambles.py - solver scrambles for each case.",
         "scrambles": dict(sorted(result.items()))}, indent=1))
    print(f"Wrote {OUT_FILE} - {len(lengths)} scrambles, "
          f"{min(lengths)}-{max(lengths)} moves (mean {sum(lengths) / len(lengths):.1f}).")


if __name__ == "__main__":
    main()
