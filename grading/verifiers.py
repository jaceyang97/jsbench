"""Per-puzzle certificate verifiers.

Some puzzles ask for a certificate (e.g. the filled grid), not just a value.
Grading those by value alone would be gameable — a model could claim the known
best sum without exhibiting a valid grid. A grader JSON opts in with
  {"verifier": "<name>", ...}
and grade.py dispatches here instead of the normalize chain.

Two verifier calling conventions live side by side here:

1. Legacy string-answer verifiers (Phase-0/1: sum_of_squares, tangled,
   knight_moves_6, what_a_trit) receive the submitted answer as a str.

2. Envelope verifiers (2026-08 open-puzzle back-fill: 9 puzzles) receive a
   dict `{"value": <agent's claimed objective>, "solution": <solution object>}`
   and always recompute the objective from `solution`. The agent's `value` is
   never trusted for pass/fail. Reference values and optimization sense
   ("max" / "min" / "eq" / "floor") come from the grader JSON; the compare
   helper `_verdict_vs_ref` returns a pass/fail plus a reason string, and
   marks solutions that beat the reference (for the writeup gallery). Puzzle
   geometry that the verifier needs (grid dimensions, laser positions, etc.)
   is transcribed by the agent into `solution` — the deterministic verifier
   trusts it; the LLM trace check (separate pass, see methodology.md) records
   fidelity.

Each verifier: fn(submitted: str | dict, grader: dict) -> (correct: bool, reason: str)
"""
from __future__ import annotations

import math
import re
from typing import Any


def verify_sum_of_squares(submitted: str, grader: dict) -> tuple[bool, str]:
    """2014-01 Sum of Squares.

    Submission format (from the puzzle): "(sum, 25 digits)" — digits fill a
    5x5 grid row-major. Constraints: 5-digit number of row i (top->bottom)
    divisible by 1..5; column j (left->right, reading down) divisible by
    6..10. Score = sum of the 25 digits. Correct iff certificate valid AND
    sum equals the best known score (grader["answer"]).
    """
    m = re.search(r"\(?\s*(\d+)\s*[,;]\s*(\d{25})\s*\)?", str(submitted).replace(" ", " "))
    if not m:
        return False, "sos-format (expected '(sum, 25 digits)')"
    claimed_sum, digits = int(m.group(1)), m.group(2)
    grid = [[int(digits[r * 5 + c]) for c in range(5)] for r in range(5)]

    actual_sum = sum(sum(row) for row in grid)
    if actual_sum != claimed_sum:
        return False, f"sos-sum-mismatch (claimed {claimed_sum}, digits sum {actual_sum})"

    for r in range(5):                      # rows divisible by 1..5
        num = int("".join(str(d) for d in grid[r]))
        if num % (r + 1) != 0:
            return False, f"sos-row{r+1}-not-divisible"
    for c in range(5):                      # cols divisible by 6..10
        num = int("".join(str(grid[r][c]) for r in range(5)))
        if num % (c + 6) != 0:
            return False, f"sos-col{c+6}-not-divisible"

    best = int(grader["answer"])
    if claimed_sum != best:
        return False, f"sos-valid-but-suboptimal ({claimed_sum} < best {best})" \
            if claimed_sum < best else f"sos-sum-exceeds-known-best ({claimed_sum} > {best}: REVIEW!)"
    return True, "sos-verified"


def verify_tangled(submitted: str, grader: dict) -> tuple[bool, str]:
    """2020-09 Tangled (Conway rational tangles).

    The dance master's R/S sequence tangles the ropes; ANY command sequence
    that returns the tangle to 0 untangles them and was accepted by Jane
    Street (leaderboard just ranked by length). Simulate with exact rational
    arithmetic: state p/q starts 0/1, S: t -> t+1, R: t -> -1/t. Convention
    validated against the official 114-command answer (maps dance+official
    to exactly 0; dance alone is nonzero).
    """
    dance = ("SRSRRSSRSRSSRSSRRSSRSSSSSRSSRSSRSRS"
             "SRSSRSSSSSSSSRSSRSSSSSRSSRSSRRSSRSS"
             "SSSRSSRSSRSSSSSSSSSSSSSSSSSRSSRSSRS")
    seq = re.sub(r"[\s,;>\-]", "", str(submitted)).upper()
    if not seq:
        return False, "tangled-empty"
    if not re.fullmatch(r"[RS]+", seq):
        return False, f"tangled-bad-chars ({sorted(set(seq) - set('RS'))})"
    p, q = 0, 1
    for c in dance + seq:
        if c == "S":
            p = p + q
        else:
            p, q = -q, p
    if p == 0 and q != 0:
        return True, f"tangled-verified ({len(seq)} commands)"
    return False, "tangled-still-tangled"


