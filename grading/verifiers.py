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


REGISTRY = {
    "sum_of_squares": verify_sum_of_squares,
}


def run_verifier(name: str, submitted: str, grader: dict) -> tuple[bool, str]:
    if name not in REGISTRY:
        return False, f"unknown-verifier({name})"
    return REGISTRY[name](submitted, grader)
