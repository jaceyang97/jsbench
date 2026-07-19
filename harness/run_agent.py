"""Primary runner: one puzzle x one model via the Claude Agent SDK.

Why the SDK and not headless CLI:
  1. Streaming input lets us put base64 image blocks in the first user message
     (native vision path — Claude Code's Read-tool image path is unreliable).
  2. CLI 2.1.90 dropped --max-turns; the SDK still exposes max_turns.

Reproducibility measures:
  - extra_args={"bare": None}: skip user hooks / CLAUDE.md / plugins entirely
    (the host machine has a global CLAUDE.md + command-rewriting hook that must
    NOT leak into benchmark runs).
  - system prompt = claude_code preset + fixed SYSTEM_APPEND (SHA-256 recorded)
  - full message stream persisted to transcript.jsonl

Usage (single manual run):
  .venv/Scripts/python -m harness.run_agent 2026-02-subtiles-2 haiku [--sample 1]
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import dataclasses
import json
import mimetypes
import re
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from grading.grade import grade_submission  # noqa: E402
from harness.prompts import (  # noqa: E402
    SYSTEM_APPEND, SYSTEM_APPEND_SHA256, TASK_RULES_SHA256, render_task,
)

CONFIG = yaml.safe_load((ROOT / "config" / "bench.yaml").read_text(encoding="utf-8"))
MODELS = {m["tier"]: m for m in
          json.loads((ROOT / "config" / "models.json").read_text(encoding="utf-8"))["models"]}
PUZZLES_DIR = ROOT / CONFIG["paths"]["puzzles"]
RUNS_DIR = ROOT / CONFIG["paths"]["runs"]

ALLOWED_TOOLS = ["Bash", "Read", "Write", "Edit", "Glob", "Grep"]
DISALLOWED_TOOLS = ["WebSearch", "WebFetch"]

# patterns in *tool inputs* that suggest attempted lookup / exfiltration.
# pip installs are ALLOWED (PyPI is on the proxy allowlist) and are recorded
# separately; everything else network-shaped gets flagged for human review.
_SUSPECT_RE = re.compile(
    r"janestreet\.com|github\.com|youtube\.com|google\.com|stackoverflow\.com"
    r"|curl\s+http|wget\s+http|Invoke-WebRequest|urllib\.request"
    r"|requests\.get|http\.client|socket\.connect"
    r"|api\.anthropic\.com|web_search|web_fetch", re.I)
_SUSPECT_TOOLS = {"WebSearch", "WebFetch"}
_PIP_RE = re.compile(r"pip3?\s+install\s+([^\n;&|]+)")


def audit_transcript(transcript_path: Path) -> tuple[bool, list[str], list[str]]:
    """Return (suspect, suspect_details, pip_installs) from actual tool calls."""
    suspect_details: list[str] = []
    pip_installs: list[str] = []
    try:
        for line in transcript_path.read_text(encoding="utf-8", errors="replace").splitlines():
            rec = json.loads(line)
            if rec.get("kind") != "AssistantMessage":
                continue
            for block in (rec.get("data", {}).get("content") or []):
                if not isinstance(block, dict) or "name" not in block:
                    continue
                blob = json.dumps(block.get("input", ""))
                for m in _PIP_RE.finditer(blob):
                    pkgs = m.group(1).strip()
                    if pkgs not in pip_installs:
                        pip_installs.append(pkgs)
                if block.get("name") in _SUSPECT_TOOLS:
                    suspect_details.append(f"tool:{block['name']}")
                    continue
                m = _SUSPECT_RE.search(_PIP_RE.sub("", blob))
                if m:
                    suspect_details.append(f"{block.get('name')}:{m.group(0)}")
    except Exception as exc:
        return True, [f"transcript-unreadable:{exc!r}"], pip_installs
    return bool(suspect_details), suspect_details[:20], pip_installs


def _jsonable(obj):
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _jsonable(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return repr(obj)


def build_workdir(puzzle_id: str, run_dir: Path) -> Path:
    """Copy the task bundle into an isolated workdir with an empty output/."""
    src = PUZZLES_DIR / puzzle_id
    workdir = run_dir / "workdir"
    shutil.copytree(src, workdir)
    (workdir / "output").mkdir()
    return workdir


def snapshot_answer(workdir: Path) -> str | None:
    """Read output/answer.json's answer field, or None."""
    p = workdir / "output" / "answer.json"
    if not p.exists():
        return None
    try:
        return str(json.loads(p.read_text(encoding="utf-8")).get("answer"))
    except Exception:
        return None