def verify_knight_moves_6(submitted: str, grader: dict) -> tuple[bool, str]:
    """2024-10 Knight Moves 6.

    Entry format (from the puzzle): "A,B,C,<a1..f6 tour>,<a6..f1 tour>",
    e.g. "1,2,253,a1,b3,c5,d3,f4,d5,f6,a6,c5,a4,b2,c4,d2,f1".
    Letter grid transcribed from the puzzle image; transcription validated by
    re-scoring the puzzle's own example entry (both trips = 2024 exactly).
    Correct iff certificate valid AND A+B+C equals the proven minimum 6
    (distinct positive integers floor 1+2+3, achieved per official solution).
    """
    rows = {6: "ABBCCC", 5: "ABBCCC", 4: "AABBCC",
            3: "AABBCC", 2: "AAABBC", 1: "AAABBC"}

    def cell(sq: str) -> str:
        return rows[int(sq[1])]["abcdef".index(sq[0])]

    toks = re.findall(r"[a-f][1-6]|\d+", str(submitted).lower())
    if len(toks) < 5 or not all(t.isdigit() for t in toks[:3]):
        return False, "km6-format (expected A,B,C,tour1,tour2)"
    a, b, c = (int(t) for t in toks[:3])
    if len({a, b, c}) != 3 or min(a, b, c) < 1:
        return False, "km6-values-not-distinct-positive"
    squares = toks[3:]
    if any(t.isdigit() for t in squares):
        return False, "km6-format (stray number inside tours)"
    if "f6" not in squares:
        return False, "km6-missing-f6"
    cut = squares.index("f6") + 1
    trips = [squares[:cut], squares[cut:]]
    if not trips[0] or not trips[1]:
        return False, "km6-two-tours-required"
    if trips[0][0] != "a1" or trips[0][-1] != "f6":
        return False, "km6-tour1-endpoints (must run a1 -> f6)"
    if trips[1][0] != "a6" or trips[1][-1] != "f1":
        return False, "km6-tour2-endpoints (must run a6 -> f1)"
    val = {"A": a, "B": b, "C": c}
    for ti, trip in enumerate(trips, 1):
        if len(set(trip)) != len(trip):
            return False, f"km6-tour{ti}-revisits-square"
        score = a
        for prev, cur in zip(trip, trip[1:]):
            dx = abs("abcdef".index(cur[0]) - "abcdef".index(prev[0]))
            dy = abs(int(cur[1]) - int(prev[1]))
            if sorted((dx, dy)) != [1, 2]:
                return False, f"km6-tour{ti}-illegal-move ({prev}->{cur})"
            if cell(cur) != cell(prev):
                score *= val[cell(cur)]
            else:
                score += val[cell(cur)]
        if score != 2024:
            return False, f"km6-tour{ti}-score {score} != 2024"
    if a + b + c != 6:
        return False, f"km6-valid-but-suboptimal (A+B+C={a+b+c} > 6)"
    return True, "km6-verified"


def verify_what_a_trit(submitted: str, grader: dict) -> tuple[bool, str]:
    """2020-07 What a Trit.

    524293 must be written as a quotient X/Y of two base-4 numerals over
    digits {0, 1, T=-1}. Multiple correct solutions exist and JS accepted
    any of them -> verify by exact conversion: value(X) == 524293 * value(Y).
    """
    s = re.sub(r"\s", "", str(submitted)).upper()
    m = re.fullmatch(r"\(?([01T]+)\)?/\(?([01T]+)\)?", s)
    if not m:
        return False, "trit-format (expected X/Y over digits 0,1,T)"
    def val(t: str) -> int:
        v = 0
        for ch in t:
            v = v * 4 + (1 if ch == "1" else (-1 if ch == "T" else 0))
        return v
    x, y = val(m.group(1)), val(m.group(2))
    if y == 0:
        return False, "trit-zero-denominator"
    if x == 524293 * y:
        return True, "trit-verified"
    return False, f"trit-wrong-value ({x}/{y} != 524293)"


# =============================================================================
# Envelope verifiers (2026-08-04 open-puzzle back-fill).
#
# Common shape: submitted = {"value": <agent's claim>, "solution": <object>}.
# Verifier always recomputes the objective from `solution`. `grader` provides:
#   reference_value : the JS-published best-known or eligibility floor
#   optimization_sense : "max" | "min" | "eq" | "floor"
#     max   → pass iff legal AND recomputed >= reference
#     min   → pass iff legal AND recomputed <= reference
#     eq    → pass iff legal AND recomputed == reference
#     floor → pass iff legal AND recomputed >= reference (a qualifying bar,
#             not a best-of-field; used where JS never published a top score)
#     none  → pass iff legal (used where no reference exists at all)
# A recomputed value that STRICTLY beats the reference (max: >; min: <) is
# passed through in the reason string so audit_transcripts can pick it out
# for the writeup's example gallery.
# =============================================================================


def _get_envelope(submitted: Any) -> tuple[dict | None, str | None]:
    """Return (solution_dict, error). error is None on success."""
    if not isinstance(submitted, dict):
        return None, "envelope-not-a-dict"
    sol = submitted.get("solution")
    if sol is None:
        return None, "envelope-solution-missing"
    return submitted, None


def _verdict_vs_ref(recomputed: float, grader: dict, tag: str) -> tuple[bool, str]:
    """Compare recomputed objective to reference_value per optimization_sense.

    tag is the puzzle short-slug used in the reason string.
    """
    sense = grader.get("optimization_sense", "max")
    ref = grader.get("reference_value")
    if sense == "none" or ref is None:
        return True, f"{tag}-verified (recomputed={recomputed}, no reference)"
    eq_tol = float(grader.get("equality_tolerance", 0))
    if sense == "max":
        if recomputed > ref + eq_tol:
            return True, f"{tag}-verified-BEATS-REF (recomputed={recomputed} > ref={ref})"
        if recomputed >= ref - eq_tol:
            return True, f"{tag}-verified (recomputed={recomputed} >= ref={ref})"
        return False, f"{tag}-legal-but-suboptimal (recomputed={recomputed} < ref={ref})"
    if sense == "min":
        if recomputed < ref - eq_tol:
            return True, f"{tag}-verified-BEATS-REF (recomputed={recomputed} < ref={ref})"
        if recomputed <= ref + eq_tol:
            return True, f"{tag}-verified (recomputed={recomputed} <= ref={ref})"
        return False, f"{tag}-legal-but-suboptimal (recomputed={recomputed} > ref={ref})"
    if sense == "eq":
        if abs(recomputed - ref) <= eq_tol:
            return True, f"{tag}-verified (recomputed={recomputed} == ref={ref})"
        return False, f"{tag}-legal-but-wrong-objective (recomputed={recomputed} != ref={ref})"
    if sense == "floor":
        if recomputed >= ref - eq_tol:
            return True, f"{tag}-verified (recomputed={recomputed} >= floor={ref})"
        return False, f"{tag}-below-qualifying-floor (recomputed={recomputed} < floor={ref})"
    return False, f"{tag}-unknown-sense({sense})"


