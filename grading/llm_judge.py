"""Optional LLM judge — a SECONDARY adjudicator for hard answer formats.

Deterministic grading (normalize.py / verifiers.py) is always PRIMARY and is
what the harness records as `correct`. Some answers are awkward to grade
deterministically (free-form strings, prose, multi-part with odd separators,
expressions typed many ways). This module re-adjudicates such runs with an LLM
and writes a *separate* `llm_judge_correct` field so the two signals can be
compared. It never overwrites the deterministic verdict.

Design guards against score inflation:
  - Only runs the LLM on cases flagged hard: grader "grading_mode":"llm", OR
    answer_type in {string, expression, multi}, OR deterministic verdict was
    wrong but the submitted answer is non-empty (potential false-negative).
  - The judge is asked for strict mathematical/semantic equivalence, given the
    puzzle's own answer-format spec. It is told to default to NOT equivalent
    when unsure. It never sees "please be lenient".
  - Uses a fixed model (opus) with thinking disabled and a structured verdict.

Reads runs/runs.jsonl, writes llm_judge fields back into each run.json and a
consolidated runs/llm_judge.jsonl. Run AFTER a batch completes.

Usage: .venv/Scripts/python -m grading.llm_judge [--only run_id1,run_id2]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "runs"
GRADERS = ROOT / "data" / "graders"
PUZZLES = ROOT / "data" / "puzzles"
JUDGE_MODEL = "claude-opus-4-8"
HARD_TYPES = {"string", "expression", "multi"}

JUDGE_SYSTEM = """\
You are a strict grader for a mathematics/logic puzzle benchmark. You decide \
whether a submitted answer is equivalent to the reference answer, according to \
the puzzle's stated answer format. Judge mathematical and semantic equivalence \
only — different notation for the same value/object is equivalent (e.g. 1/2 and \
0.5; "American Graffiti" and "american graffiti"); a different value/object is \
not. Ignore surrounding prose, restatements, and units only if the format \
allows. If you are not confident the two are the same, answer "no". Do not be \
lenient and do not give partial credit."""

JUDGE_TEMPLATE = """\
Puzzle answer format: {answer_format}

Reference (correct) answer:
{reference}

Submitted answer:
{submitted}

Are these equivalent under the stated format? Respond with a JSON object only: \
{{"equivalent": true|false, "reason": "<one sentence>"}}"""


def needs_judge(run: dict, grader: dict) -> bool:
    if grader.get("grading_mode") == "llm":
        return True
    if grader.get("answer_type") in HARD_TYPES:
        return True
    # potential deterministic false-negative: wrong but a non-empty answer given
    if not run.get("correct") and run.get("submitted_answer"):
        return True
    return False


def judge_one(client, run: dict) -> dict:
    pid = run["puzzle_id"]
    grader = json.loads((GRADERS / f"{pid}.json").read_text(encoding="utf-8"))
    meta = json.loads((PUZZLES / pid / "metadata.json").read_text(encoding="utf-8"))
    prompt = JUDGE_TEMPLATE.format(
        answer_format=meta.get("answer_format", grader.get("answer_type", "")),
        reference=grader["answer"],
        submitted=run.get("submitted_answer"))
    resp = client.messages.create(
        model=JUDGE_MODEL, max_tokens=500,
        thinking={"type": "disabled"},
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": {
            "type": "object",
            "properties": {"equivalent": {"type": "boolean"},
                           "reason": {"type": "string"}},
            "required": ["equivalent", "reason"],
            "additionalProperties": False}}})
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    verdict = json.loads(text)
    return {"llm_judge_correct": bool(verdict["equivalent"]),
            "llm_judge_reason": verdict["reason"],
            "llm_judge_model": JUDGE_MODEL}


def main() -> None:
    import anthropic
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=str, default=None)
    ap.add_argument("--all", action="store_true",
                    help="judge every run, not just hard-format ones")
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else None

    client = anthropic.Anthropic()
    out_path = RUNS_DIR / "llm_judge.jsonl"
    judged = 0
    disagreements = []
    with out_path.open("a", encoding="utf-8") as out:
        for d in sorted(RUNS_DIR.iterdir()):
            rj = d / "run.json"
            if not d.is_dir() or not rj.exists():
                continue
            run = json.loads(rj.read_text(encoding="utf-8"))
            if only and run["run_id"] not in only:
                continue
            if "llm_judge_correct" in run and not args.only:
                continue  # idempotent
            grader = json.loads((GRADERS / f"{run['puzzle_id']}.json")
                                .read_text(encoding="utf-8"))
            if not args.all and not needs_judge(run, grader):
                continue
            try:
                jv = judge_one(client, run)
            except Exception as exc:
                jv = {"llm_judge_correct": None, "llm_judge_reason": f"error: {exc!r}",
                      "llm_judge_model": JUDGE_MODEL}
            run.update(jv)
            rj.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
            out.write(json.dumps({"run_id": run["run_id"], "puzzle_id": run["puzzle_id"],
                                  "deterministic": run.get("correct"), **jv},
                                 ensure_ascii=False) + "\n")
            out.flush()
            judged += 1
            if jv["llm_judge_correct"] is not None and jv["llm_judge_correct"] != run.get("correct"):
                disagreements.append((run["run_id"], run.get("correct"),
                                      jv["llm_judge_correct"], jv["llm_judge_reason"]))
            print(f"{run['run_id']}: det={run.get('correct')} "
                  f"llm={jv['llm_judge_correct']}")

    print(f"\njudged {judged} runs; {len(disagreements)} disagreement(s):")
    for rid, det, llm, why in disagreements:
        print(f"  {rid}: deterministic={det} llm={llm} — {why}")
    print("\nNOTE: deterministic verdict remains PRIMARY. Review disagreements "
          "and, if the LLM is right, fix the grader (aliases/tolerance) and "
          "re-run analysis.regrade rather than trusting the LLM blindly.")


if __name__ == "__main__":
    main()
