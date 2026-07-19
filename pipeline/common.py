"""Shared helpers for the jsbench data pipeline.

Scraping conventions (verified 2026-07-19 against live janestreet.com):
  - Archive pages:   {base}/index.html, {base}/page2/index.html, ...
  - Puzzle page:     https://www.janestreet.com/puzzles/{slug}-index/
  - Solution page:   https://www.janestreet.com/puzzles/{slug}-solution/
  - Leaderboard:     https://www.janestreet.com/puzzles/{lb_id}-leaderboard.json
                     -> {"leaders": [names]}   (available from Nov 2015 onward)
  - lb_id ("data-directory" on solution / current-puzzle page) looks like
    "2026-03-01-planetary-parade".
  - Content DOM: main div.page-column.row >
        div.puzzle-header.col-12   (title h3)
        div.col-12.featured-image  (puzzle image, optional)
        div.col-12                 (problem / solution body)
  - Pages are UTF-8 but the server omits charset; force response.encoding.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ROOT / "config" / "bench.yaml").read_text(encoding="utf-8"))

RAW_DIR = ROOT / CONFIG["paths"]["raw"]
PUZZLES_DIR = ROOT / CONFIG["paths"]["puzzles"]
GRADERS_DIR = ROOT / CONFIG["paths"]["graders"]

BASE = "https://www.janestreet.com"
ARCHIVE_URL = CONFIG["scrape"]["base_url"]
CURRENT_URL = CONFIG["scrape"]["current_url"]
DELAY_S = float(CONFIG["scrape"]["delay_s"])
USER_AGENT = CONFIG["scrape"]["user_agent"]

_last_request_ts = 0.0


def build_session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def polite_get(session: requests.Session, url: str, timeout: int = 20) -> requests.Response:
    """GET with a global politeness delay between requests."""
    global _last_request_ts
    wait = DELAY_S - (time.monotonic() - _last_request_ts)
    if wait > 0:
        time.sleep(wait)
    resp = session.get(url, timeout=timeout)
    _last_request_ts = time.monotonic()
    resp.raise_for_status()
    if resp.encoding in (None, "ISO-8859-1") and "charset" not in resp.headers.get("content-type", ""):
        resp.encoding = "utf-8"  # server omits charset; pages are UTF-8
    return resp


def slug_from_solution_url(solution_url: str) -> str:
    m = re.search(r"/puzzles/([a-z0-9-]+?)-solution/?$", solution_url)
    if not m:
        raise ValueError(f"cannot derive slug from {solution_url}")
    return m.group(1)


def index_url(slug: str) -> str:
    return f"{BASE}/puzzles/{slug}-index/"


def solution_url(slug: str) -> str:
    return f"{BASE}/puzzles/{slug}-solution/"


def leaderboard_url(lb_id: str) -> str:
    return f"{BASE}/puzzles/{lb_id}-leaderboard.json"


def bench_id(date_text: str, slug: str) -> str:
    """Canonical puzzle id: 'YYYY-MM-{slug}' from e.g. 'March 2026'."""
    dt = datetime.strptime(date_text, "%B %Y")
    return f"{dt:%Y-%m}-{slug}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))