# ----- 2014-07 Chain Reaction ------------------------------------------------

def verify_chain_reaction(submitted: Any, grader: dict) -> tuple[bool, str]:
    """solution = {"chain": [int, ...]}
    Legality: length >= 1; all in [1,100]; distinct; each adjacent pair
    divides the other. Objective = len(chain). Max; ref 77."""
    env, err = _get_envelope(submitted)
    if err:
        return False, err
    sol = env["solution"]
    if not isinstance(sol, dict) or "chain" not in sol:
        return False, "chain-solution-missing-chain-key"
    chain = sol["chain"]
    if not isinstance(chain, list) or not chain:
        return False, "chain-not-a-nonempty-list"
    if not all(isinstance(x, int) for x in chain):
        return False, "chain-non-integer-entries"
    if any(x < 1 or x > 100 for x in chain):
        return False, "chain-value-out-of-range"
    if len(set(chain)) != len(chain):
        return False, "chain-not-distinct"
    for a, b in zip(chain, chain[1:]):
        if a % b != 0 and b % a != 0:
            return False, f"chain-adjacent-not-divisible ({a},{b})"
    return _verdict_vs_ref(len(chain), grader, "chain-reaction")


# ----- 2014-10 Minesweeping --------------------------------------------------

def verify_minesweeping(submitted: Any, grader: dict) -> tuple[bool, str]:
    """solution = {"grid": [[cell]×4]×4, "target": [r, c]}
    cell: integer 0..8 (revealed number, not a mine) OR "?" (unrevealed, may
    be a mine). Verifier enumerates all subsets of "?" cells that could be
    the true mine set, keeps subsets consistent with every revealed integer's
    3x3 neighbor count, computes fraction of consistent worlds in which
    target is a mine. Pass iff 0 < P(S) < 1 AND P(S) >= reference (38/39).
    Objective for the verdict comparison = P(S)."""
    env, err = _get_envelope(submitted)
    if err:
        return False, err
    sol = env["solution"]
    if not isinstance(sol, dict):
        return False, "mine-solution-not-a-dict"
    grid = sol.get("grid")
    tgt = sol.get("target")
    if not isinstance(grid, list) or len(grid) != 4 or any(len(r) != 4 for r in grid):
        return False, "mine-grid-not-4x4"
    if not isinstance(tgt, (list, tuple)) or len(tgt) != 2:
        return False, "mine-target-not-a-coord"
    try:
        tr, tc = int(tgt[0]), int(tgt[1])
    except Exception:
        return False, "mine-target-not-integer-coord"
    if not (0 <= tr < 4 and 0 <= tc < 4):
        return False, "mine-target-out-of-range"
    unk = []
    revealed = {}
    for r in range(4):
        for c in range(4):
            cell = grid[r][c]
            if cell == "?" or cell is None:
                unk.append((r, c))
            elif isinstance(cell, int) and 0 <= cell <= 8:
                revealed[(r, c)] = cell
            else:
                return False, f"mine-illegal-cell ({r},{c})={cell!r}"
    if (tr, tc) not in unk:
        return False, "mine-target-must-be-unrevealed"
    def neighbors(r, c):
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < 4 and 0 <= nc < 4:
                    yield nr, nc
    consistent = 0
    target_is_mine = 0
    n = len(unk)
    if n > 20:
        return False, f"mine-too-many-unknowns ({n})"
    for mask in range(1 << n):
        mines = {unk[i] for i in range(n) if (mask >> i) & 1}
        ok = True
        for (r, c), num in revealed.items():
            k = sum(1 for nr, nc in neighbors(r, c) if (nr, nc) in mines)
            if k != num:
                ok = False
                break
        if ok:
            consistent += 1
            if (tr, tc) in mines:
                target_is_mine += 1
    if consistent == 0:
        return False, "mine-no-consistent-world (revealed numbers unreachable)"
    if target_is_mine == consistent:
        return False, f"mine-P=1 (target forced; puzzle requires P<1)"
    p = target_is_mine / consistent
    return _verdict_vs_ref(p, grader, "minesweeping")


# ----- 2015-04 Hall of Mirrors -----------------------------------------------

def _reflect(direction: tuple[int, int], orient: str) -> tuple[int, int]:
    dr, dc = direction
    if orient == "/":
        return (-dc, -dr)
    if orient == "\\":
        return (dc, dr)
    raise ValueError(f"bad-orient({orient})")


