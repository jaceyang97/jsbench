"""Phase-0 gate: image delivery smoke test.

For every image in every packaged puzzle x every model tier: send the image
via Messages API with 'describe this image' and record the description.
A human (or the orchestrating session) checks each description actually
matches the image content (grids, sizes, labels).

Requires ANTHROPIC_API_KEY. Appends to runs/image_smoke.jsonl (idempotent).

Usage: .venv/Scripts/python -m harness.image_smoke [--tiers haiku,sonnet]
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

from harness.run_agent import MODELS, PUZZLES_DIR  # noqa: E402

OUT = ROOT / "runs" / "image_smoke.jsonl"


def main() -> None:
    import anthropic
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiers", type=str, default=None)
    ap.add_argument("--puzzles", type=str, default=None)
    args = ap.parse_args()
    tiers = args.tiers.split(",") if args.tiers else list(MODELS.keys())
    puzzles = (args.puzzles.split(",") if args.puzzles
               else sorted(p.name for p in PUZZLES_DIR.iterdir() if p.is_dir()))

    done = set()
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            done.add((r["puzzle_id"], r["image"], r["tier"]))

    client = anthropic.Anthropic()
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("a", encoding="utf-8") as f:
        for pid in puzzles:
            img_dir = PUZZLES_DIR / pid / "images"
            if not img_dir.exists():
                continue
            for img in sorted(img_dir.iterdir()):
                for tier in tiers:
                    if (pid, img.name, tier) in done:
                        continue
                    mime = mimetypes.guess_type(img.name)[0] or "image/jpeg"
                    kwargs = dict(
                        model=MODELS[tier]["model_id"], max_tokens=2000,
                        messages=[{"role": "user", "content": [
                            {"type": "image", "source": {
                                "type": "base64", "media_type": mime,
                                "data": base64.standard_b64encode(img.read_bytes()).decode()}},
                            {"type": "text",
                             "text": "Describe this image precisely: what kind of "
                                     "diagram/grid is it, its dimensions, and any "
                                     "numbers or labels you can read."}]}])
                    if tier in ("opus", "sonnet"):
                        kwargs["thinking"] = {"type": "disabled"}
                    try:
                        resp = client.messages.create(**kwargs)
                        text = next((b.text for b in resp.content if b.type == "text"), "")
                        rec = {"puzzle_id": pid, "image": img.name, "tier": tier,
                               "ts": datetime.now(timezone.utc).isoformat(),
                               "description": text[:1500], "ok": bool(text.strip())}
                    except Exception as exc:
                        rec = {"puzzle_id": pid, "image": img.name, "tier": tier,
                               "ts": datetime.now(timezone.utc).isoformat(),
                               "error": repr(exc), "ok": False}
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    f.flush()
                    print(f"{pid}/{img.name} x {tier}: {'ok' if rec.get('ok') else 'FAIL'}")


if __name__ == "__main__":
    main()
