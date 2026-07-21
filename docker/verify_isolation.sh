#!/usr/bin/env bash
# Phase-1 network gate — BLOCKLIST model.
# ALLOWED: general reference / programming material (agents may consult it).
# BLOCKED: an empirical set of hosts where a Jane Street solution could live
#          (source site, code hosts, search engines, video/social, other LLMs).
# The container has no direct route — the proxy is the only path, so this
# filter governs every request; the transcript audit is the post-hoc backstop.
set -u
fail=0
probe() { curl -s -o /dev/null -w "%{http_code}" --max-time 12 "$1" 2>/dev/null; }

must_reach() {
  code=$(probe "$1")
  if [ "$code" = "000" ]; then echo "FAIL(reach): $1 unreachable"; fail=1
  else echo "OK reach : $1 ($code)"; fi
}
must_block() {
  code=$(probe "$1")
  if [ "$code" = "000" ] || [ "$code" = "403" ]; then echo "OK block : $1 ($code)"
  else echo "FAIL(block): $1 reachable ($code)"; fail=1; fi
}

echo "== ALLOWED: inference + pip + reference =="
must_reach https://api.anthropic.com/v1/models
must_reach https://pypi.org/simple/
must_reach https://files.pythonhosted.org/
must_reach https://en.wikipedia.org/wiki/Euler_characteristic
must_reach https://oeis.org/
must_reach https://docs.python.org/3/
must_reach https://mathworld.wolfram.com/
must_reach https://arxiv.org/

echo "== BLOCKED: solution sources =="
must_block https://www.janestreet.com/
must_block https://github.com/
must_block https://raw.githubusercontent.com/
must_block https://gowen100.github.io/
must_block https://www.google.com/
must_block https://duckduckgo.com/
must_block https://www.bing.com/
must_block https://www.youtube.com/
must_block https://www.reddit.com/
must_block https://puzzling.stackexchange.com/
must_block https://chatgpt.com/
must_block https://api.openai.com/

echo "== direct egress (bypassing proxy) must be blocked =="
code=$(env -u HTTPS_PROXY -u HTTP_PROXY curl -s -o /dev/null -w "%{http_code}" --max-time 12 https://www.google.com/ 2>/dev/null)
if [ "$code" = "000" ]; then echo "OK: no direct route"
else echo "FAIL: direct egress works ($code)"; fail=1; fi

echo "== pip install works through proxy =="
if pip3 install --break-system-packages --quiet --no-cache-dir tabulate 2>/dev/null; then
  echo "OK: pip install succeeded"
else echo "FAIL: pip install failed"; fail=1; fi

echo "== answer surfaces must be unreachable inside the container =="
# Every location that could reveal an answer or solution must be gone:
#   data/graders (answers), data/raw (solution_md), data/review_sheet.md
#   (answers+solutions), runs/ (prior transcripts + run.json grader_snapshots).
# Only data/puzzles (clean problem bundles) may remain under /bench/data.
for d in /bench/data/graders /bench/data/raw; do
  if [ -e "$d" ] && [ "$(ls -A "$d" 2>/dev/null | wc -l)" != "0" ]; then
    echo "FAIL(leak): $d is populated"; fail=1
  else echo "OK mask : $d absent/empty"; fi
done
if [ -e /bench/data/review_sheet.md ]; then
  echo "FAIL(leak): data/review_sheet.md is present"; fail=1
else echo "OK mask : review_sheet.md absent"; fi
# runs/ history must be empty except THIS run's own dir (a single writable bind)
others=$(ls -A /bench/runs 2>/dev/null | grep -v "$(basename "$(pwd)" 2>/dev/null)" | wc -l)
echo "OK info : /bench/runs entries visible = $(ls -A /bench/runs 2>/dev/null | wc -l) (expect just this run)"
# Catch-all over the DATA tree (source code legitimately names the field
# "solution_md"; only actual data files carry answers). No grader schema
# (answer_type) and no solution text may survive anywhere under /bench/data.
if grep -rlq '"answer_type"\|"solution_md"' /bench/data 2>/dev/null; then
  echo "FAIL(leak): answer/solution data reachable under /bench/data"; fail=1
else echo "OK mask : no answer/solution data under /bench/data"; fi
# and confirm the clean bundle IS still present (needed to run)
if [ -f /bench/data/puzzles/2014-01-sum-of-squares/problem.md ]; then
  echo "OK bundle: puzzle bundles are mounted"
else echo "FAIL: puzzle bundle missing (agent cannot run)"; fail=1; fi

if [ $fail -eq 0 ]; then echo "ISOLATION VERIFIED"; else echo "ISOLATION FAILED"; fi
exit $fail
