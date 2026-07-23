"""Checkpoint auditor — the gate between batches of the full-bench run.

Audits everything recorded so far (or one batch) against hard/soft thresholds
covering the two optimization targets: CORRECTNESS and COST. Produces a
machine verdict (exit code) + human report (runs/checkpoints/cp{N}_report.md).

  HARD FAIL  -> do NOT launch the next batch until fixed (exit 2)
  WARN       -> proceed allowed, but items need review           (exit 1)
  PASS       -> proceed                                          (exit 0)

Checks:
  infra:    error rate, timeout rate, submission rate, bare_mode, containerized
            runner, transcript completeness, image delivery
  grading:  malformed answers, judge-disagreement queue, verifier errors,
            graded-wrong-with-answer sample list (eq-side-bug class)
  cost:     per-model mean vs forecast band, projected total vs hard cap
  integrity:suspect_cheating unreviewed, model handoffs, pip installs list

Usage:
  python -m analysis.checkpoint --batch plans/checkpoints/cp1.json --name cp1
  python -m analysis.checkpoint --all --name all      # audit everything so far
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CONFIG = yaml.safe_load((ROOT / "config" / "bench.yaml").read_text(encoding="utf-8"))
RUNS_LOG = ROOT / CONFIG["paths"]["runs_log"]
FORECAST = {"claude-haiku-4-5-20251001": 0.30, "claude-sonnet-5": 0.79,
            "claude-opus-4-8": 0.55, "claude-fable-5": 0.82}

TH = {  # thresholds
    "error_rate_hard": 0.05, "error_rate_warn": 0.02,
    "timeout_rate_hard": 0.20, "timeout_rate_warn": 0.10,
    "submission_rate_hard": 0.85, "submission_rate_warn": 0.92,
    "cost_band_lo": 0.4, "cost_band_hi": 2.0,   # x forecast per model (warn)
    "malformed_rate_warn": 0.02,
}


def load_runs() -> list[dict]:
    out = []
    if RUNS_LOG.exists():
        for line in RUNS_LOG.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def effective_runs(raw: list[dict]) -> tuple[list[dict], int]:
    """Latest record per (puzzle, model, sample) — the ledger is append-only
    and infra-error runs get retried, so superseded lines must not be counted
    as failures of the final batch state. Returns (effective, n_superseded)."""
    seen: dict[tuple, dict] = {}
    for r in raw:
        seen[(r.get("puzzle_id"), r.get("model_requested"), r.get("sample_idx"))] = r
    return list(seen.values()), len(raw) - len(seen)


def bundle_has_images(puzzle_id: str) -> bool:
    d = ROOT / "data" / "puzzles" / str(puzzle_id) / "images"
    return d.is_dir() and any(d.iterdir())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=str, default=None,
                    help="plan file; audit only runs whose (puzzle,tier) is in it")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--name", type=str, required=True)
    args = ap.parse_args()

    raw = [r for r in load_runs() if r.get("arm") == "agentic"]
    runs, n_superseded = effective_runs(raw)
    if args.batch:
        plan = json.loads(Path(args.batch).read_text(encoding="utf-8"))
        keys = {(i["puzzle_id"],) for i in plan}
        batch_puzzles = {i["puzzle_id"] for i in plan}
        runs_b = [r for r in runs if r["puzzle_id"] in batch_puzzles]
    else:
        plan = None
        runs_b = runs

    hard, warn, info = [], [], []
    n = len(runs_b)
    if n == 0:
        print("no runs to audit")
        sys.exit(2)

    # ---------- infra ----------
    if n_superseded:
        info.append(f"superseded ledger lines (infra retries, not counted): {n_superseded}")
    errors = [r for r in runs_b if r.get("exit_reason") == "error"]
    er = len(errors) / n
    (hard if er > TH["error_rate_hard"] else warn if er > TH["error_rate_warn"] else info).append(
        f"error rate {er:.1%} ({len(errors)}/{n}) [final states]"
        + (f" — run_ids: {[r.get('run_id') for r in errors][:5]}" if errors else ""))

    timeouts = sum(1 for r in runs_b if r.get("exit_reason") == "timeout")
    tr = timeouts / n
    (hard if tr > TH["timeout_rate_hard"] else warn if tr > TH["timeout_rate_warn"] else info).append(
        f"timeout rate {tr:.1%} ({timeouts}/{n})")

    ok_runs = [r for r in runs_b if r.get("exit_reason") != "error"]
    # runs killed by resource caps (max turns / budget / wall clock) never get
    # to write answer.json — that is model capability data, not an infra
    # failure. Submission health is measured over self-terminated runs; a high
    # cap-hit rate is surfaced separately (WARN, review the transcripts).
    cap_hit = [r for r in ok_runs
               if r.get("exit_reason") == "attempts_exhausted"
               and not r.get("submitted_answer")]
    ch = len(cap_hit) / max(len(ok_runs), 1)
    (warn if ch > 0.20 else info).append(
        f"no-answer rate (resource-cap terminations): {ch:.1%} ({len(cap_hit)}/{len(ok_runs)})")
    self_ended = [r for r in ok_runs if r not in cap_hit]
    submitted = sum(1 for r in self_ended if r.get("submitted_answer"))
    sr = submitted / max(len(self_ended), 1)
    (hard if sr < TH["submission_rate_hard"] else warn if sr < TH["submission_rate_warn"] else info).append(
        f"submission rate {sr:.1%} ({submitted}/{len(self_ended)} self-terminated runs)")

    non_bare = [r for r in ok_runs if not r.get("bare_mode")]
    (hard if non_bare else info).append(
        f"bare_mode violations: {len(non_bare)}"
        + (f" {[r['run_id'] for r in non_bare][:3]}" if non_bare else ""))

    # sdk-session = Claude Code harness; codex-exec = Codex harness. Both are
    # first-class runners for this benchmark.
    non_sess = [r for r in ok_runs if r.get("runner") not in ("sdk-session", "codex-exec")]
    (warn if non_sess else info).append(f"non-standard runner: {len(non_sess)}")

    img_runs = [r for r in ok_runs if r.get("image_delivered") is False
                and bundle_has_images(r.get("puzzle_id"))]
    (hard if img_runs else info).append(
        f"image-delivery failures (image puzzles only): {len(img_runs)}")

    missing_transcript = [r for r in ok_runs
                          if not (ROOT / r.get("transcript_path", "@none")).exists()]
    (hard if missing_transcript else info).append(
        f"missing transcripts: {len(missing_transcript)}")

    # ---------- grading ----------
    malformed = [r for r in ok_runs
                 if any(a.get("grade_status") == "malformed"
                        for a in r.get("attempts", []))]
    mr = len(malformed) / max(len(ok_runs), 1)
    (warn if mr > TH["malformed_rate_warn"] else info).append(
        f"malformed answer.json rate {mr:.1%}")

    judge_path = ROOT / "runs" / "llm_judge.jsonl"
    disagreements = []
    if judge_path.exists():
        for line in judge_path.read_text(encoding="utf-8").splitlines():
            try:
                j = json.loads(line)
            except json.JSONDecodeError:
                continue
            if j.get("llm_judge_correct") is not None and \
               j.get("llm_judge_correct") != j.get("deterministic"):
                disagreements.append(j["run_id"])
    (warn if disagreements else info).append(
        f"judge disagreements pending review: {len(disagreements)}"
        + (f" {disagreements[:5]}" if disagreements else ""))

    wrong_with_answer = [r["run_id"] for r in ok_runs
                         if not r.get("correct") and r.get("submitted_answer")]
    info.append(f"graded-wrong-with-answer (eq-side-bug class, sample for review): "
                f"{len(wrong_with_answer)}; first 5: {wrong_with_answer[:5]}")

    # ---------- cost ----------
    by_model_cost: dict[str, list[float]] = defaultdict(list)
    for r in ok_runs:
        if r.get("cost_usd") is not None:
            by_model_cost[r["model_requested"]].append(r["cost_usd"])
    for mid, costs in sorted(by_model_cost.items()):
        mean = sum(costs) / len(costs)
        fc = FORECAST.get(mid)
        line = f"{mid}: mean ${mean:.2f}/run over {len(costs)} runs (forecast ${fc})"
        if fc and not (TH["cost_band_lo"] * fc <= mean <= TH["cost_band_hi"] * fc):
            warn.append("COST BAND: " + line)
        else:
            info.append(line)

    all_spent = sum((r.get("cost_usd") or 0) for r in load_runs())
    cap = CONFIG["budget"]["hard_cap_usd"]
    frac = all_spent / cap
    (hard if frac > 0.95 else warn if frac > 0.8 else info).append(
        f"cumulative spend ${all_spent:.2f} / cap ${cap} ({frac:.0%})")

    # ---------- integrity ----------
    suspects = [r["run_id"] for r in ok_runs
                if r.get("suspect_cheating") and not r.get("suspect_reviewed")]
    reviewed = sum(1 for r in ok_runs
                   if r.get("suspect_cheating") and r.get("suspect_reviewed"))
    (hard if suspects else info).append(
        f"suspect_cheating unreviewed: {len(suspects)} (reviewed-cleared: {reviewed})"
        + (f" {suspects[:5]}" if suspects else ""))
    handoffs = [r["run_id"] for r in ok_runs if r.get("model_handoff_detected")]
    (warn if handoffs else info).append(f"model handoffs: {len(handoffs)}")
    pips = sorted({p for r in ok_runs for p in (r.get("pip_installs") or [])})
    info.append(f"pip installs observed: {pips or 'none'}")

    # ---------- solve-rate sanity ----------
    by_model_solve: dict[str, list[bool]] = defaultdict(list)
    for r in ok_runs:
        by_model_solve[r["model_requested"]].append(bool(r.get("correct")))
    for mid, v in sorted(by_model_solve.items()):
        info.append(f"{mid}: solve {sum(v)}/{len(v)}")

    # ---------- report ----------
    # hard/warn only ever receive entries when their condition fired
    verdict = "HARD-FAIL" if hard else ("WARN" if warn else "PASS")
    out_dir = ROOT / "runs" / "checkpoints"
    out_dir.mkdir(exist_ok=True)
    L = [f"# checkpoint {args.name} — {verdict}", "",
         f"runs audited: {n} (batch) / {len(runs)} (total)", ""]
    for title, items in (("HARD", hard), ("WARN", warn), ("INFO", info)):
        if items:
            L.append(f"## {title}")
            L += [f"- {x}" for x in items]
            L.append("")
    report = "\n".join(L)
    (out_dir / f"{args.name}_report.md").write_text(report, encoding="utf-8")
    print(report)
    sys.exit(2 if verdict == "HARD-FAIL" else (1 if verdict == "WARN" else 0))


if __name__ == "__main__":
    main()
