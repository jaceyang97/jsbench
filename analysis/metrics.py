"""Statistical estimators for jsbench (per Chen et al. 2021 + Miller 2024).

- pass@k: unbiased estimator 1 - C(n-c,k)/C(n,k), computed per puzzle then
  averaged over puzzles.
- pass@1 two-stage: per-puzzle mean over samples, then mean over puzzles;
  SEM = std(per-puzzle means)/sqrt(P) (puzzles as sampling units).
- clustered SE: series puzzles (shared cluster label) form one cluster.
- paired difference between two models on the same puzzle set.
"""
from __future__ import annotations

import math
from collections import defaultdict


def pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased pass@k for one problem: n samples, c correct."""
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def per_puzzle_means(runs: list[dict]) -> dict[str, float]:
    """puzzle_id -> mean correctness over samples (pass@1 per puzzle)."""
    by_puzzle: dict[str, list[bool]] = defaultdict(list)
    for r in runs:
        by_puzzle[r["puzzle_id"]].append(bool(r.get("correct")))
    return {p: sum(v) / len(v) for p, v in by_puzzle.items()}


def pass1_with_sem(runs: list[dict]) -> tuple[float, float, int]:
    """(pass@1, SEM, n_puzzles) — two-stage estimator."""
    means = per_puzzle_means(runs)
    vals = list(means.values())
    p = len(vals)
    if p == 0:
        return float("nan"), float("nan"), 0
    mean = sum(vals) / p
    if p == 1:
        return mean, float("nan"), 1
    var = sum((v - mean) ** 2 for v in vals) / (p - 1)
    return mean, math.sqrt(var / p), p


def passk_with_sem(runs: list[dict], k: int) -> tuple[float, float, int]:
    """(pass@k, SEM over puzzles, n_puzzles) using the unbiased estimator."""
    by_puzzle: dict[str, list[bool]] = defaultdict(list)
    for r in runs:
        by_puzzle[r["puzzle_id"]].append(bool(r.get("correct")))
    vals = []
    for corr in by_puzzle.values():
        n, c = len(corr), sum(corr)
        if n >= k:
            vals.append(pass_at_k(n, c, k))
    p = len(vals)
    if p == 0:
        return float("nan"), float("nan"), 0
    mean = sum(vals) / p
    if p == 1:
        return mean, float("nan"), 1
    var = sum((v - mean) ** 2 for v in vals) / (p - 1)
    return mean, math.sqrt(var / p), p


def clustered_sem(runs: list[dict], cluster_of: dict[str, str]) -> tuple[float, float, int]:
    """(pass@1, clustered SEM, n_clusters).

    cluster_of maps puzzle_id -> cluster label (e.g. 'hooks' for the whole
    Hooks series); puzzles absent from the map are their own cluster.
    Cluster-level means, then CLT over clusters.
    """
    means = per_puzzle_means(runs)
    by_cluster: dict[str, list[float]] = defaultdict(list)
    for pid, m in means.items():
        by_cluster[cluster_of.get(pid, pid)].append(m)
    cvals = [sum(v) / len(v) for v in by_cluster.values()]
    g = len(cvals)
    if g == 0:
        return float("nan"), float("nan"), 0
    mean = sum(cvals) / g
    if g == 1:
        return mean, float("nan"), 1
    var = sum((v - mean) ** 2 for v in cvals) / (g - 1)
    return mean, math.sqrt(var / g), g


def paired_diff(runs_a: list[dict], runs_b: list[dict]) -> dict:
    """Paired comparison of model A vs B on shared puzzles.

    Returns mean difference (A-B), paired SEM, 95% CI, correlation, n.
    """
    ma, mb = per_puzzle_means(runs_a), per_puzzle_means(runs_b)
    shared = sorted(set(ma) & set(mb))
    n = len(shared)
    if n < 2:
        return {"n": n, "mean_diff": float("nan"), "sem": float("nan"),
                "ci95": (float("nan"), float("nan")), "corr": float("nan")}
    diffs = [ma[p] - mb[p] for p in shared]
    mean_d = sum(diffs) / n
    var_d = sum((d - mean_d) ** 2 for d in diffs) / (n - 1)
    sem = math.sqrt(var_d / n)

    xa = [ma[p] for p in shared]
    xb = [mb[p] for p in shared]
    mean_a, mean_b = sum(xa) / n, sum(xb) / n
    cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(xa, xb)) / (n - 1)
    sa = math.sqrt(sum((a - mean_a) ** 2 for a in xa) / (n - 1))
    sb = math.sqrt(sum((b - mean_b) ** 2 for b in xb) / (n - 1))
    corr = cov / (sa * sb) if sa > 0 and sb > 0 else float("nan")

    return {"n": n, "mean_diff": mean_d, "sem": sem,
            "ci95": (mean_d - 1.96 * sem, mean_d + 1.96 * sem),
            "corr": corr,
            "significant": abs(mean_d) > 1.96 * sem if sem == sem else False}


def mde_paired(n_puzzles: int, sd_diff: float = 0.4, alpha_z: float = 1.96,
               power_z: float = 0.84) -> float:
    """Minimum detectable effect (pp) for a paired test with n puzzles.

    sd_diff=0.4 is a typical SD of per-puzzle paired differences for
    binary-ish outcomes. With 20 puzzles: ~0.25 => only >=25pp gaps are
    reliably detectable — report this honestly.
    """
    return (alpha_z + power_z) * sd_diff / math.sqrt(n_puzzles)
