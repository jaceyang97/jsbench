"""Compact summary of a run's transcript.jsonl for fable trace-check.

Full transcripts range from ~20 KB to ~40 MB (median ~22 KB, p99 ~12 MB); the
back-fill / write-up phase asks fable to categorise the run's behavior by
Schoenfeld episode (Read/Analyze/Explore/Plan/Implement/Verify), tag its
self-verification form, and, on runs that never submitted, judge whether the
answer was stated in-turn. Feeding full transcripts is wasteful for the
common case and impossible for the fat tail. This module reduces a transcript
to a linear, textually tractable summary that preserves the ordering and
content of tool calls and assistant utterances while trimming their volume.

Transcript event schema (jsbench harness, both Claude and Codex arms):
  {"t": <secs>, "attempt": N, "kind": <str>, "data": {...}}
where kind is one of SystemMessage / AssistantMessage / UserMessage /
ResultMessage. AssistantMessage.data.content is a list of blocks; each block
is a dict with either
  - {"type": "text", "text": ...}
  - {"type": "tool_use", "name": <tool>, "input": {...}}
  - {"thinking": ..., "signature": ...}  (no "type" key; identified by
    presence of "thinking")
UserMessage.data.content is a list of tool_result blocks:
  - {"tool_use_id": ..., "content": <str|list>, "is_error": bool}
"""
from __future__ import annotations

import json
from pathlib import Path


def _truncate(s: str, head: int = 800, tail: int = 200) -> str:
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    if len(s) <= head + tail + 40:
        return s
    return f"{s[:head]}\n... [truncated {len(s) - head - tail} chars] ...\n{s[-tail:]}"


def _tool_result_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for b in content:
            if isinstance(b, dict):
                if b.get("type") == "text":
                    out.append(b.get("text", ""))
                elif "text" in b:
                    out.append(b["text"])
        return "\n".join(out)
    return str(content)


def summarize_transcript(path: Path | str, max_events: int = 400) -> dict:
    p = Path(path)
    events: list[dict] = []
    total_events = 0
    tool_calls = 0
    assistant_texts = 0
    thinking_blocks = 0
    tool_results = 0
    result_meta = None
    with p.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            total_events += 1
            try:
                rec = json.loads(line)
            except Exception:
                continue
            kind = rec.get("kind")
            data = rec.get("data") or {}
            if not isinstance(data, dict):
                continue
            if kind == "AssistantMessage":
                content = data.get("content") or []
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if "thinking" in block:
                        thinking_blocks += 1
                        if len(events) < max_events:
                            events.append({
                                "step": len(events), "kind": "thinking",
                                "text": f"[thinking block, ~{len(block.get('thinking',''))} chars]",
                            })
                        continue
                    btype = block.get("type")
                    if btype == "text":
                        assistant_texts += 1
                        if len(events) < max_events:
                            events.append({
                                "step": len(events), "kind": "assistant_text",
                                "text": _truncate(block.get("text", "")),
                            })
                    elif btype == "tool_use" or "name" in block:
                        tool_calls += 1
                        if len(events) < max_events:
                            inp = block.get("input") or {}
                            events.append({
                                "step": len(events), "kind": "tool_call",
                                "tool_name": block.get("name"),
                                "text": _truncate(json.dumps(inp, ensure_ascii=False)),
                            })
            elif kind == "UserMessage":
                content = data.get("content") or []
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if "tool_use_id" in block or block.get("type") == "tool_result":
                        tool_results += 1
                        out_text = _tool_result_text(block.get("content"))
                        if len(events) < max_events:
                            events.append({
                                "step": len(events), "kind": "tool_result",
                                "text": _truncate(out_text, head=1200, tail=200),
                                "is_error": bool(block.get("is_error")),
                            })
            elif kind == "ResultMessage":
                result_meta = {
                    "subtype": data.get("subtype"),
                    "stop_reason": data.get("stop_reason"),
                    "total_cost_usd": data.get("total_cost_usd"),
                    "num_turns": data.get("num_turns"),
                }
    return {
        "transcript_path": str(p),
        "total_events_in_file": total_events,
        "events_captured": len(events),
        "counts": {
            "tool_calls_total": tool_calls,
            "assistant_texts_total": assistant_texts,
            "thinking_blocks_total": thinking_blocks,
            "tool_results_total": tool_results,
        },
        "result_meta": result_meta,
        "events": events,
    }


if __name__ == "__main__":
    import sys
    out = summarize_transcript(sys.argv[1])
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
