"""Generate the results report from runs.jsonl + probes.jsonl.

Sections: per-model pass@1 +/- SEM (and pass@k where k>1), paired
comparisons, pre/post-cutoff split, difficulty buckets, memorization
sensitivity (excluding probe-correct puzzles), cost table.

Usage: .venv/Scripts/python -m analysis.report [--out report.md]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analysis.metrics import (  # noqa: E402
    mde_paired, paired_diff, pass1_with_sem, passk_with_sem,
)

RUNS = ROOT / "runs" / "runs.jsonl"
PROBES = ROOT / "runs" / "probes.jsonl"
MODELS_CFG = json.loads((ROOT / "config" / "models.json").read_text(encoding="utf-8"))
TIER_OF = {m["model_id"]: m["tier"] for m in MODELS_CFG["models"]}
CUTOFF_OF = {m["model_id"]: m["reliable_cutoff"] for m in MODELS_CFG["models"]}


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def fmt_pct(x: float) -> str:
    return "n/a" if x != x else f"{100*x:.1f}%"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="runs/report.md")
    args = ap.parse_args()

    runs = [r for r in load_jsonl(RUNS)
            if r.get("arm") == "agentic" and r.get("exit_reason") != "error"]
    probes = load_jsonl(PROBES)
    index = {e["puzzle_id"]: e for e in
             json.loads((ROOT / "data" / "puzzles_index.json").read_text(encoding="utf-8"))}

    memorized = {(p["puzzle_id"], p["tier"]) for p in probes
                 if p.get("memorization_suspect")}

    by_model: dict[str, list[dict]] = defaultdict(list)
    for r in runs:
        by_model[r["model_requested"]].append(r)

    L = ["# jsbench results", ""]

    # --- PRIMARY: pass@k (per Jace: puzzles are rarely one-shot; attempts are
    # fully independent — no feedback ever returns to any agent)
    L += ["## PRIMARY: pass@k (unbiased estimator) ± SEM", "",
          "| model | k | pass@k | SEM | pass@1 | puzzles | runs | excl. memorized pass@k | suspect runs |",
          "|---|---|---|---|---|---|---|---|---|"]
    for mid, rs in sorted(by_model.items()):
        tier = TIER_OF.get(mid, "?")
        min_n = min((len([r for r in rs if r["puzzle_id"] == pid])
                     for pid in {r["puzzle_id"] for r in rs}), default=1)
        k = max(min_n, 1)
        pk, sem, np_ = passk_with_sem(rs, k)
        p1, _, _ = pass1_with_sem(rs)
        clean = [r for r in rs if (r["puzzle_id"], tier) not in memorized]
        pkc, _, npc = passk_with_sem(clean, k)
        n_suspect = sum(1 for r in rs if r.get("suspect_cheating"))
        L.append(f"| {mid} | {k} | {fmt_pct(pk)} | {fmt_pct(sem)} | {fmt_pct(p1)} "
                 f"| {np_} | {len(rs)} | {fmt_pct(pkc)} (n={npc}) | {n_suspect} |")

    # cross-model comparable pass@k at the common k
    common_k = min((min((len([r for r in rs if r["puzzle_id"] == pid])
                         for pid in {r["puzzle_id"] for r in rs}), default=1)
                    for rs in by_model.values()), default=1)
    if common_k > 1:
        L += ["", f"## cross-model pass@{common_k} (common k)", ""]
        for mid, rs in sorted(by_model.items()):
            pk, sem, np_ = passk_with_sem(rs, common_k)
            L.append(f"- {mid}: {fmt_pct(pk)} ± {fmt_pct(sem)} ({np_} puzzles)")

    # --- paired comparisons
    L += ["", "## paired differences (A − B, same puzzles)", "",
          "| A | B | Δ | SEM | 95% CI | corr | sig? |", "|---|---|---|---|---|---|---|"]
    for (ma, ra), (mb, rb) in combinations(sorted(by_model.items()), 2):
        d = paired_diff(ra, rb)
        if d["n"] < 2:
            continue
        lo, hi = d["ci95"]
        L.append(f"| {ma} | {mb} | {100*d['mean_diff']:+.1f}pp | {100*d['sem']:.1f}pp "
                 f"| [{100*lo:+.1f}, {100*hi:+.1f}] | {d['corr']:.2f} "
                 f"| {'YES' if d.get('significant') else 'no'} |")

    # --- pre/post cutoff
    L += ["", "## pre/post reliable-cutoff split", "",
          "| model | pre-cutoff pass@1 (n) | post-cutoff pass@1 (n) |", "|---|---|---|"]
    for mid, rs in sorted(by_model.items()):
        cutoff = CUTOFF_OF.get(mid, "9999-99")
        pre = [r for r in rs if index.get(r["puzzle_id"], {}).get("date", "") <= cutoff]
        post = [r for r in rs if index.get(r["puzzle_id"], {}).get("date", "") > cutoff]
        p_pre, _, n_pre = pass1_with_sem(pre)
        p_post, _, n_post = pass1_with_sem(post)
        L.append(f"| {mid} | {fmt_pct(p_pre)} ({n_pre}) | {fmt_pct(p_post)} ({n_post}) |")

    # --- cost
    L += ["", "## cost", "", "| model | runs | total $ | mean $/run | mean turns |",
          "|---|---|---|---|---|"]
    total = 0.0
    for mid, rs in sorted(by_model.items()):
        costs = [r.get("cost_usd") or 0 for r in rs]
        turns = [r.get("num_turns") or 0 for r in rs]
        total += sum(costs)
        L.append(f"| {mid} | {len(rs)} | ${sum(costs):.2f} "
                 f"| ${sum(costs)/max(len(rs),1):.2f} | {sum(turns)/max(len(turns),1):.0f} |")
    L.append(f"\n**Total agentic spend: ${total:.2f}**")

    # --- power honesty
    n_puz = len({r["puzzle_id"] for r in runs})
    if n_puz:
        L += ["", f"_Power note: with {n_puz} puzzles, the paired-test MDE is "
              f"roughly ±{100*mde_paired(n_puz):.0f}pp — only differences larger "
              "than this are reliably detectable at this budget._"]

    out = ROOT / args.out
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"report -> {out}")
    print("\n".join(L[:20]))


if __name__ == "__main__":
    main()
