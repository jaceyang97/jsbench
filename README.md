# jsbench

An agentic benchmark measuring Anthropic models (Claude Haiku 4.5 / Sonnet 5 /
Opus 4.8) on [Jane Street monthly puzzles](https://www.janestreet.com/puzzles/),
using Claude Code as the harness.

## Method at a glance

- **Metric**: unbiased pass@k (Chen et al. 2021), k=3 fully independent
  samples per (puzzle, model). No oracle feedback — the agent never learns
  whether an answer was right. In-run self-verification (FrontierMath-style)
  is allowed and encouraged.
- **Harness**: Claude Code (pinned via the claude-agent-sdk bundled CLI) in
  `--bare` mode; images delivered as base64 blocks in the first message
  (native vision path); agent submits to `output/answer.json`.
- **Isolation**: every sample runs in a fresh disposable Docker container
  (never reused) behind an egress proxy. Reference sites (Wikipedia, OEIS,
  docs, arXiv, StackOverflow, PyPI) are reachable; solution sources
  (janestreet.com, GitHub, search engines, YouTube/Reddit, other LLM APIs)
  are blocked. Agents may `pip install` packages — every install is logged.
- **Grading**: deterministic normalization chain (int/float-tolerance/sympy/
  string+aliases) + per-puzzle certificate verifiers for optimization puzzles;
  an LLM judge is a secondary adjudicator for hard formats and never
  overwrites the deterministic verdict. Ground truth is human-reviewed
  against official solutions.
- **Contamination defenses**: zero-tool memorization probe per (puzzle, model);
  pre/post knowledge-cutoff time partition; guessproof flags for small answer
  spaces; full-transcript cheating audit.
- **Guardrails**: staged checkpoint rollout (canary → escalating batches) with
  automated gates on infra/grading/cost/integrity — see `BENCH_PROGRAM.md`.

Full design: [`CONFIG_MAP.md`](CONFIG_MAP.md). Statistical treatment follows
Miller 2024 ("Adding Error Bars to Evals"): SEM over puzzles, clustered SE for
puzzle series, paired-difference model comparisons, honest MDE reporting.

## Repository layout

```
config/       models, pricing, cutoffs, bench parameters (verified facts)
pipeline/     scrape -> extract -> package -> validate -> review
harness/      run_agent (SDK session runner), probe, image_smoke, prompts
grading/      normalize chain, certificate verifiers, LLM judge, tests
orchestrate/  runner (per-run disposable containers), checkpoint batch builder
analysis/     metrics (pass@k/SEM/clustered/paired), report, regrade, audits
docker/       agent image + egress-proxy sidecar + isolation verification
plans/        run plans (puzzle x model x k)
BENCH_PROGRAM.md  operating protocol: batches, gates, thresholds, change log
```

**Not in the repo** (local only, reproducible): `data/` (scraped puzzles,
images, graders — Jane Street's content is not redistributed here, and keeping
the benchmark set off GitHub avoids feeding it into future training corpora),
`runs/` (transcripts, per-run logs), `.env` (credentials).

To rebuild the dataset locally:

```bash
python -m pipeline.scrape          # polite full-archive snapshot
python -m pipeline.extract
python -m pipeline.package
python -m pipeline.review          # generates the human answer-review sheet
python -m pipeline.validate --strict-review
```

## Running

```bash
# isolation gate (required before scored runs)
docker compose -f docker/docker-compose.yml up -d proxy
docker compose -f docker/docker-compose.yml run --rm agent bash docker/verify_isolation.sh

# checkpointed full bench (see BENCH_PROGRAM.md)
python -m orchestrate.checkpoints              # build batch plans
python -m orchestrate.runner --plan plans/checkpoints/cp0.json
python -m analysis.checkpoint --batch plans/checkpoints/cp0.json --name cp0
# ... gate passes -> next batch

# analysis
python -m grading.llm_judge
python -m analysis.report
python -m analysis.audit_transcripts
```

## Status

Phase 0 (5-puzzle demo, 4 models) complete — validated the full loop and
caught a real grading bug via transcript audit. Full 144-puzzle × 3-model ×
k=3 run in progress under the checkpoint protocol.
