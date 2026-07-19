"""Off-band grading of a run's submitted answer.

The agent writes {workdir}/output/answer.json = {"answer": "<string>"}.
The grader (this module) lives outside the agent's world and compares against
data/graders/{puzzle_id}.json.

Usage as library:
    from grading.grade import grade_submission
    result = grade_submission(puzzle_id, workdir)

CLI spot check:
    python -m grading.grade 2026-02-subtiles-2 runs/<run_id>/workdir
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .normalize import normalize_and_compare

ROOT = Path(__file__).resolve().parent.parent
GRADERS_DIR = ROOT / "data" / "graders"


def load_submitted(workdir: Path) -> tuple[str | None, str]:
    """Return (answer, status). status: ok|missing|malformed."""
    path = Path(workdir) / "output" / "answer.json"
    if not path.exists():
        return None, "missing"
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        ans = obj.get("answer")
        if ans is None:
            return None, "malformed"
        return str(ans), "ok"
    except Exception:
        return None, "malformed"


def grade_submission(puzzle_id: str, workdir: Path | str) -> dict:
    grader = json.loads((GRADERS_DIR / f"{puzzle_id}.json").read_text(encoding="utf-8"))
    submitted, status = load_submitted(Path(workdir))
    if status != "ok":
        return {"correct": False, "submitted_answer": submitted,
                "grade_status": status, "grade_method": None,
                "grader_needs_review": grader.get("needs_review", False)}
    if grader.get("verifier"):
        from .verifiers import run_verifier
        correct, method = run_verifier(grader["verifier"], submitted, grader)
    else:
        correct, method = normalize_and_compare(submitted, grader["answer"], grader)
    return {"correct": correct, "submitted_answer": submitted,
            "grade_status": "ok", "grade_method": method,
            "grader_needs_review": grader.get("needs_review", False)}


if __name__ == "__main__":
    print(json.dumps(grade_submission(sys.argv[1], sys.argv[2]), indent=2))
