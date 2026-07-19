"""Grading unit tests: run `python -m grading.test_normalize` from repo root.

Covers round-trips and adversarial format variants against the real demo
graders. Extend the CASES list whenever a new answer_type is introduced.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .normalize import normalize_and_compare

ROOT = Path(__file__).resolve().parent.parent

CASES = [
    ("2014-01-sum-of-squares", "205", True),
    ("2014-01-sum-of-squares", " 205 ", True),
    ("2014-01-sum-of-squares", "204", False),
    ("2016-03-knight-moves", "19,675,656", True),
    ("2016-03-knight-moves", "19675656", True),
    ("2016-05-hooks-2", "17418240", True),
    ("2025-12-robot-javelin", "0.4939370904", True),
    ("2025-12-robot-javelin", "0.49393709044", True),
    ("2025-12-robot-javelin", "(229 - 60*sqrt(5))/192", True),
    ("2025-12-robot-javelin", "0.494", False),
    ("2025-12-robot-javelin", "0.618034", False),
    ("2026-02-subtiles-2", "9072", True),
    ("2026-02-subtiles-2", "9,072", True),
    ("2026-02-subtiles-2", "9073", False),
    ("2026-03-planetary-parade", "1/44, 5/44", True),
    ("2026-03-planetary-parade", "1/44,5/44", True),
    ("2026-03-planetary-parade", "0.022727272727, 0.113636363636", True),
    ("2026-03-planetary-parade", "5/44, 1/44", False),
    ("2026-03-planetary-parade", "1/44", False),
    ("2016-02-travel-agent", "3.35e48", True),
    ("2016-02-travel-agent", "3.36e48", True),
    ("2016-02-travel-agent", "3.5e48", False),
]


def main() -> int:
    fails = 0
    for pid, sub, expect in CASES:
        grader = json.loads(
            (ROOT / "data" / "graders" / f"{pid}.json").read_text(encoding="utf-8"))
        ok, why = normalize_and_compare(sub, grader["answer"], grader)
        if ok != expect:
            fails += 1
            print(f"FAIL {pid} {sub!r} -> {ok} ({why}), expected {expect}")
    print(f"{len(CASES) - fails}/{len(CASES)} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
