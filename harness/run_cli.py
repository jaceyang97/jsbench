"""Fallback runner: headless CLI (`claude -p`) instead of the Agent SDK.

Use only for cross-checking SDK results or if the SDK breaks.
Limitations vs run_agent.py (why this is the FALLBACK):
  - claude-code 2.1.90 has no --max-turns: only budget + wall-clock caps apply.
  - Images cannot be attached to the prompt; the agent must Read them from
    disk itself (historically unreliable) -> every image needs the Phase-0
    smoke test before trusting CLI-mode results on image puzzles.

Usage: .venv/Scripts/python -m harness.run_cli 2026-02-subtiles-2 haiku
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from grading.grade import grade_submission  # noqa: E402
from harness.prompts import SYSTEM_APPEND, SYSTEM_APPEND_SHA256, render_task  # noqa: E402
from harness.run_agent import CONFIG, MODELS, RUNS_DIR, build_workdir  # noqa: E402

ALLOWED = "Bash,Read,Write,Edit,Glob,Grep"
DISALLOWED = "WebSearch,WebFetch"


def run_cli(puzzle_id: str, tier: str, sample_idx: int = 1) -> dict:
    mcfg = MODELS[tier]
    run_id = f"{puzzle_id}_{tier}_s{sample_idx}_cli_{uuid.uuid4().hex[:8]}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True)
    workdir = build_workdir(puzzle_id, run_dir)

    meta = json.loads((workdir / "metadata.json").read_text(encoding="utf-8"))
    problem_md = (workdir / "problem.md").read_text(encoding="utf-8")
    has_imgs = (workdir / "images").exists()
    task = render_task(problem_md, meta["answer_format"], meta["date"], has_imgs)
    if has_imgs:
        task += ("\nIMPORTANT: view each file under images/ with the Read tool "
                 "before solving; the images are part of the problem.\n")

    env = dict(os.environ,
               CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
               DISABLE_AUTOUPDATER="1",
               CLAUDE_CODE_GIT_BASH_PATH=r"A:\Git\bin\bash.exe")
    cmd = ["claude", "-p", task,
           "--model", mcfg["model_id"],
           "--output-format", "json",
           "--max-budget-usd", str(mcfg["max_budget_usd"]),
           "--allowedTools", ALLOWED,
           "--disallowedTools", DISALLOWED,
           "--permission-mode", "bypassPermissions",
           "--append-system-prompt", SYSTEM_APPEND,
           "--no-session-persistence"]
    if os.environ.get("ANTHROPIC_API_KEY"):
        cmd.append("--bare")

    start_ts = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=workdir, env=env, capture_output=True,
                              text=True, encoding="utf-8",
                              timeout=CONFIG["wall_clock_timeout_s"], shell=True)
        (run_dir / "result.json").write_text(proc.stdout, encoding="utf-8")
        result = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except subprocess.TimeoutExpired:
        result = {"subtype": "timeout"}
    wall = round(time.monotonic() - t0, 1)

    grade = grade_submission(puzzle_id, workdir)
    record = {
        "run_id": run_id, "puzzle_id": puzzle_id, "arm": "agentic",
        "model_requested": mcfg["model_id"],
        "model_actual": sorted((result.get("modelUsage") or result.get("model_usage") or {}).keys()),
        "harness": f"claude-code@{CONFIG['harness']['claude_code_version']}",
        "runner": "cli", "bare_mode": "--bare" in cmd,
        "system_prompt_sha256": SYSTEM_APPEND_SHA256,
        "sample_idx": sample_idx, "start_ts": start_ts, "wall_time_s": wall,
        "num_turns": result.get("num_turns"),
        "cost_usd": result.get("total_cost_usd"),
        "exit_reason": "submitted" if grade["grade_status"] == "ok"
                       else result.get("subtype", "error"),
        "image_delivered": None,   # CLI mode: unknown; requires smoke test
        "submitted_answer": grade["submitted_answer"], "correct": grade["correct"],
    }
    (run_dir / "run.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("puzzle_id")
    ap.add_argument("tier")
    ap.add_argument("--sample", type=int, default=1)
    a = ap.parse_args()
    print(json.dumps(run_cli(a.puzzle_id, a.tier, a.sample), indent=2))
