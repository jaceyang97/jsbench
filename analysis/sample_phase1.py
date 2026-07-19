"""Stratified sampling of the Phase-1 core set (candidate list for Jace).

Strata (per handoff doc §11):
  - era: post-cutoff (>= 2026-02, clean held-out) / recent pre-cutoff
    (2023-2026-01) / mid (2018-2022) / early (2014-2017)
  - difficulty: solver_percentile_in_year buckets (easy >=67, mid 33-67,
    hard <33); pre-leaderboard puzzles fall back to "unknown"
  - has_image mix

Exclusions: graders with exclude_recommended, puzzles with no reviewed answer
(unless --allow-unreviewed), Phase-0 demo puzzles (already burned).

Output: plans/phase1_candidates.json + human-readable table on stdout.
Jace approves/edits, then: orchestrate.runner --plan plans/phase1.json
(k per tier comes from config/models.json phase1_k).

Usage: .venv/Scripts/python -m analysis.sample_phase1 [--n 20] [--seed 7]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEMO = {"2016-05-hooks-2", "2026-03-planetary-parade", "2016-03-knight-moves",
        "2025-12-robot-javelin", "2014-01-sum-of-squares", "2016-02-travel-agent",
        "2026-02-subtiles-2"}

# relative era weights (scaled to --n). post_cutoff is capped by availability
# (only a handful of post-cutoff puzzles exist), so its target is min(weight, pool).
ERA_WEIGHTS = {"post_cutoff": 4, "recent_pre": 8, "mid": 7, "early": 6}


def era_of(date: str) -> str:
    if date >= "2026-02":
        return "post_cutoff"
    if date >= "2023-01":
        return "recent_pre"
    if date >= "2018-01":
        return "mid"
    return "early"


def diff_bucket(pct) -> str:
    if pct is None:
        return "unknown"
    return "easy" if pct >= 67 else ("mid" if pct >= 33 else "hard")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--allow-unreviewed", action="store_true")
    args = ap.parse_args()
    rng = random.Random(args.seed)

    index = json.loads((ROOT / "data" / "puzzles_index.json").read_text(encoding="utf-8"))
    pool = []
    for e in index:
        pid = e["puzzle_id"]
        if pid in DEMO:
            continue
        gpath = ROOT / "data" / "graders" / f"{pid}.json"
        if not gpath.exists():
            continue
        g = json.loads(gpath.read_text(encoding="utf-8"))
        if g.get("exclude_recommended"):
            continue
        if g.get("needs_review") and not args.allow_unreviewed:
            continue
        e["_era"] = era_of(e["date"])
        e["_diff"] = diff_bucket(e.get("solver_percentile_in_year"))
        pool.append(e)

    if not pool:
        print("pool empty — run the full pipeline (+ review) first, or pass "
              "--allow-unreviewed for a provisional list")
        return

    scale = args.n / sum(ERA_WEIGHTS.values())
    picks = []
    for era, w in ERA_WEIGHTS.items():
        want = round(w * scale)
        cands = [e for e in pool if e["_era"] == era]
        # spread across difficulty buckets within the era
        by_diff = {}
        for e in cands:
            by_diff.setdefault(e["_diff"], []).append(e)
        chosen = []
        buckets = sorted(by_diff)
        i = 0
        while len(chosen) < min(want, len(cands)):
            b = buckets[i % len(buckets)]
            if by_diff[b]:
                chosen.append(by_diff[b].pop(rng.randrange(len(by_diff[b]))))
            i += 1
            if all(not v for v in by_diff.values()):
                break
        picks.extend(chosen)

    # top up if a stratum ran short (e.g. post-cutoff pool is tiny)
    if len(picks) < args.n:
        chosen_ids = {e["puzzle_id"] for e in picks}
        rest = [e for e in pool if e["puzzle_id"] not in chosen_ids]
        rng.shuffle(rest)
        picks.extend(rest[:args.n - len(picks)])

    picks.sort(key=lambda e: e["puzzle_id"])
    print(f"{'puzzle_id':38s} {'era':12s} {'diff':8s} {'img':4s} solvers")
    for e in picks:
        print(f"{e['puzzle_id']:38s} {e['_era']:12s} {e['_diff']:8s} "
              f"{'yes' if e['has_image'] else 'no':4s} {e.get('solver_count_raw')}")

    plans = ROOT / "plans"
    plans.mkdir(exist_ok=True)
    models = json.loads((ROOT / "config" / "models.json").read_text(encoding="utf-8"))["models"]
    plan = [{"puzzle_id": e["puzzle_id"], "tier": m["tier"], "k": m["samples_k"]}
            for e in picks for m in models]
    (plans / "phase1_candidates.json").write_text(
        json.dumps(plan, indent=2), encoding="utf-8")
    total_runs = sum(i["k"] for i in plan)
    print(f"\n{len(picks)} puzzles -> {total_runs} runs "
          f"-> plans/phase1_candidates.json (Jace approves, rename to phase1.json)")


if __name__ == "__main__":
    main()