def verify_hall_of_mirrors(submitted: Any, grader: dict) -> tuple[bool, str]:
    """solution = {
      "geometry": {"rows": R, "cols": C,
                   "lasers": [{"row": r, "col": c, "dr": dr, "dc": dc}, ...],
                   "goals":  [{"row": r, "col": c, "dr": dr, "dc": dc}, ...]},
      "mirrors": [{"row": r, "col": c, "length": N, "orientation": "/" or "\\",
                   "step": [sr, sc]}, ...]
    }
    Laser/goal `row,col` is the edge-adjacent grid cell the laser enters at
    (or the goal receives at); `dr,dc` is the initial in-bound direction.
    Mirror occupies N cells from (r,c) stepping by (sr,sc), all cells must
    be in-grid; each cell may have at most one mirror. Simulate each laser
    forward: reflect on any mirror cell; a laser reaches a goal if it exits
    the grid at a goal cell with matching outbound direction.
    Objective = 5*(goals_hit) - sum(N+2 per mirror). Max; ref 77."""
    env, err = _get_envelope(submitted)
    if err:
        return False, err
    sol = env["solution"]
    geom = sol.get("geometry") if isinstance(sol, dict) else None
    mirrors = sol.get("mirrors") if isinstance(sol, dict) else None
    if not isinstance(geom, dict) or not isinstance(mirrors, list):
        return False, "hom-geometry-or-mirrors-missing"
    try:
        R, C = int(geom["rows"]), int(geom["cols"])
        lasers = [(int(l["row"]), int(l["col"]), int(l["dr"]), int(l["dc"])) for l in geom["lasers"]]
        goals = [(int(g["row"]), int(g["col"]), int(g["dr"]), int(g["dc"])) for g in geom["goals"]]
    except Exception as e:
        return False, f"hom-geometry-parse ({e})"
    mirror_cells: dict[tuple[int, int], str] = {}
    mirror_cost = 0
    for m in mirrors:
        try:
            r, c = int(m["row"]), int(m["col"])
            n = int(m["length"])
            orient = m["orientation"]
            sr, sc = m.get("step", [1, 1 if orient == "\\" else -1])
            sr, sc = int(sr), int(sc)
        except Exception:
            return False, "hom-mirror-parse"
        if orient not in ("/", "\\"):
            return False, f"hom-bad-orient({orient})"
        if abs(sr) != 1 or abs(sc) != 1:
            return False, "hom-mirror-step-must-be-diagonal-unit"
        if n < 1:
            return False, "hom-mirror-length-<1"
        for i in range(n):
            rr, cc = r + sr * i, c + sc * i
            if not (0 <= rr < R and 0 <= cc < C):
                return False, f"hom-mirror-out-of-grid ({rr},{cc})"
            if (rr, cc) in mirror_cells:
                return False, f"hom-cell-double-mirror ({rr},{cc})"
            mirror_cells[(rr, cc)] = orient
        mirror_cost += n + 2
    goal_set = {(r, c, dr, dc) for (r, c, dr, dc) in goals}
    goals_hit = 0
    for (r, c, dr, dc) in lasers:
        rr, cc, ddr, ddc = r, c, dr, dc
        steps = 0
        limit = 4 * R * C
        hit = False
        while 0 <= rr < R and 0 <= cc < C and steps < limit:
            if (rr, cc) in mirror_cells:
                ddr, ddc = _reflect((ddr, ddc), mirror_cells[(rr, cc)])
            rr, cc = rr + ddr, cc + ddc
            steps += 1
            if not (0 <= rr < R and 0 <= cc < C):
                exit_r, exit_c = rr - ddr, cc - ddc
                out_key = (exit_r, exit_c, ddr, ddc)
                if out_key in goal_set:
                    goals_hit += 1
                    hit = True
                break
    score = 5 * goals_hit - mirror_cost
    return _verdict_vs_ref(score, grader, "hall-of-mirrors")


# ----- 2015-06 Polymath ------------------------------------------------------

def _canonical_shapes(cells: list[tuple[int, int]]) -> set[tuple[tuple[int, int], ...]]:
    """8 rotations/reflections; each canonicalised by translating to origin."""
    forms = set()
    for _ in range(2):
        for _ in range(4):
            xs = [x for x, _ in cells]
            ys = [y for _, y in cells]
            mn_x, mn_y = min(xs), min(ys)
            forms.add(tuple(sorted((x - mn_x, y - mn_y) for x, y in cells)))
            cells = [(y, -x) for x, y in cells]
        cells = [(-x, y) for x, y in cells]
    return forms


def verify_polymath(submitted: Any, grader: dict) -> tuple[bool, str]:
    """solution = {
      "board": [[int×10]×10],
      "n": int,
      "T_cells": [[dr, dc], ...],       # arbitrary reference shape of the n-omino
      "placements": [[[r, c], ...], ...]  # each list has n cells (row,col)
    }
    Legality: T_cells is a connected n-omino; each placement is n cells all
    in-grid that are a rotation/reflection of T_cells; placements pairwise
    disjoint; within one placement all covered board values are distinct.
    Objective = sum over placements of prod(board values under placement).
    Max; ref 20160."""
    env, err = _get_envelope(submitted)
    if err:
        return False, err
    sol = env["solution"]
    board = sol.get("board") if isinstance(sol, dict) else None
    n = sol.get("n") if isinstance(sol, dict) else None
    T = sol.get("T_cells") if isinstance(sol, dict) else None
    placements = sol.get("placements") if isinstance(sol, dict) else None
    if not (isinstance(board, list) and len(board) == 10 and all(len(r) == 10 for r in board)):
        return False, "poly-board-not-10x10"
    if not isinstance(n, int) or n < 1:
        return False, "poly-n-invalid"
    if not isinstance(T, list) or len(T) != n:
        return False, "poly-T-cells-count-mismatch"
    try:
        T_tuples = [(int(a), int(b)) for a, b in T]
    except Exception:
        return False, "poly-T-cells-parse"
    if len(set(T_tuples)) != n:
        return False, "poly-T-cells-not-distinct"
    adj = set(T_tuples)
    from collections import deque
    seen = {T_tuples[0]}
    q = deque([T_tuples[0]])
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if (nx, ny) in adj and (nx, ny) not in seen:
                seen.add((nx, ny))
                q.append((nx, ny))
    if seen != adj:
        return False, "poly-T-cells-disconnected"
    canonicals = _canonical_shapes(T_tuples)
    used_cells: set[tuple[int, int]] = set()
    total = 0
    if not isinstance(placements, list) or not placements:
        return False, "poly-no-placements"
    for i, pl in enumerate(placements):
        try:
            pl_cells = [(int(r), int(c)) for r, c in pl]
        except Exception:
            return False, f"poly-placement{i}-parse"
        if len(pl_cells) != n:
            return False, f"poly-placement{i}-wrong-length"
        if any(not (0 <= r < 10 and 0 <= c < 10) for r, c in pl_cells):
            return False, f"poly-placement{i}-out-of-grid"
        if len(set(pl_cells)) != n:
            return False, f"poly-placement{i}-not-distinct"
        if used_cells & set(pl_cells):
            return False, f"poly-placement{i}-overlaps-earlier"
        mn_r = min(r for r, _ in pl_cells)
        mn_c = min(c for _, c in pl_cells)
        norm = tuple(sorted((r - mn_r, c - mn_c) for r, c in pl_cells))
        if norm not in canonicals:
            return False, f"poly-placement{i}-not-a-rotation-of-T"
        values = [board[r][c] for r, c in pl_cells]
        try:
            values = [int(v) for v in values]
        except Exception:
            return False, f"poly-placement{i}-nonint-board-value"
        if len(set(values)) != n:
            return False, f"poly-placement{i}-has-duplicate-values"
        used_cells.update(pl_cells)
        prod = 1
        for v in values:
            prod *= v
        total += prod
    return _verdict_vs_ref(total, grader, "polymath")


