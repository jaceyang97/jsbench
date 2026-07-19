"""Scrape Jane Street puzzle archive into data/raw/ (HTML snapshots + images).

Everything downstream (extract/package) reads only from data/raw/, so the
benchmark is reproducible from the snapshot alone.

Layout produced:
  data/raw/archive/page{N}.html
  data/raw/manifest.json                 # one entry per puzzle
  data/raw/puzzles/{bench_id}/index.html
  data/raw/puzzles/{bench_id}/solution.html
  data/raw/puzzles/{bench_id}/leaderboard.json   # {"leaders": [...]} or absent
  data/raw/puzzles/{bench_id}/images/{filename}  # index-page images only

Usage:
  python -m pipeline.scrape --limit 5          # first N archived puzzles (newest first)
  python -m pipeline.scrape --only subtiles-2,planetary-parade
  python -m pipeline.scrape                    # full archive
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from .common import (
    ARCHIVE_URL, BASE, RAW_DIR, bench_id, build_session, index_url,
    leaderboard_url, polite_get, read_json, sha256_bytes,
    slug_from_solution_url, write_json,
)


def parse_archive_page(html: str) -> list[dict]:
    """Return [{date_text, name, solution_url}] for one archive page."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for row in soup.select("div.row"):
        date_tag = row.select_one(".left span.date")
        name_tag = row.select_one(".left span.name")
        if not (date_tag and name_tag):
            continue
        date_text = date_tag.get_text(strip=True).rstrip(":")
        try:
            datetime.strptime(date_text, "%B %Y")
        except ValueError:
            continue
        link = row.select_one(".right a.solution-link")
        sol = urljoin(BASE, link["href"]) if link and link.has_attr("href") else ""
        out.append({"date_text": date_text, "name": name_tag.get_text(strip=True),
                    "solution_url": sol})
    return out


def fetch_archive(session) -> list[dict]:
    """Walk all archive pages, saving raw HTML, returning combined entries."""
    entries, page = [], 1
    while True:
        url = f"{ARCHIVE_URL}{'page%d/' % page if page > 1 else ''}index.html"
        try:
            resp = polite_get(session, url)
        except Exception as exc:
            logger.info(f"archive page {page}: stop ({exc})")
            break
        page_entries = parse_archive_page(resp.text)
        if not page_entries:
            break
        (RAW_DIR / "archive").mkdir(parents=True, exist_ok=True)
        (RAW_DIR / "archive" / f"page{page}.html").write_text(resp.text, encoding="utf-8")
        logger.info(f"archive page {page}: {len(page_entries)} puzzles")
        entries.extend(page_entries)
        page += 1
    return entries


def extract_data_directory(html: str) -> str | None:
    m = re.search(r'data-directory="([^"]+)"', html)
    return m.group(1) if m else None


def scrape_puzzle(session, entry: dict) -> dict | None:
    """Fetch index + solution + leaderboard + images for one archived puzzle."""
    if not entry["solution_url"]:
        return None  # current puzzle: no solution yet -> excluded from bench data
    slug = slug_from_solution_url(entry["solution_url"])
    pid = bench_id(entry["date_text"], slug)
    pdir = RAW_DIR / "puzzles" / pid
    pdir.mkdir(parents=True, exist_ok=True)

    meta = {
        "bench_id": pid, "slug": slug,
        "date_text": entry["date_text"], "name": entry["name"],
        "index_url": index_url(slug), "solution_url": entry["solution_url"],
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "images": [], "leaderboard_id": None, "solver_count_raw": None,
        "solver_list_available": False,
    }

    idx_html = polite_get(session, meta["index_url"]).text
    (pdir / "index.html").write_text(idx_html, encoding="utf-8")

    sol_html = polite_get(session, entry["solution_url"]).text
    (pdir / "solution.html").write_text(sol_html, encoding="utf-8")

    lb_id = extract_data_directory(sol_html)
    if lb_id:
        meta["leaderboard_id"] = lb_id
        try:
            lb = polite_get(session, leaderboard_url(lb_id)).json()
            write_json(pdir / "leaderboard.json", lb)
            leaders = lb.get("leaders", [])
            meta["solver_count_raw"] = len(leaders)
            meta["solver_list_available"] = bool(leaders)
        except Exception as exc:
            logger.warning(f"{pid}: leaderboard fetch failed: {exc}")

    # Index-page images (puzzle content only; site chrome lives under /assets/)
    soup = BeautifulSoup(idx_html, "html.parser")
    for img in soup.select("main img"):
        src = img.get("src", "")
        if not src or "/assets/" in src:
            continue
        img_url = urljoin(BASE, src)
        fname = img_url.rstrip("/").split("/")[-1]
        try:
            data = polite_get(session, img_url).content
        except Exception as exc:
            logger.warning(f"{pid}: image fetch failed {img_url}: {exc}")
            continue
        (pdir / "images").mkdir(exist_ok=True)
        (pdir / "images" / fname).write_bytes(data)
        meta["images"].append({"file": fname, "source_url": img_url,
                               "sha256": sha256_bytes(data), "bytes": len(data)})

    write_json(pdir / "meta.json", meta)
    logger.info(f"{pid}: ok (images={len(meta['images'])}, "
                f"solvers={meta['solver_count_raw']})")
    return meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="max puzzles (newest first)")
    ap.add_argument("--only", type=str, default=None, help="comma-separated slugs")
    ap.add_argument("--skip-existing", action="store_true",
                    help="skip puzzles already in data/raw/puzzles/")
    args = ap.parse_args()

    session = build_session()
    entries = fetch_archive(session)
    logger.info(f"archive total: {len(entries)} entries")

    only = set(args.only.split(",")) if args.only else None
    manifest_path = RAW_DIR / "manifest.json"
    manifest = {m["bench_id"]: m for m in
                (read_json(manifest_path) if manifest_path.exists() else [])}

    done = 0
    for entry in entries:
        if not entry["solution_url"]:
            continue
        slug = slug_from_solution_url(entry["solution_url"])
        if only and slug not in only:
            continue
        pid = bench_id(entry["date_text"], slug)
        if args.skip_existing and (RAW_DIR / "puzzles" / pid / "meta.json").exists():
            manifest.setdefault(pid, read_json(RAW_DIR / "puzzles" / pid / "meta.json"))
            continue
        try:
            meta = scrape_puzzle(session, entry)
        except Exception as exc:
            logger.error(f"{pid}: scrape failed: {exc}")
            continue
        if meta:
            manifest[meta["bench_id"]] = meta
            done += 1
        if args.limit and done >= args.limit:
            break

    # Dedupe entries sharing a leaderboard_id (the archive sometimes lists the
    # newest puzzle under two months during a transition). Keep the bench_id
    # whose YYYY-MM matches the leaderboard id's own date.
    by_lb: dict[str, list[dict]] = {}
    for m in manifest.values():
        by_lb.setdefault(m.get("leaderboard_id") or m["bench_id"], []).append(m)
    deduped = []
    for lb_id, entries in by_lb.items():
        if len(entries) == 1:
            deduped.append(entries[0])
            continue
        entries.sort(key=lambda m: m["bench_id"][:7] != (lb_id or "")[:7])
        keep, drop = entries[0], entries[1:]
        for d in drop:
            logger.warning(f"dedupe: dropping {d['bench_id']} (same leaderboard "
                           f"as {keep['bench_id']})")
        deduped.append(keep)

    write_json(manifest_path, deduped)
    logger.info(f"scraped {done} puzzles; manifest has {len(deduped)}")


if __name__ == "__main__":
    sys.exit(main())
