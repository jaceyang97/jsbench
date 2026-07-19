# jsbench agent container: Claude Code (pinned) + offline scientific stack.
# The container has NO direct egress; all traffic goes through the allowlist
# proxy sidecar (see docker-compose.yml). Solver libraries are pre-baked
# because the agent cannot pip install (no PyPI egress).
FROM node:20-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pinned harness version — keep in sync with config/bench.yaml
RUN npm install -g @anthropic-ai/claude-code@2.1.215

# Solver stack (matches harness/prompts.py claims — keep in sync)
RUN pip3 install --break-system-packages --no-cache-dir \
        numpy scipy sympy pandas z3-solver ortools networkx pillow matplotlib

ENV DISABLE_AUTOUPDATER=1 \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
    PYTHONIOENCODING=utf-8

# Python-side harness deps (orchestrator runs inside the container too).
# claude-agent-sdk is PINNED: its wheel bundles the authoritative claude CLI
# (0.2.123 bundles 2.1.215 — must match config/bench.yaml).
RUN pip3 install --break-system-packages --no-cache-dir \
        claude-agent-sdk==0.2.123 anthropic requests beautifulsoup4 lxml loguru pyyaml

WORKDIR /bench
# repo is bind-mounted at /bench by docker-compose
