"""Codex harness runner — the OpenAI/GPT counterpart to harness/run_agent.py.

Runs one (puzzle, GPT model, sample) under the OpenAI **Codex CLI** instead of
Claude Code, and emits the IDENTICAL run.json + transcript.jsonl schema so the
whole downstream pipeline (host-side grading, cheating audit, analysis.report,
checkpoints) treats both harnesses the same. This is the "native-agent product
comparison": each model runs in its own agent scaffold; everything else — the
puzzle bundle, the task framing, k=3 independent sampling, the disposable
container, the egress blocklist, answer-store masking, host-side grading, the
per-tier budget/turn caps — is held constant.

What necessarily differs (and is recorded honestly): the agent scaffold itself
(Codex's system prompt / planning loop / tool semantics vs Claude Code's), and
that cost is computed from token usage x published pricing rather than returned
by the SDK. Both models receive the SAME task text (SYSTEM_APPEND + render_task)
and the same images.

Runs INSIDE the codex container (invoked by orchestrate.runner via
`docker compose run agent-codex python3 -m harness.run_agent_codex ...`).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Reuse every shared helper so the two harnesses stay byte-for-byte comparable
# where it matters (bundle copy, answer read, cheating audit, record schema).
from harness.run_agent import (  # noqa: E402
    CONFIG, MODELS, PUZZLES_DIR, RUNS_DIR,
    build_workdir, read_submitted_answer, audit_transcript,
)
from harness.prompts import (  # noqa: E402
    SYSTEM_APPEND, SYSTEM_APPEND_SHA256, TASK_RULES_SHA256,
    RETRY_FEEDBACK_SHA256, render_task,
)

CODEX_VERSION = CONFIG["harness"].get("codex_version", "unknown")


def codex_prompt(problem_md: str, answer_format: str, date: str, has_images: bool) -> str:
    """Identical task content to the Claude side. On the Claude harness the
    SYSTEM_APPEND rides in the system prompt and render_task is the first user
    message; Codex keeps its own native system prompt, so we hand it both as the
    initial instruction. The two models thus read the same task, differing only
    in the harness scaffold — exactly the comparison we want."""
    return SYSTEM_APPEND + "\n\n" + render_task(problem_md, answer_format, date, has_images)


def _login(codex_home: Path) -> bool:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return False
    codex_home.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(["codex", "login", "--with-api-key"], input=key,
                       text=True, capture_output=True,
                       env={**os.environ, "CODEX_HOME": str(codex_home)})
    return "logged in" in (p.stdout + p.stderr).lower()


def _map_event(ev: dict, t: float, tf, counters: dict, usage_acc: dict) -> None:
    """Map one Codex JSONL event to the Claude-compatible transcript schema and
    append it to the transcript file. Tool calls become AssistantMessage content
    blocks with name/input so audit_transcript() works unchanged."""
    typ = ev.get("type")
    line = None
    if typ == "item.completed":
        item = ev.get("item", {})
        it = item.get("type")
        if it == "agent_message":
            line = {"t": t, "attempt": 1, "kind": "AssistantMessage",
                    "data": {"content": [{"type": "text", "text": item.get("text", "")}]}}
        elif it == "reasoning":
            line = {"t": t, "attempt": 1, "kind": "AssistantMessage",
                    "data": {"content": [{"type": "thinking",
                                          "text": item.get("text", "")}]}}
        elif it == "command_execution":
            counters["tool_calls"] += 1
            line = {"t": t, "attempt": 1, "kind": "AssistantMessage",
                    "data": {"content": [{"name": "Bash",
                                          "input": {"command": item.get("command", "")}}]}}
            # the command's output comes back as a UserMessage (tool result),
            # mirroring how Claude tool results are logged
            res = {"t": t, "attempt": 1, "kind": "UserMessage",
                   "data": {"tool_use_result": {
                       "stdout": item.get("aggregated_output", ""),
                       "exit_code": item.get("exit_code"),
                       "status": item.get("status")}}}
            tf.write(json.dumps(line, ensure_ascii=False) + "\n")
            tf.write(json.dumps(res, ensure_ascii=False) + "\n")
            return
        elif it == "error":
            line = {"t": t, "attempt": 1, "kind": "AssistantMessage",
                    "data": {"content": [{"type": "text",
                                          "text": item.get("message", "")}], },
                    "error": item.get("message")}
    elif typ == "turn.completed":
        u = ev.get("usage", {}) or {}
        for k in ("input_tokens", "cached_input_tokens", "output_tokens",
                  "reasoning_output_tokens", "cache_write_input_tokens"):
            usage_acc[k] = usage_acc.get(k, 0) + (u.get(k) or 0)
        counters["turns"] += 1
        line = {"t": t, "attempt": 1, "kind": "ResultMessage",
                "data": {"subtype": "turn.completed", "usage": u}}
    elif typ == "turn.failed":
        counters["failed"] = ev.get("error", {}).get("message", "turn.failed")
        line = {"t": t, "attempt": 1, "kind": "ResultMessage",
                "data": {"subtype": "turn.failed", "error": ev.get("error")}}
    elif typ in ("thread.started", "turn.started"):
        line = {"t": t, "attempt": 1, "kind": "SystemMessage", "data": ev}
    if line is not None:
        tf.write(json.dumps(line, ensure_ascii=False) + "\n")


def _cost_usd(usage: dict, pricing: dict) -> float:
    """OpenAI cost model: uncached input at input price, cached input at the
    cache-read price, output (reasoning included) at output price."""
    inp = usage.get("input_tokens", 0)
    cached = usage.get("cached_input_tokens", 0)
    out = usage.get("output_tokens", 0)
    uncached = max(inp - cached, 0)
    return round((uncached * pricing["input"]
                  + cached * pricing.get("cache_read", 0)
                  + out * pricing["output"]) / 1_000_000, 6)


def run_codex(puzzle_id: str, tier: str, sample_idx: int = 1,
              run_id: str | None = None, timeout_s: int | None = None) -> dict:
    import uuid
    mcfg = MODELS[tier]
    assert mcfg.get("harness") == "codex", f"{tier} is not a codex tier"
    run_id = run_id or f"{puzzle_id}_{tier}_s{sample_idx}_{uuid.uuid4().hex[:8]}"

    out_base = os.environ.get("JSB_RUN_DIR")
    run_dir = Path(out_base) if out_base else (RUNS_DIR / run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    workdir = build_workdir(puzzle_id, run_dir)

    meta = json.loads((workdir / "metadata.json").read_text(encoding="utf-8"))
    problem_md = (workdir / "problem.md").read_text(encoding="utf-8")
    img_dir = workdir / "images"
    images = sorted(str(p) for p in img_dir.iterdir()) if img_dir.exists() else []

    prompt = codex_prompt(problem_md, meta["answer_format"], meta["date"], bool(images))
    transcript_path = run_dir / "transcript.jsonl"
    (run_dir / "initial_message.json").write_text(json.dumps(
        {"prompt": prompt, "images": [Path(i).name for i in images]},
        ensure_ascii=False, indent=2), encoding="utf-8")

    codex_home = Path("/tmp") / f"codex_home_{run_id}"
    logged_in = _login(codex_home)

    # The prompt goes via STDIN, not as a positional arg: `-i/--image` is
    # variadic (<FILE>...), so a trailing positional prompt after `-i` is
    # swallowed as another image file. Codex reads the prompt from stdin when
    # no positional prompt is given.
    cmd = ["codex", "exec", "--json", "-m", mcfg["model_id"],
           "-C", str(workdir), "--skip-git-repo-check",
           "--dangerously-bypass-approvals-and-sandbox",
           "-o", str(run_dir / "last_message.txt")]
    for img in images:
        cmd += ["-i", img]

    (run_dir / "options.json").write_text(json.dumps({
        "harness": f"codex@{CODEX_VERSION}", "model": mcfg["model_id"],
        "cmd": cmd[:-1] + ["<prompt>"], "sandbox": "bypass (container is the sandbox)",
        "system_prompt_sha256": SYSTEM_APPEND_SHA256,
        "task_rules_sha256": TASK_RULES_SHA256,
        "max_budget_usd": mcfg["max_budget_usd"], "max_turns": mcfg["max_turns"],
        "wall_clock_timeout_s": timeout_s or CONFIG["wall_clock_timeout_s"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    start_ts = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()
    counters = {"tool_calls": 0, "turns": 0, "failed": None}
    usage_acc: dict = {}
    timed_out = False
    raw_path = run_dir / "codex_raw.jsonl"

    env = {**os.environ, "CODEX_HOME": str(codex_home)}
    tf = transcript_path.open("a", encoding="utf-8")
    rawf = raw_path.open("a", encoding="utf-8")
    try:
        proc = subprocess.run(
            cmd, env=env, text=True, capture_output=True, input=prompt,
            timeout=(timeout_s or CONFIG["wall_clock_timeout_s"]))
        stdout, stderr = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        timed_out = True
        stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
    for ln in stdout.splitlines():
        ln = ln.strip()
        if not ln or not ln.startswith("{"):
            continue
        try:
            ev = json.loads(ln)
        except json.JSONDecodeError:
            continue
        rawf.write(ln + "\n")
        _map_event(ev, round(time.monotonic() - t0, 2), tf, counters, usage_acc)
    tf.close()
    rawf.close()
    (run_dir / "stderr.log").write_text(stderr or "", encoding="utf-8")

    wall_time_s = round(time.monotonic() - t0, 1)
    submitted_answer = read_submitted_answer(workdir)

    if timed_out:
        exit_reason = "timeout"
    elif not logged_in:
        exit_reason = "error"
    elif counters["failed"] and submitted_answer is None:
        exit_reason = "error"
    elif submitted_answer is not None:
        exit_reason = "submitted"
    else:
        exit_reason = "attempts_exhausted"

    suspect, suspect_details, pip_installs = audit_transcript(transcript_path)
    cost = _cost_usd(usage_acc, mcfg["pricing_per_mtok"])

    record = {
        "run_id": run_id, "puzzle_id": puzzle_id, "arm": "agentic",
        "model_requested": mcfg["model_id"], "model_actual": [mcfg["model_id"]],
        "model_handoff_detected": False,
        "harness": f"codex@{CODEX_VERSION}",
        "runner": "codex-exec",
        "bare_mode": True,   # API-key auth, no user config loaded
        "system_prompt_sha256": SYSTEM_APPEND_SHA256,
        "task_rules_sha256": TASK_RULES_SHA256,
        "retry_feedback_sha256": RETRY_FEEDBACK_SHA256,
        "sample_idx": sample_idx,
        "max_attempts": mcfg.get("max_attempts", 1),
        "attempts_used": 1,
        "solved_on_attempt": None,
        "correct": None,
        "grading": "pending-host",
        "first_try_correct": None,
        "attempts": [{"attempt": 1, "submitted_answer": submitted_answer,
                      "correct": None,
                      "grade_status": "ok" if submitted_answer is not None else "missing",
                      "grade_method": None,
                      "turn_subtype": counters["failed"] or "turn.completed",
                      "turn_cost_usd": cost,
                      "cumulative_num_turns": counters["turns"]}],
        "start_ts": start_ts, "wall_time_s": wall_time_s,
        "num_turns": counters["turns"],
        "tool_calls": counters["tool_calls"],
        "input_tokens": usage_acc.get("input_tokens"),
        "output_tokens": usage_acc.get("output_tokens"),
        "cache_read_tokens": usage_acc.get("cached_input_tokens"),
        "cache_creation_tokens": usage_acc.get("cache_write_input_tokens"),
        "reasoning_output_tokens": usage_acc.get("reasoning_output_tokens"),
        "cost_usd": cost,
        "cost_method": "token-usage x published pricing (Codex returns no USD)",
        # Reasoning effort is NOT overridden — Codex sends reasoning_effort=null,
        # so GPT-5.6's own default applies. Symmetric with the Claude arm, which
        # never sets --effort (Claude Code default). Recorded for transparency.
        "reasoning_effort": "default (codex model_reasoning_effort=null)",
        "exit_reason": exit_reason,
        "image_delivered": bool(images),
        "suspect_cheating": suspect,
        "suspect_details": suspect_details,
        "pip_installs": pip_installs,
        "submitted_answer": submitted_answer,
        "grade_method": None,
        "grader_needs_review": None,
        "grader_snapshot": None,
        "transcript_path": f"{CONFIG['paths']['runs']}/{run_id}/transcript.jsonl",
    }
    (run_dir / "run.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("puzzle_id")
    ap.add_argument("tier", choices=[t for t, m in MODELS.items()
                                     if m.get("harness") == "codex"])
    ap.add_argument("--sample", type=int, default=1)
    ap.add_argument("--run-id", type=str, default=None)
    args = ap.parse_args()
    rec = run_codex(args.puzzle_id, args.tier, args.sample, args.run_id)
    print(json.dumps({k: rec[k] for k in
                      ("run_id", "exit_reason", "submitted_answer", "cost_usd",
                       "num_turns", "tool_calls")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
