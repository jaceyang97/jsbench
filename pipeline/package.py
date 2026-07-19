"""Build agent-visible task bundles and off-band graders from extractions.

Reads  data/raw/puzzles/{bench_id}/   (meta.json, extracted.json, images/)
Writes data/puzzles/{bench_id}/problem.md
       data/puzzles/{bench_id}/images/*
       data/puzzles/{bench_id}/metadata.json      # NO answer material
       data/graders/{bench_id}.json               # answer + normalization rules
       data/puzzles_index.json                    # off-band study metadata

Answer isolation invariant: nothing under data/puzzles/ may contain the
answer, the solution text, or solver names. validate.py enforces this.

Solver difficulty signals (off-band index only):
  solver_count_raw          raw leaderboard count (None pre-Nov-2015)
  solver_percentile_in_year rank percentile within the same calendar year
"""
from __future__ import annotations

import argparse
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone

from loguru import logger

from .common import GRADERS_DIR, PUZZLES_DIR, RAW_DIR, ROOT, read_json, write_json


def package_one(pid: str) -> dict | None:
    pdir = RAW_DIR / "puzzles" / pid
    ext_path = pdir / "extracted.json"
    if not ext_path.exists():
        logger.warning(f"{pid}: not extracted yet")
        return None
    ext = read_json(ext_path)
    meta = read_json(pdir / "meta.json")

    out_dir = PUZZLES_DIR / pid
    out_dir.mkdir(parents=True, exist_ok=True)

    # problem.md — original wording, images referenced relatively.
    # Scrub any janestreet token (submission emails, literal URLs): the bench
    # supplies its own submission protocol and the source site must not leak.
    import re as _re
    problem_body = _re.sub(r"\S*janestreet\S*", "[removed]", ext["problem_md"],
                           flags=_re.I)
    if len(problem_body.strip()) < 40 and meta.get("images"):
        note = ("*(The full problem statement is contained in the attached "
                "image(s) — see the `images/` directory.)*")
        problem_body = f"{problem_body}\n\n{note}".strip()
    (out_dir / "problem.md").write_text(
        f"# {ext['title']}\n\n{problem_body}\n", encoding="utf-8")

    # images
    images_meta = []
    if meta.get("images"):
        (out_dir / "images").mkdir(exist_ok=True)
        for im in meta["images"]:
            src = pdir / "images" / im["file"]
            if src.exists():
                shutil.copy2(src, out_dir / "images" / im["file"])
                # NOTE: no source_url here — agent-visible metadata must not
                # reveal janestreet.com URLs (invites lookups, trips the audit)
                images_meta.append({"file": f"images/{im['file']}",
                                    "sha256": im["sha256"]})

    # off-band grader — NEVER clobber a human-reviewed grader
    cands = ext["answer_candidates"]
    gpath = GRADERS_DIR / f"{pid}.json"
    existing_grader = read_json(gpath) if gpath.exists() else None
    if existing_grader and not existing_grader.get("needs_review", True):
        grader = existing_grader          # reviewed: keep as-is
    else:
        grader = {
            "puzzle_id": pid,
            "answer": cands[0] if cands else None,
            "answer_type": ext["answer_format_guess"],
            "tolerance": {"type": "exact"} if ext["answer_format_guess"] != "decimal"
                         else {"type": "rel", "eps": 1e-6},
            "aliases": [],
            "answer_candidates": cands,   # for the human review pass
            "needs_review": True,
            "source_solution_url": meta["solution_url"],
        }
        # human-set flags survive regeneration even pre-review
        if existing_grader:
            for key in ("answer_in_problem_ok", "exclude_recommended",
                        "review_note", "public_answer_format"):
                if key in existing_grader:
                    grader[key] = existing_grader[key]
        write_json(gpath, grader)

    # agent-visible metadata (no answers). answer_format comes from the
    # reviewed grader's public_answer_format when available.
    date = pid[:7]
    answer_format = (grader.get("public_answer_format")
                     or ext["answer_format_guess"])
    metadata = {
        "puzzle_id": pid,
        "date": date,
        "title": ext["title"],
        "has_image": bool(images_meta),
        "answer_format": answer_format,
        "images": images_meta,
    }
    write_json(out_dir / "metadata.json", metadata)

    return {
        "puzzle_id": pid, "date": date, "title": ext["title"],
        "slug": meta["slug"], "has_image": bool(images_meta),
        "answer_format": answer_format,
        "solver_count_raw": meta.get("solver_count_raw"),
        "solver_list_available": meta.get("solver_list_available", False),
        "source_urls": {"puzzle": meta["index_url"], "solution": meta["solution_url"]},
        "scrape_date": meta.get("scraped_at"),
    }


def add_solver_percentiles(index: list[dict]) -> None:
    """solver_percentile_in_year: rank of solver_count within same calendar year.

    Non-parametric within-year percentile; cancels the year-over-year growth
    in participation. 100 = most-solved (easiest proxy) that year.
    """
    by_year: dict[str, list[dict]] = defaultdict(list)
    for e in index:
        if e["solver_count_raw"] is not None:
            by_year[e["date"][:4]].append(e)
    for year, entries in by_year.items():
        counts = sorted(e["solver_count_raw"] for e in entries)
        n = len(counts)
        for e in entries:
            if n == 1:
                e["solver_percentile_in_year"] = 50.0
            else:
                rank = counts.index(e["solver_count_raw"])
                e["solver_percentile_in_year"] = round(100.0 * rank / (n - 1), 1)
    for e in index:
        e.setdefault("solver_percentile_in_year", None)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=str, default=None)
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else None

    pids = sorted(p.name for p in (RAW_DIR / "puzzles").iterdir() if p.is_dir())
    index = []
    for pid in pids:
        if only and pid not in only:
            continue
        entry = package_one(pid)
        if entry:
            index.append(entry)
            logger.info(f"{pid}: packaged")

    # merge with existing index (partial runs shouldn't drop other entries)
    idx_path = ROOT / "data" / "puzzles_index.json"
    if idx_path.exists():
        existing = {e["puzzle_id"]: e for e in read_json(idx_path)}
        for e in index:
            existing[e["puzzle_id"]] = e
        index = sorted(existing.values(), key=lambda e: e["puzzle_id"])
    add_solver_percentiles(index)
    write_json(idx_path, index)
    logger.info(f"index: {len(index)} puzzles -> {idx_path}")


if __name__ == "__main__":
    sys.exit(main())
