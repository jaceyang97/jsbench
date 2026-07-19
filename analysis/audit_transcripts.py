"""Summarize run transcripts for the Phase-0 gate review.

For each run directory: exit reason, correctness, turns, cost, tool mix,
bash command peek, image handling, and any network-suspect lines — so a human
can review 20 transcripts in minutes and drill into anomalies only.

Usage: .venv/Scripts/python -m analysis.audit_transcripts [--full run_id]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"


def summarize(run_dir: Path) -> dict | None:
    rj = run_dir / "run.json"
    tj = run_dir / "transcript.jsonl"
    if not rj.exists():
        return None
    rec = json.loads(rj.read_text(encoding="utf-8"))
    tools = Counter()
    bash_cmds: list[str] = []
    read_targets: list[str] = []
    if tj.exists():
        for line in tj.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            if m.get("kind") != "AssistantMessage":
                continue
            for b in (m.get("data", {}).get("content") or []):
                if isinstance(b, dict) and b.get("name"):
                    tools[b["name"]] += 1
                    inp = b.get("input") or {}
                    if b["name"] == "Bash":
                        bash_cmds.append(str(inp.get("command", ""))[:120])
                    if b["name"] == "Read":
                        read_targets.append(str(inp.get("file_path", "")))
    return {
        "run_id": run_dir.name,
        "puzzle": rec.get("puzzle_id"), "model": rec.get("model_requested"),
        "exit": rec.get("exit_reason"), "correct": rec.get("correct"),
        "turns": rec.get("num_turns"), "cost": rec.get("cost_usd"),
        "wall_s": rec.get("wall_time_s"),
        "bare": rec.get("bare_mode"),
        "suspect": rec.get("suspect_cheating"),
        "handoff": rec.get("model_handoff_detected"),
        "tools": dict(tools),
        "read_images": [t for t in read_targets if "images" in t.replace("\\", "/")],
        "bash_sample": bash_cmds[:5],
        "answer": rec.get("submitted_answer"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", type=str, default=None, help="dump one run's details")
    args = ap.parse_args()

    if args.full:
        print(json.dumps(summarize(RUNS / args.full), indent=2, ensure_ascii=False))
        return

    rows = [s for d in sorted(RUNS.iterdir()) if d.is_dir()
            if (s := summarize(d))]
    print(f"{'puzzle':26s} {'model':28s} {'exit':12s} {'ok':3s} {'turns':5s} "
          f"{'cost':7s} {'flags':10s} answer")
    for s in rows:
        flags = "".join([
            "S" if s["suspect"] else "",
            "H" if s["handoff"] else "",
            "!" if not s["bare"] else "",
        ])
        print(f"{(s['puzzle'] or '?')[:26]:26s} {(s['model'] or '?')[:28]:28s} "
              f"{(s['exit'] or '?')[:12]:12s} {'Y' if s['correct'] else 'n':3s} "
              f"{str(s['turns']):5s} ${(s['cost'] or 0):5.2f} {flags:10s} "
              f"{str(s['answer'])[:40]}")
    print("\nflags: S=suspect_cheating  H=model_handoff  !=non-bare(OAuth smoke)")


if __name__ == "__main__":
    main()