# ----- 2016-08 Swing Time ----------------------------------------------------

def _col_a(c: str) -> int:
    return "abcdefghijklmnopqrst".index(c.lower())


def _parse_square(s: str) -> tuple[int, int]:
    m = re.fullmatch(r"([a-tA-T])\s*(\d{1,2})", str(s).strip())
    if not m:
        raise ValueError(f"bad-square({s})")
    return (int(m.group(2)) - 1, _col_a(m.group(1)))


def _collinear_between(a: tuple[int, int], b: tuple[int, int],
                        posts: set[tuple[int, int]]) -> bool:
    (r1, c1), (r2, c2) = a, b
    dr, dc = r2 - r1, c2 - c1
    g = math.gcd(abs(dr), abs(dc)) or 1
    sr, sc = dr // g, dc // g
    r, c = r1 + sr, c1 + sc
    while (r, c) != (r2, c2):
        if (r, c) in posts:
            return True
        r += sr
        c += sc
    return False


def verify_swing_time(submitted: Any, grader: dict) -> tuple[bool, str]:
    """solution = {
      "posts": ["c1","e1",...],           # supplied by grader.canonical_geometry
      "start": "a1", "end": "t20",         # supplied by grader.canonical_geometry
      "swings": [{"post": "a4", "stop": "c3", "wrap": ["c4"] or []}, ...]
    }
    The rope has length D = |cur - swing_post|. During the swing, the rope
    may bend around zero or more intermediate posts before reaching the
    particle at its stopping cell. The agent declares that wrap chain (an
    ordered list of post positions; omit or [] for a straight radius swing).
    The verifier confirms rope conservation:
        D = |post - wrap[0]| + |wrap[0] - wrap[1]| + ... + |wrap[-1] - stop|
    (or D = |post - stop| when the wrap list is empty). Cost per swing =
    1 / D**2 (initial rope length is the physical rope length).

    Enforced legality checks: cur→swing_post visibility (no other post is
    strictly between them on the straight line); each wrap post is a real
    post; the stop is post-less and in-board; the chain of stops feeds each
    subsequent cur; first cur = start, last stop = end.

    NOT enforced (deferred to the trace-check pass): the physical arc-
    obstruction rule (the arc traced by the particle around the swing post
    must not pass through any other post). This is why the grader's
    optimization_sense for this puzzle is "none" — the gate lets a legally
    stated sequence pass and logs the cost for the writeup gallery; the
    trace check audits whether the sequence is physically executable."""
    env, err = _get_envelope(submitted)
    if err:
        return False, err
    sol = env["solution"]
    if not isinstance(sol, dict):
        return False, "swing-solution-not-a-dict"
    try:
        posts = {_parse_square(p) for p in sol["posts"]}
        start = _parse_square(sol["start"])
        end = _parse_square(sol["end"])
        swings = sol["swings"]
    except Exception as e:
        return False, f"swing-parse ({e})"
    if not isinstance(swings, list) or not swings:
        return False, "swing-no-swings"
    if start in posts or end in posts:
        return False, "swing-start-or-end-is-a-post"
    cur = start
    total = 0.0
    ROPE_TOL = 1e-6
    for i, s in enumerate(swings):
        try:
            post = _parse_square(s["post"])
            stop = _parse_square(s["stop"])
        except Exception as e:
            return False, f"swing{i}-parse ({e})"
        if not (0 <= post[0] < 20 and 0 <= post[1] < 20):
            return False, f"swing{i}-post-out-of-board"
        if not (0 <= stop[0] < 20 and 0 <= stop[1] < 20):
            return False, f"swing{i}-stop-out-of-board"
        if post not in posts:
            return False, f"swing{i}-post-not-in-post-list"
        if stop in posts:
            return False, f"swing{i}-stop-on-a-post"
        if _collinear_between(cur, post, posts - {post}):
            return False, f"swing{i}-post-not-visible-from-particle"
        d_cur_post = math.hypot(cur[0] - post[0], cur[1] - post[1])
        if d_cur_post <= 0:
            return False, f"swing{i}-zero-length"
        wrap = s.get("wrap") or []
        if not isinstance(wrap, list):
            return False, f"swing{i}-wrap-not-a-list"
        try:
            wrap_pts = [_parse_square(w) for w in wrap]
        except Exception as e:
            return False, f"swing{i}-wrap-parse ({e})"
        for j, wp in enumerate(wrap_pts):
            if wp not in posts:
                return False, f"swing{i}-wrap{j}-not-a-post"
        chain = [post, *wrap_pts, stop]
        seg_total = sum(math.hypot(a[0] - b[0], a[1] - b[1])
                        for a, b in zip(chain, chain[1:]))
        if abs(seg_total - d_cur_post) > ROPE_TOL:
            return False, (f"swing{i}-rope-not-conserved "
                           f"(|cur-post|={d_cur_post}, sum-of-segments={seg_total})")
        total += d_cur_post ** -2
        cur = stop
    if cur != end:
        return False, f"swing-end-mismatch (finished at {cur}, expected {end})"
    return _verdict_vs_ref(total, grader, "swing-time")


