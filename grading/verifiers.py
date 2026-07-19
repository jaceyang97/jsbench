"""Per-puzzle certificate verifiers.

Some puzzles ask for a certificate (e.g. the filled grid), not just a value.
Grading those by value alone would be gameable — a model could claim the known
best sum without exhibiting a valid grid. A grader JSON opts in with
  {"verifier": "<name>", ...}
and grade.py dispatches here instead of the normalize chain.

Each verifier: fn(submitted: str, grader: dict) -> (correct: bool, reason: str)
"""
from __future__ import annotations

import re


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


REGISTRY = {
    "sum_of_squares": verify_sum_of_squares,
    "tangled": verify_tangled,
    "knight_moves_6": verify_knight_moves_6,
}


def run_verifier(name: str, submitted: str, grader: dict) -> tuple[bool, str]:
    if name not in REGISTRY:
        return False, f"unknown-verifier({name})"
    return REGISTRY[name](submitted, grader)
