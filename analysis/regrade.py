"""Re-grade all recorded runs after a grader/normalizer fix.

Re-runs grade_submission over every run directory that has a workdir, updates
each run.json, and rewrites runs/runs.jsonl in place (backup kept). Reports
every run whose verdict changed.

Usage: .venv/Scripts/python -m analysis.regrade
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from grading.grade import grade_submission  # noqa: E402

RUNS = ROOT / "runs"
LOG = RUNS / "runs.jsonl"


def main() -> None:
    changed = []
    updated_by_id: dict[str, dict] = {}
    for d in sorted(RUNS.iterdir()):
        rj = d / "run.json"
        if not d.is_dir() or not rj.exists() or not (d / "workdir").exists():
            continue
        rec = json.loads(rj.read_text(encoding="utf-8"))
        g = grade_submission(rec["puzzle_id"], d / "workdir")
        if (g["correct"], g["grade_method"]) != (rec.get("correct"), rec.get("grade_method")):
            changed.append((rec["run_id"], rec.get("correct"), g["correct"], g["grade_method"]))
        rec.update(correct=g["correct"], grade_method=g["grade_method"],
                   submitted_answer=g["submitted_answer"],
                   grader_needs_review=g["grader_needs_review"])
        rj.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        updated_by_id[rec["run_id"]] = rec

    if LOG.exists():
        shutil.copy2(LOG, LOG.with_suffix(".jsonl.bak"))
        lines = []
        for line in LOG.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            r = updated_by_id.get(r.get("run_id"), r)
            lines.append(json.dumps(r, ensure_ascii=False))
        LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"regraded {len(updated_by_id)} runs; {len(changed)} verdict change(s):")
    for run_id, old, new, method in changed:
        print(f"  {run_id}: {old} -> {new} ({method})")


if __name__ == "__main__":
    main()
