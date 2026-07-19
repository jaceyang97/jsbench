"""Integrity checks over packaged puzzles and graders.

Checks:
  1. every packaged puzzle has problem.md with substance
  2. has_image=true  =>  images/ non-empty; image files match recorded sha256
  3. grader exists, has an answer, and survives its own normalization round-trip
  4. answer isolation: answer string and solution text never appear inside the
     agent-visible bundle
  5. metadata completeness

Exit code 1 if any ERROR (warnings don't fail).

Usage: python -m pipeline.validate [--only id1,id2] [--strict-review]
  --strict-review also fails on graders with needs_review=true
  (run before Phase 1; Phase 0 tolerates unreviewed answers)
"""
from __future__ import annotations

import argparse
import sys

from loguru import logger

from .common import GRADERS_DIR, PUZZLES_DIR, read_json, sha256_bytes

sys.path.insert(0, str(PUZZLES_DIR.parent.parent))
from grading.normalize import normalize_and_compare  # noqa: E402


def validate_one(pid: str, strict_review: bool) -> list[str]:
    errors: list[str] = []
    pdir = PUZZLES_DIR / pid

    # 1. problem.md
    prob = pdir / "problem.md"
    if not prob.exists():
        return [f"{pid}: problem.md missing"]
    text = prob.read_text(encoding="utf-8")
    meta_probe = read_json(pdir / "metadata.json") if (pdir / "metadata.json").exists() else {}
    gpath_pre = GRADERS_DIR / f"{pid}.json"
    grader_pre = read_json(gpath_pre) if gpath_pre.exists() else {}
    if (len(text) < 80 and not meta_probe.get("has_image")
            and not grader_pre.get("exclude_recommended")):
        errors.append(f"{pid}: problem.md suspiciously short ({len(text)} ch) and no image")

    # 5. metadata
    meta_path = pdir / "metadata.json"
    if not meta_path.exists():
        return errors + [f"{pid}: metadata.json missing"]
    meta = read_json(meta_path)
    for key in ("puzzle_id", "date", "title", "has_image", "answer_format"):
        if key not in meta:
            errors.append(f"{pid}: metadata missing key {key}")

    # 2. images
    if meta.get("has_image"):
        imgs = list((pdir / "images").glob("*")) if (pdir / "images").exists() else []
        if not imgs:
            errors.append(f"{pid}: has_image=true but images/ empty")
        recorded = {im["file"].split("/")[-1]: im["sha256"] for im in meta.get("images", [])}
        for f in imgs:
            if f.name in recorded and sha256_bytes(f.read_bytes()) != recorded[f.name]:
                errors.append(f"{pid}: sha256 mismatch for {f.name}")

    # 3. grader + round-trip
    gpath = GRADERS_DIR / f"{pid}.json"
    if not gpath.exists():
        return errors + [f"{pid}: grader missing"]
    grader = read_json(gpath)
    ans = grader.get("answer")
    if not ans:
        if grader.get("needs_review"):
            logger.warning(f"{pid}: grader has no answer yet (unreviewed)")
        else:
            errors.append(f"{pid}: grader has no answer")
    elif grader.get("verifier"):
        from grading.verifiers import REGISTRY
        if grader["verifier"] not in REGISTRY:
            errors.append(f"{pid}: verifier '{grader['verifier']}' not registered")
    else:
        ok, why = normalize_and_compare(ans, ans, grader)
        if not ok:
            errors.append(f"{pid}: grader round-trip failed ({why})")
    if strict_review and grader.get("needs_review"):
        errors.append(f"{pid}: grader needs_review=true (run pipeline.review)")

    # 4. answer isolation — scan EVERY file in the agent-visible bundle
    bundle_files = [p for p in pdir.rglob("*") if p.is_file()]
    for f in bundle_files:
        rel = f.relative_to(pdir).as_posix()
        if "sol" in f.name.lower() and f.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif"):
            errors.append(f"{pid}: image file '{rel}' looks like a solution image")
        if f.suffix.lower() in (".md", ".json", ".txt"):
            bt = f.read_text(encoding="utf-8", errors="replace")
            low = bt.lower()
            if "janestreet" in low:
                errors.append(f"{pid}: '{rel}' contains a janestreet reference")
            if "-solution" in low:
                errors.append(f"{pid}: '{rel}' contains a solution URL fragment")
            if ans and not grader.get("answer_in_problem_ok"):
                needle = str(ans).replace(",", "").strip()
                if len(needle) >= 4 and needle in bt.replace(",", ""):
                    errors.append(f"{pid}: answer string appears in '{rel}'")
                elif len(needle) >= 1 and needle in bt.replace(",", ""):
                    logger.warning(f"{pid}: short answer string appears in "
                                   f"'{rel}' (likely coincidental — check)")
    return errors


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=str, default=None)
    ap.add_argument("--strict-review", action="store_true")
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else None

    pids = sorted(p.name for p in PUZZLES_DIR.iterdir() if p.is_dir())
    all_errors = []
    for pid in pids:
        if only and pid not in only:
            continue
        errs = validate_one(pid, args.strict_review)
        for e in errs:
            logger.error(e)
        all_errors.extend(errs)

    if all_errors:
        logger.error(f"validation FAILED: {len(all_errors)} error(s)")
        sys.exit(1)
    logger.info(f"validation OK ({len(pids)} puzzles)")


if __name__ == "__main__":
    main()
