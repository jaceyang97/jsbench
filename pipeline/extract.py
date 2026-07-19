"""Parse raw HTML snapshots into structured per-puzzle extraction files.

Reads  data/raw/puzzles/{bench_id}/           (produced by pipeline.scrape)
Writes data/raw/puzzles/{bench_id}/extracted.json

extracted.json:
  {
    "bench_id", "title", "problem_md", "solution_md",
    "answer_candidates": [str],     # heuristic; MUST be human-reviewed
    "has_image": bool
  }

Answer heuristic: Jane Street solution pages usually state the final answer in
bold (<b>/<strong>) in the opening paragraphs. We collect all bold spans plus
standalone numbers from the first two paragraphs as candidates, ordered by
likelihood. package.py copies the top candidate into the grader with
needs_review=true; the review step (pipeline.review) finalizes ground truth.

Usage:
  python -m pipeline.extract [--only bench_id1,bench_id2]
"""
from __future__ import annotations

import argparse
import re
import sys

from bs4 import BeautifulSoup, NavigableString, Tag
from loguru import logger

from .common import RAW_DIR, read_json, write_json


# ---------------------------------------------------------------- html -> md

def _inline_text(node: Tag | NavigableString) -> str:
    if isinstance(node, NavigableString):
        return str(node)
    name = node.name
    inner = "".join(_inline_text(c) for c in node.children)
    if name in ("strong", "b"):
        return f"**{inner.strip()}**" if inner.strip() else ""
    if name in ("em", "i"):
        return f"*{inner.strip()}*" if inner.strip() else ""
    if name == "a":
        # Leakage control: NEVER emit URLs into the agent-visible bundle —
        # links reveal janestreet.com and invite lookups. Keep visible text.
        return inner
    if name == "sub":
        return f"_{inner.strip()}"
    if name == "sup":
        return f"^{inner.strip()}"
    if name == "br":
        return "\n"
    if name == "img":
        src = node.get("src", "")
        fname = src.rstrip("/").split("/")[-1]
        return f"![{node.get('alt', '')}](images/{fname})"
    return inner


def _table_to_md(table: Tag) -> str:
    rows = []
    for tr in table.find_all("tr"):
        cells = [re.sub(r"\s+", " ", _inline_text(td)).strip()
                 for td in tr.find_all(["td", "th"])]
        rows.append("| " + " | ".join(cells) + " |")
    if len(rows) >= 1:
        ncols = rows[0].count("|") - 1
        rows.insert(1, "|" + " --- |" * ncols)
    return "\n".join(rows)


def block_to_md(el: Tag) -> str:
    name = el.name
    if name == "p":
        return re.sub(r"[ \t]+", " ", _inline_text(el)).strip()
    if name in ("h1", "h2", "h3", "h4"):
        return "### " + el.get_text(" ", strip=True)
    if name in ("ul", "ol"):
        lines = []
        for i, li in enumerate(el.find_all("li", recursive=False), 1):
            bullet = "-" if name == "ul" else f"{i}."
            lines.append(f"{bullet} " + re.sub(r"\s+", " ", _inline_text(li)).strip())
        return "\n".join(lines)
    if name == "table":
        return _table_to_md(el)
    if name in ("pre", "code"):
        return "```\n" + el.get_text() + "\n```"
    if name == "div":
        parts = [block_to_md(c) for c in el.find_all(recursive=False) if isinstance(c, Tag)]
        return "\n\n".join(p for p in parts if p)
    if name == "img":
        return _inline_text(el)
    return el.get_text(" ", strip=True)


def body_to_md(body: Tag) -> str:
    parts = []
    for child in body.find_all(recursive=False):
        if not isinstance(child, Tag):
            continue
        md = block_to_md(child)
        if md:
            parts.append(md)
    return "\n\n".join(parts).strip()


# ------------------------------------------------------------- page parsing

def parse_page(html: str) -> tuple[str, str, bool]:
    """Return (title, body_md, has_featured_image)."""
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.select_one("main div.puzzle-header h3")
    title = title_tag.get_text(strip=True) if title_tag else ""
    has_img = soup.select_one("main div.featured-image img") is not None

    body_md = ""
    for col in soup.select("main div.page-column.row > div.col-12"):
        classes = col.get("class", [])
        if "puzzle-header" in classes or "featured-image" in classes:
            continue
        body_md = body_to_md(col)
        break
    return title, body_md, has_img


# --------------------------------------------------------- answer heuristic

_NUM_RE = re.compile(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?(?![\w])")


def answer_candidates(solution_md: str) -> list[str]:
    """Ordered candidate answers from the solution text."""
    cands: list[str] = []
    paras = [p for p in solution_md.split("\n\n") if p.strip()]
    head = "\n\n".join(paras[:3])

    for m in re.finditer(r"\*\*(.+?)\*\*", head):          # bold spans first
        cands.append(m.group(1).strip().rstrip("."))
    for m in re.finditer(r"answer\s+(?:is|was)\s+([^\s,.;]+)", head, re.I):
        cands.append(m.group(1).strip())
    for m in _NUM_RE.finditer(head):                        # bare numbers last
        cands.append(m.group(0))

    seen, out = set(), []
    for c in cands:
        c = c.strip()
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out[:8]


def guess_answer_format(candidate: str | None) -> str:
    if not candidate:
        return "unknown"
    c = candidate.replace(",", "")
    if re.fullmatch(r"[-+]?\d+", c):
        return "integer"
    if re.fullmatch(r"[-+]?\d*\.\d+", c):
        return "decimal"
    return "string"


# -------------------------------------------------------------------- main

def extract_one(pid: str) -> dict | None:
    pdir = RAW_DIR / "puzzles" / pid
    if not (pdir / "index.html").exists():
        logger.warning(f"{pid}: no index.html")
        return None
    title, problem_md, has_img = parse_page((pdir / "index.html").read_text(encoding="utf-8"))
    _, solution_md, _ = parse_page((pdir / "solution.html").read_text(encoding="utf-8"))
    meta = read_json(pdir / "meta.json")

    cands = answer_candidates(solution_md)
    out = {
        "bench_id": pid,
        "title": title or meta["name"],
        "problem_md": problem_md,
        "solution_md": solution_md,
        "answer_candidates": cands,
        "answer_format_guess": guess_answer_format(cands[0] if cands else None),
        "has_image": has_img or bool(meta.get("images")),
    }
    write_json(pdir / "extracted.json", out)
    logger.info(f"{pid}: extracted (problem {len(problem_md)} ch, "
                f"{len(cands)} answer candidates)")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=str, default=None)
    args = ap.parse_args()

    only = set(args.only.split(",")) if args.only else None
    pids = sorted(p.name for p in (RAW_DIR / "puzzles").iterdir() if p.is_dir())
    n = 0
    for pid in pids:
        if only and pid not in only:
            continue
        if extract_one(pid):
            n += 1
    logger.info(f"extracted {n} puzzles")


if __name__ == "__main__":
    sys.exit(main())
