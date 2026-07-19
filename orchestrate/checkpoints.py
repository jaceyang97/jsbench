"""Build the checkpointed batch plans for the full-bench run.

autoresearch-style staged rollout: escalating fixed-cost batches with a gate
between each. Early batches are cheap canaries that shake out infra problems
before real money is committed; every gate re-audits everything run so far.

Batches (3 models, no fable):
  cp0  canary   3 puzzles x k=1   (~$5)    infra shakeout only, not scored
  cp1  12 puzzles x k=3           (~$59)   incl. reviewed/known puzzles (grading calibration)
  cp2  25 puzzles x k=3           (~$123)
  cp3  45 puzzles x k=3           (~$221)
  cp4  remainder x k=3            (~$280)

Stratification: puzzles are dealt round-robin across batches within each
(era, difficulty) cell, so every batch is representative — cost forecasts and
solve-rate sanity checks from early batches extrapolate to later ones.

Usage:  python -m orchestrate.checkpoints          # writes plans/checkpoints/
        python -m orchestrate.checkpoints --list   # show batch composition
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TIERS = ["haiku", "sonnet", "opus"]          # no fable (memorization + cost)
BATCH_SIZES = [3, 12, 25, 45, None]          # None = remainder
CANARY_K = 1
FULL_K = 3

# calibration puzzles (ground truth battle-tested in Phase 0 / already reviewed)
CALIBRATION = ["2016-05-hooks-2", "2026-03-planetary-parade", "2016-03-knight-moves",
               "2025-12-robot-javelin", "2014-01-sum-of-squares"]


def era_of(date: str) -> str:
    if date >= "2026-02":
        return "post_cutoff"
    if date >= "2023-01":
        return "recent"
    if date >= "2018-01":
        return "mid"
    return "early"


def diff_bucket(pct) -> str:
    if pct is None:
        return "unknown"
    return "easy" if pct >= 67 else ("mid" if pct >= 33 else "hard")


def usable_puzzles() -> list[dict]:
    index = json.loads((ROOT / "data" / "puzzles_index.json").read_text(encoding="utf-8"))
    out = []
    for e in index:
        gpath = ROOT / "data" / "graders" / f"{e['puzzle_id']}.json"
        if not gpath.exists():
            continue
        g = json.loads(gpath.read_text(encoding="utf-8"))
        if g.get("exclude_recommended"):
            continue
        e["_reviewed"] = not g.get("needs_review", True)
        e["_has_answer"] = bool(g.get("answer"))
        e["_era"] = era_of(e["date"])
        e["_diff"] = diff_bucket(e.get("solver_percentile_in_year"))
        out.append(e)
    return out


def build_batches(puzzles: list[dict]) -> list[list[dict]]:
    """Deal puzzles into batches.

    cp0 (canary, k=1): the first 3 calibration puzzles — an infra shakeout.
      These runs ARE valid independent sample_1's and are REUSED by the scored
      set (the runner is idempotent on (puzzle, model, sample_idx)), so nothing
      is wasted.
    cp1..cp4 (scored, k=3): the FULL puzzle set — every usable puzzle, including
      the 3 calibration ones, stratified by (era, diff). For a calibration
      puzzle the runner skips sample_1 (already done in cp0) and runs samples
      2,3; every other puzzle runs samples 1,2,3.
    """
    n_batches = len(BATCH_SIZES)
    batches: list[list[dict]] = [[] for _ in range(n_batches)]
    caps = [s if s is not None else 10**9 for s in BATCH_SIZES[1:]]  # cp1..cp4

    calib = [p for p in puzzles if p["puzzle_id"] in CALIBRATION]
    batches[0] = calib[:BATCH_SIZES[0]]          # cp0 canary

    # cp1..cp4: ALL puzzles, calibration first (so their sample_2/3 run early),
    # then a stratified round-robin over the rest.
    scored_batches = [[] for _ in range(n_batches - 1)]
    for p in calib:                              # every calibration puzzle -> cp1
        scored_batches[0].append(p)

    rest = [p for p in puzzles if p["puzzle_id"] not in CALIBRATION]
    cells: dict[tuple, list[dict]] = defaultdict(list)
    for p in sorted(rest, key=lambda e: e["puzzle_id"]):
        cells[(p["_era"], p["_diff"])].append(p)
    queues = [q for _, q in sorted(cells.items())]
    target = 0
    while any(queues):
        progressed = False
        for q in queues:
            if not q:
                continue
            while target < len(scored_batches) and len(scored_batches[target]) >= caps[target]:
                target += 1
            if target >= len(scored_batches):
                break
            scored_batches[target].append(q.pop(0))
            progressed = True
        if not progressed or target >= len(scored_batches):
            break
    for i, sb in enumerate(scored_batches):
        batches[i + 1] = sb
    return batches


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    puzzles = usable_puzzles()
    batches = build_batches(puzzles)

    plans_dir = ROOT / "plans" / "checkpoints"
    plans_dir.mkdir(parents=True, exist_ok=True)

    total_cost = 0.0
    cost_per = {"haiku": 0.30, "sonnet": 0.79, "opus": 0.55}
    meta = []
    for i, batch in enumerate(batches):
        k = CANARY_K if i == 0 else FULL_K
        plan = [{"puzzle_id": p["puzzle_id"], "tier": t, "k": k}
                for p in batch for t in TIERS]
        (plans_dir / f"cp{i}.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
        est = sum(cost_per[t] * k for p in batch for t in TIERS)
        total_cost += est
        unreviewed = [p["puzzle_id"] for p in batch if not p["_reviewed"]]
        meta.append({"batch": f"cp{i}", "puzzles": len(batch), "k": k,
                     "runs": sum(x["k"] for x in plan),
                     "est_cost_usd": round(est, 2),
                     "unreviewed_graders": len(unreviewed)})
        if args.list:
            eras = defaultdict(int)
            for p in batch:
                eras[p["_era"]] += 1
            print(f"cp{i}: {len(batch)} puzzles, k={k}, ~${est:.0f}, "
                  f"eras={dict(eras)}, unreviewed={len(unreviewed)}")
    (plans_dir / "meta.json").write_text(json.dumps(
        {"tiers": TIERS, "batches": meta, "est_total_usd": round(total_cost, 2)},
        indent=2), encoding="utf-8")
    print(f"\n{len(puzzles)} usable puzzles -> {len(batches)} batches, "
          f"est total ~${total_cost:.0f} -> {plans_dir}")


if __name__ == "__main__":
    main()
