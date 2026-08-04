"""Off-band grading of a run's submitted answer.

The agent writes {workdir}/output/answer.json. There are two shapes:
  * legacy answer_string: {"answer": "<string>"}. The 134 pre-back-fill
    puzzles use this shape.
  * envelope: {"value": <objective value>, "solution": <solution object>}.
    The 9 open-competition back-fill puzzles use this shape and are graded by
    a compound verifier that recomputes the objective from `solution` and
    ignores `value` (the trace check is a separate pass; see methodology.md).

The grader (this module) lives outside the agent's world and compares against
data/graders/{puzzle_id}.json. The grader JSON opts into the envelope by
setting `envelope: true`; grade.py then passes the parsed dict to the
registered verifier instead of a string.

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


def load_submitted(workdir: Path, envelope: bool = False):
    """Return (submitted, status).

    status: ok|missing|malformed
    submitted: for legacy, a str; for envelope, a dict with keys "value" and
    "solution" (both required present, though value may be None).
    """
    path = Path(workdir) / "output" / "answer.json"
    if not path.exists():
        return None, "missing"
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None, "malformed"
    if envelope:
        if not isinstance(obj, dict) or "solution" not in obj:
            return None, "malformed"
        return {"value": obj.get("value"), "solution": obj.get("solution")}, "ok"
    ans = obj.get("answer") if isinstance(obj, dict) else None
    if ans is None:
        return None, "malformed"
    return str(ans), "ok"


def grade_submission(puzzle_id: str, workdir: Path | str) -> dict:
    grader = json.loads((GRADERS_DIR / f"{puzzle_id}.json").read_text(encoding="utf-8"))
    envelope = bool(grader.get("envelope"))
    submitted, status = load_submitted(Path(workdir), envelope=envelope)
    if status != "ok":
        return {"correct": False, "submitted_answer": submitted,
                "grade_status": status, "grade_method": None,
                "grader_needs_review": grader.get("needs_review", False)}
    if grader.get("verifier"):
        # If the grader ships a canonical_geometry dict, its keys REPLACE the
        # matching keys in solution before the verifier sees them. This closes
        # the transcription-trust cheating vector on the 4 geometry-heavy
        # puzzles (hall-of-mirrors, polymath, swing-time, almost-magic): the
        # agent can still write geometry into its envelope, but grade.py
        # ignores it. The verifier code stays untouched.
        submitted_for_verifier = submitted
        canonical = grader.get("canonical_geometry")
        if canonical and isinstance(submitted, dict):
            sol = submitted.get("solution")
            if isinstance(sol, dict):
                new_sol = dict(sol)
                for k, v in canonical.items():
                    new_sol[k] = v
                submitted_for_verifier = {"value": submitted.get("value"),
                                          "solution": new_sol}
        from .verifiers import run_verifier
        try:
            correct, method = run_verifier(grader["verifier"],
                                           submitted_for_verifier, grader)
        except Exception as exc:
            correct, method = False, f"verifier-crash({type(exc).__name__}: {exc!r})"
    else:
        correct, method = normalize_and_compare(submitted, grader["answer"], grader)
    return {"correct": correct, "submitted_answer": submitted,
            "grade_status": "ok", "grade_method": method,
            "grader_needs_review": grader.get("needs_review", False)}


if __name__ == "__main__":
    print(json.dumps(grade_submission(sys.argv[1], sys.argv[2]), indent=2))
