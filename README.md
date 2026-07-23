# jsbench

jsbench is an agentic benchmark on the
[Jane Street monthly puzzles](https://www.janestreet.com/puzzles/).
Each puzzle is a hard, self-contained reasoning problem. Each puzzle has one
answer that a grader can check.

The benchmark measures **native agent products**, not bare models:

- The three Claude models run in **Claude Code** (CLI 2.1.215, Agent SDK 0.2.123).
- The three GPT-5.6 models run in the **Codex CLI** (0.145.0).

Each model runs in the agent harness that its vendor ships. Thus a score in
this benchmark applies to the model together with its harness.

## Results

The full run is **134 puzzles × 6 models × 3 independent samples = 2,412
sessions**. The metric is unbiased **pass@3** (Chen et al. 2021). The standard
error is computed across puzzles.

| Model | Harness | pass@3 | pass@1 | Mean cost per run |
|---|---|:---:|:---:|:---:|
| GPT-5.6 Sol | Codex | **81.3% ± 3.4%** | 72.1% | $0.57 |
| Claude Opus 4.8 | Claude Code | **70.1% ± 4.0%** | 61.4% | $1.25 |
| GPT-5.6 Terra | Codex | **65.7% ± 4.1%** | 57.2% | $0.37 |
| GPT-5.6 Luna | Codex | **55.2% ± 4.3%** | 41.5% | $0.15 |
| Claude Sonnet 5 | Claude Code | **47.8% ± 4.3%** | 41.3% | $0.94 |
| Claude Haiku 4.5 | Claude Code | **24.6% ± 3.7%** | 16.7% | $0.27 |

Significance comes from paired per-puzzle tests on pass@1:

- Sol is above Opus by +10.7pp. This difference is significant.
- Opus is above Terra by +4.2pp. This difference is **not** significant.
- Sonnet and Luna differ by 0.2pp on pass@1. This difference is **not** significant.
- In each model family, each step of the ladder (Sol > Terra > Luna;
  Opus > Sonnet > Haiku) is significant.
- With 134 puzzles, the paired minimum detectable effect is approximately ±10pp.

**Memorization control.** Before the run, a zero-tool probe asks each model for
each puzzle answer. When we remove the puzzles that the probe hit, the results
almost do not change (Opus 70.1% → 68.8%; no GPT model had a probe hit).
Memorization does not drive the ranking.

**Cost.** The total agentic spend is **$1,428.74** (Claude arm $987.79 + GPT
arm $440.95). At each capability tier, the GPT run cost is lower.

**Caution on turn counts.** Turn counts are not comparable across the two
harnesses. Codex counts one full session as one turn. The comparable activity
metric is tool calls (GPT mean 11.2 per run, median 7). Both harnesses do real
multi-step agentic work.

All tables, paired differences, and cutoff splits:
[`results/FINAL_REPORT.md`](results/FINAL_REPORT.md).

## How it works

- **Independent samples, no oracle feedback.** Each of the k=3 samples per
  (puzzle, model) pair is a new session. The agent never learns if an answer
  was correct. The pass@k estimator handles "more tries" statistically, not
  behaviorally. Self-verification inside a run (the agent checks its own work
  with code) is permitted, and the task text asks for it.

- **Disposable, isolated containers.** Each sample runs in a new Docker
  container behind an egress proxy. Reference sites (Wikipedia, OEIS, Python
  docs, arXiv, StackOverflow, PyPI) are reachable. Solution sources
  (janestreet.com, code-hosting sites, search engines, other LLM APIs) are
  blocked. A script asserts the block before each batch. The two arms use
  mirror proxies: the Claude proxy blocks openai.com, and the Codex proxy
  blocks anthropic.com. The agent can `pip install` packages, and the harness
  logs each install.

- **Answers never reach the agent.** Grading runs on the host, after the
  session ends. The container gets the puzzle bundle (problem text + images)
  mounted read-only. Empty tmpfs mounts mask the answer keys, the official
  solutions, and all previous run records out of the container filesystem.

- **Same inputs, default reasoning effort.** Both harnesses get identical task
  text, identical rules, and the same images. Reasoning effort is never
  overridden: each model runs at its own vendor default, and the harness
  records the resolved value in each run record. Vendor effort scales are not
  calibrated to each other, so a shared forced label would be false fairness.

- **Deterministic grading, human-checked ground truth.** The primary grader is
  a normalization chain (integer / float tolerance / sympy / string + aliases)
  plus per-puzzle certificate verifiers for optimization puzzles. An LLM judge
  is a secondary check for unusual formats and never overrides the
  deterministic verdict. Each ground-truth answer was checked against the
  official solution by hand.

- **Staged rollout with gates.** The run moves in checkpoint batches with
  increasing cost. Between batches, an automated gate audits error rates,
  submission rates, timeouts, cost against forecast, grading disagreements,
  and cheating flags. The protocol and the full change log are in
  [`docs/BENCH_PROGRAM.md`](docs/BENCH_PROGRAM.md).

The full design record is in [`docs/CONFIG_MAP.md`](docs/CONFIG_MAP.md).

## Repository layout

```
config/       models, prices, knowledge cutoffs, bench parameters
pipeline/     scrape -> extract -> package -> validate -> review
harness/      Claude Code runner, Codex runner, shared prompts, probes
grading/      normalization chain, certificate verifiers, LLM judge, tests
orchestrate/  per-run disposable containers, checkpoint batch builder
analysis/     pass@k / SEM / paired metrics, report, regrade, transcript audit
docker/       agent images (Claude + Codex), egress proxies, isolation checks
plans/        run plans (Claude arm: checkpoints/, GPT arm: checkpoints_gpt/)
results/      final aggregate report (numbers only, no puzzle answers)
docs/         design record (CONFIG_MAP) and operating protocol (BENCH_PROGRAM)
```

**Not committed** (local only, reproducible): `data/` (scraped puzzles,
images, graders — Jane Street content is not redistributed, and this also
keeps the benchmark set out of future training corpora), `runs/` (transcripts
and per-run records, which contain answers), and `.env` (the API keys).

## Integrity notes

The change log in [`docs/BENCH_PROGRAM.md`](docs/BENCH_PROGRAM.md) records two
incidents in full, with dates:

- **Isolation leak, found and sealed mid-run.** The first harness version
  mounted the repository read-write and graded inside the container. An audit
  found 9 runs (of 1206) that read answer content. The fix moved grading to
  the host, made the repository mount read-only, and masked all answer
  surfaces with tmpfs. All 27 samples on the 3 affected puzzles were re-run
  under the sealed harness before any final number was produced.
- **Transcript deletion accident.** A cleanup script deleted 662 of 1284 run
  directories. The append-only ledger survived, so no metric changed. The
  transcript-level audit covers the runs that remain.

The GPT arm had zero cheating suspects and zero probe hits, and all 1206
transcripts are present.

## How to reproduce

```bash
# 1. Rebuild the dataset locally (git ships nothing puzzle-specific)
python -m pipeline.scrape          # polite full-archive snapshot
python -m pipeline.extract
python -m pipeline.package
python -m pipeline.review          # emits the human answer-review sheet
python -m pipeline.validate --strict-review

# 2. Build the images and prove that the isolation holds
docker compose -f docker/docker-compose.yml build
docker compose -f docker/docker-compose.yml up -d proxy proxy-codex
docker compose -f docker/docker-compose.yml run --rm agent bash docker/verify_isolation.sh
docker compose -f docker/docker-compose.yml run --rm agent-codex bash docker/verify_isolation_codex.sh

# 3. Run the checkpointed benchmark (Claude arm, then GPT arm)
python -m orchestrate.checkpoints                         # build batch plans
python -m orchestrate.runner   --plan plans/checkpoints/cp0.json
python -m analysis.checkpoint  --batch plans/checkpoints/cp0.json --name cp0
# gate passes -> next batch, and so on; GPT plans are in plans/checkpoints_gpt/

# 4. Analyze
python -m grading.llm_judge
python -m analysis.report
python -m analysis.audit_transcripts
```

Requirements: Docker, Python 3.11+, and `ANTHROPIC_API_KEY` +
`OPENAI_API_KEY` in `.env` (see [`.env.example`](.env.example)).

## License

MIT — see [`LICENSE`](LICENSE). The license covers the benchmark *code* only.
The Jane Street puzzle content is not included and remains theirs.
