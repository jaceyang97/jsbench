"""Orchestrator: run the puzzle x model x sample matrix with guardrails.

- asyncio semaphore concurrency (config: concurrency)
- budget circuit breaker: cumulative cost_usd vs budget.hard_cap_usd
- 30-min wall-clock timeout per run (enforced inside run_agent)
- idempotent: (puzzle, model tier, sample_idx) already in runs.jsonl with a
  terminal exit_reason is skipped -> safe to re-invoke after interruption
- retries: infra errors only (exit_reason == "error"), <= retries.infra_max

Plan file format (JSON): [{"puzzle_id": ..., "tier": ..., "k": N}, ...]
Or use --phase0 for the built-in demo matrix (5 puzzles x 4 tiers x 1).

Usage:
  .venv/Scripts/python -m orchestrate.runner --phase0 [--dry-run]
  .venv/Scripts/python -m orchestrate.runner --plan plans/phase1.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.run_agent import CONFIG, MODELS, run_agent  # noqa: E402
from grading.grade import grade_submission  # noqa: E402  (HOST-side only)

RUNS_LOG = ROOT / CONFIG["paths"]["runs_log"]
GRADERS_DIR = ROOT / "data" / "graders"


def grade_on_host(rec: dict) -> dict:
    """Grade a finished run on the HOST (agents never touch data/graders).

    The container writes run.json with grading='pending-host', correct=None,
    and the raw submitted_answer read from its own output/answer.json. We grade
    from that workdir, fill the verdict fields, finalize exit_reason
    (submitted -> solved), and rewrite runs/<id>/run.json so it is the single
    source of truth. Idempotent: already-graded records pass through."""
    if rec.get("grading") != "pending-host":
        return rec
    run_id = rec.get("run_id")
    workdir = ROOT / CONFIG["paths"]["runs"] / run_id / "workdir"
    try:
        g = grade_submission(rec["puzzle_id"], workdir)
    except Exception as exc:
        rec["grading"] = f"host-error: {exc!r}"
        return rec
    correct = bool(g["correct"])
    rec["correct"] = correct
    rec["submitted_answer"] = g["submitted_answer"]
    rec["grade_method"] = g["grade_method"]
    rec["grader_needs_review"] = g["grader_needs_review"]
    rec["solved_on_attempt"] = 1 if correct else None
    rec["first_try_correct"] = correct
    for a in rec.get("attempts", []):
        a["correct"] = correct
        a["grade_method"] = g["grade_method"]
    snap = json.loads((GRADERS_DIR / f"{rec['puzzle_id']}.json")
                      .read_text(encoding="utf-8"))
    rec["grader_snapshot"] = {k: snap[k] for k in
                              ("answer", "answer_type", "tolerance", "aliases",
                               "verifier", "grading_mode") if k in snap}
    if correct and rec.get("exit_reason") == "submitted":
        rec["exit_reason"] = "solved"
    rec["grading"] = "host-graded"
    rj = ROOT / CONFIG["paths"]["runs"] / run_id / "run.json"
    if rj.exists():
        rj.write_text(json.dumps(rec, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    return rec

# Phase 0 demo set (travel-agent excluded: approximate score-type answer)
PHASE0_PUZZLES = [
    "2016-05-hooks-2",           # grid puzzle, image essential
    "2026-03-planetary-parade",  # pure math/probability, post-cutoff 2026
    "2016-03-knight-moves",      # optimization, code helpful
    "2025-12-robot-javelin",     # game theory/probability, pre-cutoff recent
    "2014-01-sum-of-squares",    # 2014-era, no leaderboard
]


def load_done() -> dict[tuple, dict]:
    done = {}
    if RUNS_LOG.exists():
        for line in RUNS_LOG.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = (r["puzzle_id"], r["model_requested"], r["sample_idx"])
            done[key] = r
    return done


def build_queue(plan: list[dict], done: dict) -> list[dict]:
    queue = []
    retry_counts = {}
    for item in plan:
        tier = item["tier"]
        model_id = MODELS[tier]["model_id"]
        for s in range(1, item.get("k", 1) + 1):
            key = (item["puzzle_id"], model_id, s)
            prev = done.get(key)
            if prev and prev.get("exit_reason") != "error":
                continue  # terminal (submitted/max_turns/max_budget/timeout/no_answer)
            if prev and prev.get("exit_reason") == "error":
                retry_counts[key] = retry_counts.get(key, 0) + 1
                if retry_counts[key] > CONFIG["retries"]["infra_max"]:
                    continue
            queue.append({"puzzle_id": item["puzzle_id"], "tier": tier, "sample_idx": s})
    return queue


async def run_one_containerized(item: dict) -> dict:
    """Run one attempt in a FRESH disposable container (--rm, never reused).

    The repo is bind-mounted, so the container writes runs/<run_id>/ directly;
    we read run.json afterwards. Container-level guarantees per run: clean
    filesystem, clean pip state, fresh /tmp — no cross-run contamination.
    """
    import uuid
    run_id = (f"{item['puzzle_id']}_{item['tier']}_s{item['sample_idx']}"
              f"_{uuid.uuid4().hex[:8]}")
    # Pre-create THIS run's output dir on the host and bind ONLY it into the
    # container's otherwise-tmpfs-masked /bench/runs. The agent thus cannot see
    # any other run's transcript or grader_snapshot (the mount-leak fix).
    host_run_dir = ROOT / CONFIG["paths"]["runs"] / run_id
    host_run_dir.mkdir(parents=True, exist_ok=True)
    # Bind the writable output at /out (OUTSIDE the read-only, answer-masked
    # /bench). run_agent writes there via JSB_RUN_DIR; the host reads it back.
    run_mount = f"{host_run_dir.as_posix()}:/out"
    # --no-deps: NEVER let concurrent `compose run` invocations manage the
    # proxy dependency — at high concurrency they race and one recreates the
    # proxy mid-batch, instantly killing every other client (observed as
    # same-second error bursts). The orchestrator/watchdog owns the proxy.
    cmd = ["docker", "compose", "-f", str(ROOT / "docker" / "docker-compose.yml"),
           "run", "--rm", "-T", "--no-deps",
           "-v", run_mount, "-e", "JSB_RUN_DIR=/out", "agent",
           "python3", "-m", "harness.run_agent",
           item["puzzle_id"], item["tier"],
           "--sample", str(item["sample_idx"]), "--run-id", run_id]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    # generous outer guard: in-container harness enforces the real timeout
    try:
        await asyncio.wait_for(proc.wait(), CONFIG["wall_clock_timeout_s"] + 300)
    except asyncio.TimeoutError:
        proc.kill()
    run_json = ROOT / CONFIG["paths"]["runs"] / run_id / "run.json"
    if run_json.exists():
        return json.loads(run_json.read_text(encoding="utf-8"))
    return {"run_id": run_id, "puzzle_id": item["puzzle_id"],
            "model_requested": MODELS[item["tier"]]["model_id"],
            "sample_idx": item["sample_idx"], "arm": "agentic",
            "exit_reason": "error", "error": "container produced no run.json"}


async def run_all(queue: list[dict], containerized: bool = True) -> None:
    sem = asyncio.Semaphore(CONFIG["concurrency"])
    spent = sum((r.get("cost_usd") or 0) for r in load_done().values())
    spent_lock = asyncio.Lock()
    stop = asyncio.Event()

    async def one(item):
        nonlocal spent
        if stop.is_set():
            return
        async with sem:
            if stop.is_set():
                return
            mode = "container" if containerized else "host"
            logger.info(f"START {item['puzzle_id']} x {item['tier']} "
                        f"s{item['sample_idx']} [{mode}]")
            try:
                if containerized:
                    rec = await run_one_containerized(item)
                else:
                    rec = await run_agent(item["puzzle_id"], item["tier"],
                                          item["sample_idx"])
            except Exception as exc:
                logger.error(f"harness crash: {item}: {exc!r}")
                rec = {"puzzle_id": item["puzzle_id"],
                       "model_requested": MODELS[item["tier"]]["model_id"],
                       "sample_idx": item["sample_idx"],
                       "exit_reason": "error", "error": repr(exc), "arm": "agentic"}
            # HOST-side grading: the container returns an ungraded record; the
            # orchestrator (which alone may read data/graders) finalizes it.
            rec = grade_on_host(rec)
            RUNS_LOG.parent.mkdir(exist_ok=True)
            with RUNS_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            async with spent_lock:
                spent += rec.get("cost_usd") or 0
                logger.info(f"DONE  {item['puzzle_id']} x {item['tier']} "
                            f"s{item['sample_idx']}: {rec.get('exit_reason')} "
                            f"correct={rec.get('correct')} "
                            f"cost=${rec.get('cost_usd') or 0:.3f} "
                            f"(total ${spent:.2f})")
                if spent >= CONFIG["budget"]["hard_cap_usd"]:
                    logger.error(f"BUDGET CIRCUIT BREAKER: ${spent:.2f} >= "
                                 f"${CONFIG['budget']['hard_cap_usd']} — halting queue")
                    stop.set()

    await asyncio.gather(*(one(i) for i in queue))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", type=str, default=None)
    ap.add_argument("--phase0", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--local", action="store_true",
                    help="run on host instead of per-run disposable containers "
                         "(smoke tests only — NOT valid for scored runs)")
    args = ap.parse_args()

    if args.phase0:
        plan = [{"puzzle_id": p, "tier": t, "k": 1}
                for p in PHASE0_PUZZLES for t in MODELS.keys()]
    elif args.plan:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    else:
        ap.error("need --plan or --phase0")

    queue = build_queue(plan, load_done())
    est = sum(MODELS[i["tier"]]["max_budget_usd"] for i in queue)
    logger.info(f"queue: {len(queue)} runs, worst-case cost <= ${est:.0f}")
    if args.dry_run:
        for i in queue:
            print(f"  {i['puzzle_id']} x {i['tier']} s{i['sample_idx']}")
        return
    asyncio.run(run_all(queue, containerized=not args.local))


if __name__ == "__main__":
    main()