# ----- 2017-08 Middlylinks ---------------------------------------------------

def verify_middlylinks(submitted: Any, grader: dict) -> tuple[bool, str]:
    """solution = {
      "paths": {"5": [[x,y], ...], "13": [...], "17": [...],
                "25": [...], "65": [...], "125": [...]}
    }
    Each path is a sequence of dot coordinates. For key k, every consecutive
    pair must have squared-distance == k. Product of link counts equals
    N(5)*N(13)*N(17)*N(25)*N(65)*N(125). Ref 4293120 (equality). JS admitted
    the puzzle was under-determined so multiple valid path sets exist; this
    verifier checks the numeric answer equality plus the per-link-length
    invariant, and treats the geometric intersection rule as a soft check
    logged in the reason (deterministic verifier is not strict about it)."""
    env, err = _get_envelope(submitted)
    if err:
        return False, err
    sol = env["solution"]
    if not isinstance(sol, dict) or "paths" not in sol:
        return False, "ml-solution-missing-paths"
    paths = sol["paths"]
    keys = ["5", "13", "17", "25", "65", "125"]
    if not isinstance(paths, dict) or any(k not in paths for k in keys):
        return False, "ml-paths-must-cover-5-13-17-25-65-125"
    prod = 1
    for k in keys:
        seq = paths[k]
        if not isinstance(seq, list) or len(seq) < 2:
            return False, f"ml-path{k}-too-short"
        try:
            pts = [(int(x), int(y)) for x, y in seq]
        except Exception:
            return False, f"ml-path{k}-parse"
        if len(set(pts)) != len(pts):
            return False, f"ml-path{k}-revisits-a-dot"
        k_int = int(k)
        for a, b in zip(pts, pts[1:]):
            d2 = (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
            if d2 != k_int:
                return False, f"ml-path{k}-bad-link-length ({a}->{b}, d^2={d2}!={k_int})"
        prod *= (len(pts) - 1)
    return _verdict_vs_ref(prod, grader, "middlylinks")


# ----- 2019-07 Scraggle -----------------------------------------------------

SCRABBLE_SCORES = {**{c: 1 for c in "aeioulnrst"}, **{c: 2 for c in "dg"},
                   **{c: 3 for c in "bcmp"}, **{c: 4 for c in "fhvwy"},
                   "k": 5, "j": 8, "x": 8, "q": 10, "z": 10}


def verify_scraggle(submitted: Any, grader: dict) -> tuple[bool, str]:
    """solution = {
      "grid": [["a"|"e"|"i"|"o"|"u"|<consonant>|null]×6]×6,
      "regions": {"red": [[r,c],...], "blue": [[r,c],...],
                  "green": [[r,c],...], "purple": [[r,c],...]},
      "words": [{"word": "...", "path": [[r,c], ...]}, ...]  # exactly 4
    }
    Verifier structural checks: 6x6 grid; consonants placed by agent are
    distinct; 4 distinct words; each word i starts and ends inside region i
    (red/blue/green/purple in order); each consecutive pair in path is a
    king's move; letters along the path spell the word (case-insensitive);
    last letter of word i == first letter of word i+1. Objective =
    prod(word_score) where word_score = sum of Scrabble letter scores.
    JS never published a top score; ref = None → pass on legality.
    NOTE: dictionary check is deferred to the trace-check pass (out of
    scope for the deterministic verifier — the puzzle demands legal
    Scrabble words but shipping OSPD lookup here is disproportionate)."""
    env, err = _get_envelope(submitted)
    if err:
        return False, err
    sol = env["solution"]
    if not isinstance(sol, dict):
        return False, "scr-solution-not-a-dict"
    grid = sol.get("grid")
    regions = sol.get("regions")
    words = sol.get("words")
    if not (isinstance(grid, list) and len(grid) == 6
            and all(isinstance(r, list) and len(r) == 6 for r in grid)):
        return False, "scr-grid-not-6x6"
    if not isinstance(regions, dict) or set(regions) != {"red", "blue", "green", "purple"}:
        return False, "scr-regions-shape"
    if not isinstance(words, list) or len(words) != 4:
        return False, "scr-need-exactly-4-words"
    letters = {}
    for r in range(6):
        for c in range(6):
            v = grid[r][c]
            if v is None:
                continue
            if not isinstance(v, str) or len(v) != 1 or not v.isalpha():
                return False, f"scr-bad-cell ({r},{c})={v!r}"
            letters[(r, c)] = v.lower()
    consonants = [v for v in letters.values() if v not in "aeiou"]
    if len(set(consonants)) != len(consonants):
        return False, "scr-consonants-not-distinct"
    for name in ("red", "blue", "green", "purple"):
        try:
            _ = {(int(r), int(c)) for r, c in regions[name]}
        except Exception:
            return False, f"scr-region-{name}-parse"
    region_sets = {n: {(int(r), int(c)) for r, c in regions[n]} for n in regions}
    region_order = ["red", "blue", "green", "purple"]
    word_forms = []
    word_paths = []
    scores = []
    for i, w in enumerate(words):
        if not isinstance(w, dict):
            return False, f"scr-word{i}-not-a-dict"
        word = str(w.get("word", "")).lower()
        path = w.get("path")
        if not word:
            return False, f"scr-word{i}-empty"
        if not isinstance(path, list) or len(path) < 2:
            return False, f"scr-word{i}-path-too-short"
        try:
            path_pts = [(int(r), int(c)) for r, c in path]
        except Exception:
            return False, f"scr-word{i}-path-parse"
        if len(path_pts) != len(word):
            return False, f"scr-word{i}-path-length-!=-word-length"
        for a, b in zip(path_pts, path_pts[1:]):
            dr, dc = abs(a[0] - b[0]), abs(a[1] - b[1])
            if max(dr, dc) != 1:
                return False, f"scr-word{i}-not-king-move ({a}->{b})"
        for j, (r, c) in enumerate(path_pts):
            if not (0 <= r < 6 and 0 <= c < 6):
                return False, f"scr-word{i}-off-grid-at-{j}"
            expected = word[j]
            got = letters.get((r, c))
            if got is None or got != expected:
                return False, f"scr-word{i}-letter-mismatch at {j}: grid={got!r}, word={expected!r}"
        rset = region_sets[region_order[i]]
        if path_pts[0] not in rset or path_pts[-1] not in rset:
            return False, f"scr-word{i}-endpoints-not-in-{region_order[i]}"
        word_forms.append(word)
        word_paths.append(path_pts)
        scores.append(sum(SCRABBLE_SCORES.get(ch, 0) for ch in word))
    if len(set(word_forms)) != 4:
        return False, "scr-words-not-distinct"
    for i in range(3):
        if word_forms[i][-1] != word_forms[i + 1][0]:
            return False, f"scr-chain-break-letter-{i}-to-{i+1}"
        if tuple(word_paths[i][-1]) != tuple(word_paths[i + 1][0]):
            return False, (f"scr-chain-break-square-{i}-to-{i+1} "
                           f"(end of word{i} = {word_paths[i][-1]}, "
                           f"start of word{i+1} = {word_paths[i+1][0]})")
    prod = 1
    for s in scores:
        prod *= s
    return _verdict_vs_ref(prod, grader, "scraggle")


# ----- 2022-04 Almost Magic --------------------------------------------------

def verify_almost_magic(submitted: Any, grader: dict) -> tuple[bool, str]:
    """solution = {
      "grid": [[int, ...], ...],           # agent transcribes overall shape
      "subsquares": [[r_top, c_left], ...] # 4 anchors of the 3x3 sub-magic-squares
    }
    Legality: all cells are distinct positive ints; each of the 4 3x3
    sub-squares anchored at (r_top,c_left) has 8 line sums differing by at
    most 1 (i.e., an almost-magic square). Objective = sum of every cell
    that appears in at least one sub-square. Min; ref 470."""
    env, err = _get_envelope(submitted)
    if err:
        return False, err
    sol = env["solution"]
    if not isinstance(sol, dict):
        return False, "am-solution-not-a-dict"
    grid = sol.get("grid")
    subs = sol.get("subsquares")
    if not isinstance(grid, list) or not all(isinstance(r, list) for r in grid):
        return False, "am-grid-not-2d"
    if not isinstance(subs, list) or len(subs) != 4:
        return False, "am-need-4-subsquares"
    rows = len(grid)
    cols = max((len(r) for r in grid), default=0)
    covered = set()
    for i, anchor in enumerate(subs):
        try:
            r0, c0 = int(anchor[0]), int(anchor[1])
        except Exception:
            return False, f"am-sub{i}-anchor-parse"
        if not (0 <= r0 <= rows - 3 and 0 <= c0 <= cols - 3):
            return False, f"am-sub{i}-anchor-out-of-range"
        box = []
        for dr in range(3):
            row = grid[r0 + dr]
            if len(row) < c0 + 3:
                return False, f"am-sub{i}-row-too-short"
            for dc in range(3):
                v = row[c0 + dc]
                if not isinstance(v, int) or v <= 0:
                    return False, f"am-sub{i}-cell-not-positive-int"
                box.append(v)
                covered.add((r0 + dr, c0 + dc))
        sums = []
        for r in range(3):
            sums.append(box[r * 3] + box[r * 3 + 1] + box[r * 3 + 2])
        for c in range(3):
            sums.append(box[c] + box[c + 3] + box[c + 6])
        sums.append(box[0] + box[4] + box[8])
        sums.append(box[2] + box[4] + box[6])
        if max(sums) - min(sums) > 1:
            return False, f"am-sub{i}-not-almost-magic (sums differ by {max(sums)-min(sums)})"
    all_values = [grid[r][c] for r, c in covered]
    if len(set(all_values)) != len(all_values):
        return False, "am-covered-values-not-distinct"
    total = sum(all_values)
    return _verdict_vs_ref(total, grader, "almost-magic")


# ----- 2024-06 Altered States 2 ---------------------------------------------

US_STATE_POP_2020 = {
    "ALABAMA": 5024279, "ALASKA": 733391, "ARIZONA": 7151502,
    "ARKANSAS": 3011524, "CALIFORNIA": 39538223, "COLORADO": 5773714,
    "CONNECTICUT": 3605944, "DELAWARE": 989948, "FLORIDA": 21538187,
    "GEORGIA": 10711908, "HAWAII": 1455271, "IDAHO": 1839106,
    "ILLINOIS": 12812508, "INDIANA": 6785528, "IOWA": 3190369,
    "KANSAS": 2937880, "KENTUCKY": 4505836, "LOUISIANA": 4657757,
    "MAINE": 1362359, "MARYLAND": 6177224, "MASSACHUSETTS": 7029917,
    "MICHIGAN": 10077331, "MINNESOTA": 5706494, "MISSISSIPPI": 2961279,
    "MISSOURI": 6154913, "MONTANA": 1084225, "NEBRASKA": 1961504,
    "NEVADA": 3104614, "NEWHAMPSHIRE": 1377529, "NEWJERSEY": 9288994,
    "NEWMEXICO": 2117522, "NEWYORK": 20201249, "NORTHCAROLINA": 10439388,
    "NORTHDAKOTA": 779094, "OHIO": 11799448, "OKLAHOMA": 3959353,
    "OREGON": 4237256, "PENNSYLVANIA": 13002700, "RHODEISLAND": 1097379,
    "SOUTHCAROLINA": 5118425, "SOUTHDAKOTA": 886667, "TENNESSEE": 6910840,
    "TEXAS": 29145505, "UTAH": 3271616, "VERMONT": 643077,
    "VIRGINIA": 8631393, "WASHINGTON": 7705281, "WESTVIRGINIA": 1793716,
    "WISCONSIN": 5893718, "WYOMING": 576851,
}


def _walk_letters(grid: list[list[str]], path: list[tuple[int, int]]) -> str | None:
    out = []
    prev = None
    for (r, c) in path:
        if not (0 <= r < 5 and 0 <= c < 5):
            return None
        if prev is not None:
            if max(abs(r - prev[0]), abs(c - prev[1])) != 1:
                return None
        out.append(grid[r][c])
        prev = (r, c)
    return "".join(out)


def verify_altered_states_2(submitted: Any, grader: dict) -> tuple[bool, str]:
    """solution = {
      "grid": [["A", ...], ..., ]   # 5x5 uppercase letters, OR "grid_string": <25-char>
      "states": [{"canonical": "CALIFORNIA", "path": [[r,c], ...]}, ...]
    }
    canonical must be a US state name in canonical no-space uppercase form
    (e.g. NEWYORK, NORTHCAROLINA). Path length = len(canonical); each
    consecutive step is a king's move; letters along path differ from
    canonical in at most one position (the "alter one letter" rule). Score
    = sum of 2020 populations of distinct canonical states. Floor sense:
    pass iff score >= reference_value (165379868, JS's leaderboard cutoff).
    """
    env, err = _get_envelope(submitted)
    if err:
        return False, err
    sol = env["solution"]
    if not isinstance(sol, dict):
        return False, "as2-solution-not-a-dict"
    grid = sol.get("grid")
    if grid is None and "grid_string" in sol:
        s = sol["grid_string"]
        if not isinstance(s, str) or len(s) != 25 or not s.isalpha():
            return False, "as2-grid-string-not-25-alpha"
        grid = [[s[r * 5 + c].upper() for c in range(5)] for r in range(5)]
    if not (isinstance(grid, list) and len(grid) == 5
            and all(hasattr(r, "__len__") and len(r) == 5 for r in grid)):
        return False, "as2-grid-not-5x5"
    norm_grid = [[None] * 5 for _ in range(5)]
    for r in range(5):
        for c in range(5):
            try:
                v = grid[r][c]
            except Exception:
                return False, f"as2-grid-cell-not-indexable ({r},{c})"
            if not (isinstance(v, str) and len(v) == 1 and v.isalpha()):
                return False, f"as2-grid-cell-not-letter ({r},{c})"
            norm_grid[r][c] = v.upper()
    grid = norm_grid
    states = sol.get("states")
    if not isinstance(states, list):
        return False, "as2-states-not-a-list"
    seen_canonical = set()
    total_pop = 0
    for i, st in enumerate(states):
        if not isinstance(st, dict):
            return False, f"as2-state{i}-not-a-dict"
        canonical = str(st.get("canonical", "")).upper().replace(" ", "").replace("-", "")
        if canonical not in US_STATE_POP_2020:
            return False, f"as2-state{i}-not-a-us-state ({canonical!r})"
        try:
            path = [(int(r), int(c)) for r, c in st.get("path", [])]
        except Exception:
            return False, f"as2-state{i}-path-parse"
        if len(path) != len(canonical):
            return False, f"as2-state{i}-path-length-!=-name-length"
        walked = _walk_letters(grid, path)
        if walked is None:
            return False, f"as2-state{i}-bad-king-move-or-off-grid"
        diffs = sum(1 for a, b in zip(walked, canonical) if a != b)
        if diffs > 1:
            return False, f"as2-state{i}-more-than-one-alteration ({walked} vs {canonical})"
        if canonical in seen_canonical:
            continue
        seen_canonical.add(canonical)
        total_pop += US_STATE_POP_2020[canonical]
    return _verdict_vs_ref(total_pop, grader, "altered-states-2")


# =============================================================================


REGISTRY = {
    # Legacy string-answer verifiers.
    "sum_of_squares": verify_sum_of_squares,
    "tangled": verify_tangled,
    "knight_moves_6": verify_knight_moves_6,
    "what_a_trit": verify_what_a_trit,
    # Envelope verifiers.
    "chain_reaction": verify_chain_reaction,
    "minesweeping": verify_minesweeping,
    "hall_of_mirrors": verify_hall_of_mirrors,
    "polymath": verify_polymath,
    "swing_time": verify_swing_time,
    "middlylinks": verify_middlylinks,
    "scraggle": verify_scraggle,
    "almost_magic": verify_almost_magic,
    "altered_states_2": verify_altered_states_2,
}


def run_verifier(name: str, submitted, grader: dict) -> tuple[bool, str]:
    if name not in REGISTRY:
        return False, f"unknown-verifier({name})"
    return REGISTRY[name](submitted, grader)
