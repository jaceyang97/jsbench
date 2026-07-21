# jsbench

An agentic benchmark measuring how well Claude models solve
[Jane Street's monthly puzzles](https://www.janestreet.com/puzzles/) when
driven by Claude Code as the harness. Each puzzle is a hard, self-contained
reasoning problem with a single verifiable answer.

## Results

Full run: **134 puzzles × 3 models × 3 independent samples = 1,206 sessions.**
Metric is unbiased **pass@3** (Chen et al. 2021) with the standard error taken
over puzzles.

| Model | pass@3 | pass@1 | mean $/session |
|-------|:------:|:------:|:--------------:|
| Claude Opus 4.8   | **70.1% ± 4.0%** | 61.4% | $1.25 |
| Claude Sonnet 5   | **47.8% ± 4.3%** | 41.3% | $0.94 |
| Claude Haiku 4.5  | **24.6% ± 3.7%** | 16.7% | $0.27 |

All three pairwise gaps are statistically significant (paired over the same
puzzles). Excluding puzzles a zero-tool memorization probe could answer barely
moves the numbers (Opus 70.1% → 68.8%), so memorization is not driving the
ranking. With 134 puzzles the paired minimum detectable effect is ≈ ±10pp.

## How it works

- **Independent sampling, no oracle feedback.** Each of the k=3 samples per
  (puzzle, model) is a fresh session; the agent never learns whether an answer
  was correct. "Multiple tries" is handled statistically by the pass@k
  estimator, not behaviorally by a feedback loop. In-run self-verification
  (the agent checking its own work with code) is allowed and encouraged.

- **Disposable, isolated containers.** Every sample runs in a fresh Docker
  container behind an egress proxy. Reference sites (Wikipedia, OEIS, Python
  docs, arXiv, StackOverflow, PyPI) are reachable; solution sources
  (janestreet.com, GitHub, search engines, other LLM APIs) are blocked and the
  block is asserted before every run. The agent may `pip install` anything;
  every install is logged.

- **Answers never reach the agent.** Grading runs on the host. The container
  gets the puzzle bundle (problem text + images) mounted read-only; the answer
  keys and official solutions are masked out of its filesystem entirely.

- **Deterministic grading, human-reviewed ground truth.** A normalization
  chain (integer / float-tolerance / sympy / string+aliases) plus per-puzzle
  certificate verifiers for optimization puzzles. An LLM judge is a secondary
  adjudicator for awkward formats and never overrides the deterministic
  verdict. Every answer was checked against the official solution by hand.

- **Staged rollout with gates.** The run proceeds in escalating checkpoint
  batches; between batches an automated gate audits error/submission/timeout
  rates, cost vs. forecast, grading disagreements, and cheating flags. Details
  and the full change log are in [`docs/BENCH_PROGRAM.md`](docs/BENCH_PROGRAM.md).

Full design rationale: [`docs/CONFIG_MAP.md`](docs/CONFIG_MAP.md).

## Repository layout

```
config/       models, pricing, cutoffs, bench parameters
pipeline/     scrape -> extract -> package -> validate -> review
harness/      agent runner (SDK session), memorization probe, image smoke test
grading/      normalization chain, certificate verifiers, LLM judge, tests
orchestrate/  runner (per-run disposable containers), checkpoint batch builder
analysis/     pass@k / SEM / paired metrics, report, regrade, transcript audit
docker/       agent image, egress-proxy sidecar, isolation verification
plans/        run plans (puzzle x model x k)
docs/         operating protocol and full design
```

**Not committed** (local only, reproducible): `data/` (scraped puzzles,
images, graders — Jane Street's content is not redistributed, which also keeps
the benchmark set out of future training corpora), `runs/` (transcripts and
per-run logs), and `.env` (the API key).

## Reproducing

```bash
# 1. rebuild the dataset locally (nothing puzzle-specific is shipped in git)
python -m pipeline.scrape          # polite full-archive snapshot
python -m pipeline.extract
python -m pipeline.package
python -m pipeline.review          # emits the human answer-review sheet
python -m pipeline.validate --strict-review

# 2. build images and prove the isolation holds
docker compose -f docker/docker-compose.yml build
docker compose -f docker/docker-compose.yml up -d proxy
docker compose -f docker/docker-compose.yml run --rm agent bash docker/verify_isolation.sh

# 3. run the checkpointed benchmark
python -m orchestrate.checkpoints                         # build batch plans
python -m orchestrate.runner   --plan plans/checkpoints/cp0.json
python -m analysis.checkpoint  --batch plans/checkpoints/cp0.json --name cp0
# gate passes -> next batch, and so on

# 4. analyze
python -m grading.llm_judge
python -m analysis.report
python -m analysis.audit_transcripts
```

Requires Docker, Python 3.11+, and an `ANTHROPIC_API_KEY` in `.env`.

## License

MIT — see [`LICENSE`](LICENSE). Note this covers the benchmark *code* only; the
Jane Street puzzle content it operates on is not included and remains theirs.
