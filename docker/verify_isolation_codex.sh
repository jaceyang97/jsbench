#!/usr/bin/env bash
# Isolation gate for the CODEX agent image — the mirror of verify_isolation.sh.
# Asserts the symmetric network policy (OpenAI reachable = the agent's own
# inference endpoint; Anthropic + every solution source blocked) plus the same
# answer-store masking. Run inside the agent-codex container:
#   docker compose -f docker/docker-compose.yml run --rm agent-codex \
#       bash docker/verify_isolation_codex.sh
set -u
fail=0

reach() { local c; c=$(curl -s -o /dev/null -w "%{http_code}" -m 12 "$1");
  if [ "$c" != "000" ]; then echo "OK reach : $1 ($c)"; else echo "FAIL(reach): $1"; fail=1; fi; }
block() { local c; c=$(curl -s -o /dev/null -w "%{http_code}" -m 12 "$1");
  if [ "$c" = "000" ] || [ "$c" = "403" ]; then echo "OK block : $1 ($c)"; else echo "FAIL(block): $1 ($c)"; fail=1; fi; }

echo "== ALLOWED: OpenAI inference + pip + reference =="
reach https://api.openai.com/v1/models
reach https://pypi.org/simple/
reach https://files.pythonhosted.org/
reach https://en.wikipedia.org/wiki/Hook

echo "== BLOCKED: Anthropic + solution sources =="
block https://api.anthropic.com/
block https://www.janestreet.com/
block https://github.com/
block https://raw.githubusercontent.com/
block https://www.google.com/
block https://duckduckgo.com/
block https://puzzling.stackexchange.com/

echo "== answer surfaces must be unreachable inside the container =="
for d in /bench/data/graders /bench/data/raw; do
  if [ -e "$d" ] && [ "$(ls -A "$d" 2>/dev/null | wc -l)" != "0" ]; then
    echo "FAIL(leak): $d is populated"; fail=1
  else echo "OK mask : $d absent/empty"; fi
done
if [ -e /bench/data/review_sheet.md ]; then echo "FAIL(leak): review_sheet.md present"; fail=1
else echo "OK mask : review_sheet.md absent"; fi
if grep -rlq '"answer_type"\|"solution_md"' /bench/data 2>/dev/null; then
  echo "FAIL(leak): answer/solution data reachable under /bench/data"; fail=1
else echo "OK mask : no answer/solution data under /bench/data"; fi
if [ -f /bench/data/puzzles/2014-01-sum-of-squares/problem.md ]; then
  echo "OK bundle: puzzle bundles are mounted"
else echo "FAIL: puzzle bundle missing"; fail=1; fi

echo "== pip install works through proxy =="
if pip3 install --break-system-packages --quiet --no-cache-dir tabulate 2>/dev/null; then
  echo "OK: pip install succeeded"; else echo "FAIL: pip install failed"; fail=1; fi

echo "== codex CLI present + authenticates with API key =="
if command -v codex >/dev/null; then echo "OK: codex $(codex --version 2>/dev/null)"
else echo "FAIL: codex CLI missing"; fail=1; fi

if [ $fail -eq 0 ]; then echo "CODEX ISOLATION VERIFIED"; else echo "CODEX ISOLATION FAILED"; fi
exit $fail
