"""Generate a human-review sheet for grader answers.

Produces data/review_sheet.md: per puzzle — current grader answer, all
candidates, the opening of the official solution, and the source URL.
A reviewer edits data/graders/{id}.json directly (set "answer", optionally
"answer_type"/"tolerance"/"aliases") and flips "needs_review": false.

Usage: python -m pipeline.review [--only id1,id2]
"""
from __future__ import annotations

import argparse

from loguru import logger

from .common import GRADERS_DIR, RAW_DIR, ROOT, read_json


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=str, default=None)
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else None

    lines = ["# Grader answer review sheet", "",
             "Edit `data/graders/<id>.json` -> set `answer`, then `needs_review: false`.", ""]
    for gpath in sorted(GRADERS_DIR.glob("*.json")):
        pid = gpath.stem
        if only and pid not in only:
            continue
        g = read_json(gpath)
        ext = read_json(RAW_DIR / "puzzles" / pid / "extracted.json")
        sol_head = "\n\n".join(
            p for p in ext["solution_md"].split("\n\n") if p.strip())[:900]
        status = "NEEDS REVIEW" if g.get("needs_review") else "reviewed"
        lines += [
            f"## {pid}  [{status}]",
            f"- current answer: `{g['answer']}`  (type: {g['answer_type']})",
            f"- candidates: {', '.join('`%s`' % c for c in g.get('answer_candidates', []))}",
            f"- solution: {g['source_solution_url']}",
            "", "> " + sol_head.replace("\n", "\n> "), "",
        ]
    out = ROOT / "data" / "review_sheet.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"review sheet -> {out}")


if __name__ == "__main__":
    main()