def image_blocks(workdir: Path) -> list[dict]:
    blocks = []
    img_dir = workdir / "images"
    if img_dir.exists():
        for f in sorted(img_dir.iterdir()):
            mime = mimetypes.guess_type(f.name)[0] or "image/jpeg"
            blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": mime,
                           "data": base64.standard_b64encode(f.read_bytes()).decode()},
            })
    return blocks


async def run_agent(puzzle_id: str, tier: str, sample_idx: int = 1,
                    run_id: str | None = None,
                    timeout_s: int | None = None) -> dict:
    """One persistent session per (puzzle, model): the agent gets up to N
    feedback-guided attempts. After each WRONG submission we send only the
    fact that it was wrong (harness/prompts.RETRY_FEEDBACK) and the agent
    continues from its own work in the SAME session. The session ends on the
    first correct answer, or when N attempts / turn / budget / wall-clock caps
    are hit. Grading happens off-band; a correct verdict is the only thing that
    ends the session early, and the agent is never told it was right."""
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
    from claude_agent_sdk.types import ResultMessage
    from harness.prompts import render_retry, RETRY_FEEDBACK_SHA256

    mcfg = MODELS[tier]
    run_id = run_id or f"{puzzle_id}_{tier}_s{sample_idx}_{uuid.uuid4().hex[:8]}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    workdir = build_workdir(puzzle_id, run_dir)

    meta = json.loads((workdir / "metadata.json").read_text(encoding="utf-8"))
    problem_md = (workdir / "problem.md").read_text(encoding="utf-8")
    imgs = image_blocks(workdir)

    task_text = render_task(problem_md, meta["answer_format"], meta["date"], bool(imgs))
    content: list[dict] = imgs + [{"type": "text", "text": task_text}]

    import os
    # --bare requires ANTHROPIC_API_KEY (OAuth is never read in bare mode).
    # Official runs MUST use bare + API key. Plumbing smoke tests without a key
    # fall back to OAuth with setting_sources=[] (still isolates user hooks /
    # CLAUDE.md, but is NOT valid for scored runs — flagged in the record).
    bare_ok = bool(os.environ.get("ANTHROPIC_API_KEY"))
    extra_args = {"bare": None} if bare_ok else {}
    options = ClaudeAgentOptions(
        model=mcfg["model_id"],
        cwd=str(workdir),
        max_turns=mcfg["max_turns"],
        max_budget_usd=mcfg["max_budget_usd"],
        allowed_tools=ALLOWED_TOOLS,
        disallowed_tools=DISALLOWED_TOOLS,
        permission_mode="bypassPermissions",
        system_prompt={"type": "preset", "preset": "claude_code",
                       "append": SYSTEM_APPEND},
        extra_args=extra_args,
        setting_sources=[],
        env={
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "DISABLE_AUTOUPDATER": "1",
            "PYTHONIOENCODING": "utf-8",
            "CLAUDE_CODE_GIT_BASH_PATH": r"A:\Git\bin\bash.exe",
        },
    )

    # ---- full-fidelity logging: exact first message + resolved options ----
    import importlib.metadata
    sdk_version = importlib.metadata.version("claude-agent-sdk")
    initial_log = {
        "text_blocks": [b["text"] for b in content if b.get("type") == "text"],
        "image_blocks": [{"media_type": b["source"]["media_type"],
                          "bytes_b64": len(b["source"]["data"]),
                          "sha256_of_b64": __import__("hashlib").sha256(
                              b["source"]["data"].encode()).hexdigest()}
                         for b in content if b.get("type") == "image"],
        "block_order": [b.get("type") for b in content],
    }
    (run_dir / "initial_message.json").write_text(
        json.dumps(initial_log, ensure_ascii=False, indent=2), encoding="utf-8")
    options_log = {
        "model": mcfg["model_id"], "max_turns": mcfg["max_turns"],
        "max_budget_usd": mcfg["max_budget_usd"],
        "allowed_tools": ALLOWED_TOOLS, "disallowed_tools": DISALLOWED_TOOLS,
        "permission_mode": "bypassPermissions",
        "system_prompt": {"preset": "claude_code", "append": SYSTEM_APPEND},
        "bare_mode": bare_ok, "setting_sources": [],
        "env_non_secret": {k: v for k, v in options.env.items()
                           if "KEY" not in k and "TOKEN" not in k},
        "sdk_version": sdk_version,
        "harness_claude_code_version": CONFIG["harness"]["claude_code_version"],
        "wall_clock_timeout_s": timeout_s or CONFIG["wall_clock_timeout_s"],
    }
    (run_dir / "options.json").write_text(
        json.dumps(options_log, ensure_ascii=False, indent=2), encoding="utf-8")

    options_log["max_attempts"] = mcfg["max_attempts"]
    options_log["retry_feedback_sha256"] = RETRY_FEEDBACK_SHA256
    (run_dir / "options.json").write_text(
        json.dumps(options_log, ensure_ascii=False, indent=2), encoding="utf-8")

    stderr_path = run_dir / "stderr.log"
    stderr_fh = stderr_path.open("a", encoding="utf-8")
    options.stderr = lambda line: (stderr_fh.write(line + "\n"), stderr_fh.flush())

    async def first_message():
        yield {"type": "user",
               "message": {"role": "user", "content": content},
               "parent_tool_use_id": None,
               "session_id": "default"}

    start_ts = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()
    transcript_path = run_dir / "transcript.jsonl"
    tf = transcript_path.open("a", encoding="utf-8")

    max_attempts = mcfg["max_attempts"]
    attempts: list[dict] = []          # per-attempt record
    results: list = []                 # ResultMessage per attempt turn
    tool_calls = 0
    solved_on_attempt: int | None = None
    exit_reason = "error"
    timed_out = False
    last_result = None

    def log_msg(msg, attempt):
        nonlocal tool_calls, last_result
        rec = {"t": round(time.monotonic() - t0, 2), "attempt": attempt,
               "kind": type(msg).__name__, "data": _jsonable(msg)}
        tf.write(json.dumps(rec, ensure_ascii=False) + "\n")
        tf.flush()
        if type(msg).__name__ == "AssistantMessage":
            for block in getattr(msg, "content", []) or []:
                if type(block).__name__ == "ToolUseBlock":
                    tool_calls += 1
        if isinstance(msg, ResultMessage):
            last_result = msg

    try:
        async with asyncio.timeout(timeout_s or CONFIG["wall_clock_timeout_s"]):
            async with ClaudeSDKClient(options=options) as client:
                for attempt in range(1, max_attempts + 1):
                    prompt = first_message() if attempt == 1 else render_retry(
                        attempts[-1]["submitted_answer"] or "(no answer written)")
                    await client.query(prompt)
                    turn_result = None
                    async for msg in client.receive_response():
                        log_msg(msg, attempt)
                        if isinstance(msg, ResultMessage):
                            turn_result = msg
                    results.append(turn_result)

                    # grade this attempt off-band (agent never sees the verdict)
                    grade = grade_submission(puzzle_id, workdir)
                    attempts.append({
                        "attempt": attempt,
                        "submitted_answer": grade["submitted_answer"],
                        "correct": grade["correct"],
                        "grade_status": grade["grade_status"],
                        "grade_method": grade["grade_method"],
                        "turn_subtype": getattr(turn_result, "subtype", None),
                        "turn_cost_usd": getattr(turn_result, "total_cost_usd", None),
                        "cumulative_num_turns": getattr(turn_result, "num_turns", None),
                    })
                    if grade["correct"]:
                        solved_on_attempt = attempt
                        break
                    # if the turn itself hit a hard cap, stop retrying
                    st = getattr(turn_result, "subtype", "") or ""
                    if turn_result is None or "max_turns" in st or "budget" in st:
                        break
    except TimeoutError:
        timed_out = True
        tf.write(json.dumps({"kind": "harness_timeout"}) + "\n")
    except Exception as exc:
        tf.write(json.dumps({"kind": "harness_error", "error": repr(exc)}) + "\n")
    finally:
        tf.close()
        stderr_fh.close()

    wall_time_s = round(time.monotonic() - t0, 1)
    final_grade = grade_submission(puzzle_id, workdir)
    correct = solved_on_attempt is not None
    attempts_used = len(attempts)

    # --- exit reason
    last = last_result
    last_subtype = getattr(last, "subtype", None)
    if correct:
        exit_reason = "solved"
    elif timed_out:
        exit_reason = "timeout"
    elif last is None:
        exit_reason = "error"
    elif attempts_used >= max_attempts:
        # single-attempt mode (the literature-standard default): a graded-wrong
        # submission is just "submitted"; only multi-attempt sessions report
        # attempts_exhausted
        exit_reason = ("submitted" if max_attempts == 1 and
                       attempts and attempts[-1]["grade_status"] == "ok"
                       else "attempts_exhausted")
    elif last_subtype == "error_max_turns":
        exit_reason = "max_turns"
    elif "budget" in (last_subtype or ""):
        exit_reason = "max_budget"
    else:
        exit_reason = last_subtype or "no_answer"

    # --- model handoff detection (Fable safety classifier -> Opus)
    model_actual = sorted((last.model_usage or {}).keys()) if last else []
    handoff = any(mcfg["model_id"] not in m and m for m in model_actual) if model_actual else False

    # --- cheating audit (actual tool calls only)
    suspect, suspect_details, pip_installs = audit_transcript(transcript_path)

    # session-cumulative usage/cost come from the LAST ResultMessage
    usage = (last.usage or {}) if last else {}
    record = {
        "run_id": run_id, "puzzle_id": puzzle_id, "arm": "agentic",
        "model_requested": mcfg["model_id"], "model_actual": model_actual,
        "model_handoff_detected": handoff,
        "harness": f"claude-code@{CONFIG['harness']['claude_code_version']}",
        "runner": "sdk-session",
        "bare_mode": bare_ok,
        "system_prompt_sha256": SYSTEM_APPEND_SHA256,
        "task_rules_sha256": TASK_RULES_SHA256,
        "retry_feedback_sha256": RETRY_FEEDBACK_SHA256,
        "sample_idx": sample_idx,
        "max_attempts": max_attempts,
        "attempts_used": attempts_used,
        "solved_on_attempt": solved_on_attempt,     # 1..N or None
        "correct": correct,                          # solved within N attempts
        "first_try_correct": bool(attempts and attempts[0]["correct"]),
        "attempts": attempts,                        # full per-attempt trail
        "start_ts": start_ts, "wall_time_s": wall_time_s,
        "num_turns": sum((a.get("cumulative_num_turns") or 0) for a in attempts),
        "tool_calls": tool_calls,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cache_read_tokens": usage.get("cache_read_input_tokens"),
        "cache_creation_tokens": usage.get("cache_creation_input_tokens"),
        "cost_usd": getattr(last, "total_cost_usd", None),   # cumulative session cost
        "exit_reason": exit_reason,
        "image_delivered": bool(imgs),
        "suspect_cheating": suspect,
        "suspect_details": suspect_details,
        "pip_installs": pip_installs,
        "submitted_answer": final_grade["submitted_answer"],
        "grade_method": final_grade["grade_method"],
        "grader_needs_review": final_grade["grader_needs_review"],
        "grader_snapshot": {
            k: v for k, v in json.loads(
                (ROOT / "data" / "graders" / f"{puzzle_id}.json")
                .read_text(encoding="utf-8")).items()
            if k in ("answer", "answer_type", "tolerance", "aliases", "verifier",
                     "grading_mode")
        },
        "transcript_path": str(transcript_path.relative_to(ROOT)),
    }
    (run_dir / "run.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("puzzle_id")
    ap.add_argument("tier", choices=list(MODELS.keys()))
    ap.add_argument("--sample", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=None)
    ap.add_argument("--run-id", type=str, default=None,
                    help="explicit run id (used by the containerized orchestrator)")
    args = ap.parse_args()
    record = asyncio.run(run_agent(args.puzzle_id, args.tier, args.sample,
                                   run_id=args.run_id, timeout_s=args.timeout))
    print(json.dumps(record, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
