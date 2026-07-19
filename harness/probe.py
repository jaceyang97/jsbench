"""Memorization probe: zero-tool, answer-only, straight Messages API.

Per puzzle x model: send problem text + images, ask for the bare answer with
no reasoning. A correct probe answer strongly suggests the answer is memorized
from training data -> memorization_suspect=true, used for sensitivity analysis.

Model quirks (verified against claude-api skill 2026-07-19):
  - fable-5: thinking always on, cannot be disabled; sampling params rejected.
    Cost control: effort=low + small max_tokens. Thinking still burns tokens,
    so fable probes cost slightly more than the others. There is no way to
    fully suppress reasoning on fable-5 — record this caveat with results.
  - opus-4-8 / sonnet-5: thinking={"type":"disabled"} accepted.
  - haiku-4-5: extended-thinking model; omit `thinking` entirely = off.

Usage:
  .venv/Scripts/python -m harness.probe --puzzles 2026-02-subtiles-2 --tiers haiku
  .venv/Scripts/python -m harness.probe            # all packaged puzzles x all tiers
Appends one JSON line per probe to runs/probes.jsonl (idempotent: skips done).
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from grading.normalize import normalize_and_compare  # noqa: E402
from harness.run_agent import CONFIG, MODELS, PUZZLES_DIR  # noqa: E402

PROBES_PATH = ROOT / CONFIG["paths"]["runs"] / "probes.jsonl"

PROBE_PROMPT = """\
This is a Jane Street monthly puzzle ({date}), titled "{title}".

{problem}

Do not reason step by step. Do not write code. If you already know the final \
answer to this puzzle, output the answer alone in its simplest form and \
nothing else. If you do not know, output exactly: UNKNOWN"""


def probe_one(client, puzzle_id: str, tier: str) -> dict:
    mcfg = MODELS[tier]
    pdir = PUZZLES_DIR / puzzle_id
    meta = json.loads((pdir / "metadata.json").read_text(encoding="utf-8"))
    problem = (pdir / "problem.md").read_text(encoding="utf-8")

    content = []
    img_dir = pdir / "images"
    if img_dir.exists():
        for f in sorted(img_dir.iterdir()):
            mime = mimetypes.guess_type(f.name)[0] or "image/jpeg"
            content.append({"type": "image",
                            "source": {"type": "base64", "media_type": mime,
                                       "data": base64.standard_b64encode(f.read_bytes()).decode()}})
    content.append({"type": "text", "text": PROBE_PROMPT.format(
        date=meta["date"], title=meta["title"], problem=problem)})

    kwargs = dict(model=mcfg["model_id"], max_tokens=200,
                  messages=[{"role": "user", "content": content}])
    if tier == "fable":
        kwargs["output_config"] = {"effort": "low"}   # thinking can't be disabled
        kwargs["max_tokens"] = 4000                    # room for forced thinking
    elif tier in ("opus", "sonnet"):
        kwargs["thinking"] = {"type": "disabled"}
    # haiku: omit thinking entirely = off

    resp = client.messages.create(**kwargs)
    text = next((b.text for b in resp.content if b.type == "text"), "").strip()

    grader = json.loads((ROOT / "data" / "graders" / f"{puzzle_id}.json")
                        .read_text(encoding="utf-8"))
    said_unknown = text.strip().upper() == "UNKNOWN"
    correct = False
    if not said_unknown and text:
        correct, _ = normalize_and_compare(text, grader["answer"], grader)

    return {
        "arm": "probe", "puzzle_id": puzzle_id, "tier": tier,
        "model": mcfg["model_id"],
        "model_actual": resp.model,
        "stop_reason": resp.stop_reason,
        "ts": datetime.now(timezone.utc).isoformat(),
        "response_text": text[:500],
        "said_unknown": said_unknown,
        "probe_correct": correct,
        "memorization_suspect": correct,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
    }


def main() -> None:
    import anthropic
    ap = argparse.ArgumentParser()
    ap.add_argument("--puzzles", type=str, default=None, help="comma-separated ids")
    ap.add_argument("--tiers", type=str, default=None, help="comma-separated tiers")
    args = ap.parse_args()

    puzzles = (args.puzzles.split(",") if args.puzzles
               else sorted(p.name for p in PUZZLES_DIR.iterdir() if p.is_dir()))
    tiers = args.tiers.split(",") if args.tiers else list(MODELS.keys())

    done = set()
    if PROBES_PATH.exists():
        for line in PROBES_PATH.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            done.add((r["puzzle_id"], r["tier"]))

    client = anthropic.Anthropic()
    PROBES_PATH.parent.mkdir(exist_ok=True)
    with PROBES_PATH.open("a", encoding="utf-8") as f:
        for pid in puzzles:
            for tier in tiers:
                if (pid, tier) in done:
                    continue
                try:
                    rec = probe_one(client, pid, tier)
                except Exception as exc:
                    rec = {"arm": "probe", "puzzle_id": pid, "tier": tier,
                           "error": repr(exc),
                           "ts": datetime.now(timezone.utc).isoformat()}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                status = rec.get("error") or ("MEMORIZED?" if rec.get("probe_correct")
                                              else ("unknown" if rec.get("said_unknown") else "wrong"))
                print(f"{pid} x {tier}: {status}")


if __name__ == "__main__":
    main()
