# jsbench — full benchmark design record (final, v4)

Generated: 2026-07-19 · Repository: github.com/jaceyang97/jsbench (code
public; data/ and runs/ local).

- v3: return to the literature standard — k independent samples, no oracle
  feedback, Chen unbiased pass@k. (The v2 feedback-retry design was rejected
  on review; it remains as an experimental flag, off by default.)
- v4: **full set of 144 puzzles × 3 models (no Fable) × k=3, with checkpoint
  guardrails between batches** (§11-bis).

> **Status of this document.** This is the frozen design record for the
> Claude arm, as approved on 2026-07-19. Values that changed during
> operations (the puzzle count 144→134, the concurrency, the circuit-breaker
> level, the wall-clock cap) are recorded, with dates, in the
> [`BENCH_PROGRAM.md`](BENCH_PROGRAM.md) change log. The GPT (Codex) arm was
> added on 2026-07-22 as a mirror of this design; see the addendum at the end
> of this file. The original document was partly in Chinese; it was rewritten
> in controlled English on 2026-07-24 with no number changed.

---

## 1. Goal and primary metric (v3: independent-sample pass@k)

**Question**: how well do Anthropic models (Haiku 4.5 / Sonnet 5 / Opus 4.8;
**Fable 5 does not compete**, reasons in §10) solve Jane Street monthly
puzzles in the Claude Code harness?

**Primary metric: pass@k over k fully independent samples** (the
HumanEval / Chen et al. 2021 unbiased estimator `1 − C(n−c,k)/C(n,k)`,
computed per puzzle, then averaged across puzzles). Each attempt = a new
container + a new session, **with no oracle feedback** — the agent never
learns if it was correct; grading stays fully outside the agent world. The
estimator handles "more tries help" statistically, not behaviorally.

**Why not "tell the model it was wrong and let it retry"** (the v2 design,
rejected): oracle feedback changes the measured object from "solving ability"
to "adaptive search against the grader". Puzzles with small answer spaces
(one letter, a binary choice) can be hit by enumeration. No mature benchmark
(HumanEval, FrontierMath, SWE-bench, ARC-AGI) uses oracle feedback — ARC's
"2 submissions per task" are simultaneous, with no feedback between them.
**The legitimate form of "iterative improvement"** is FrontierMath-style
in-run self-verification (the agent checks its own answer with code before
submission); TASK_RULES asks for exactly that.

| Model | model_id | k (independent) | Per-run budget cap | max_turns | Reliable cutoff |
|---|---|---|---|---|---|
| Haiku 4.5 | claude-haiku-4-5-20251001 | **3** | $0.75 | 30 | 2025-02 |
| Sonnet 5 | claude-sonnet-5 | **3** | $1.50 | 40 | 2026-01 |
| Opus 4.8 | claude-opus-4-8 | **3** | $3.00 | 40 | 2026-01 |
| ~~Fable 5~~ | ~~claude-fable-5~~ | not competing | — | — | cost + memorization, see §10 |

k = 3 for all models: pass@1 / pass@2 / pass@3 stay comparable across models.

**Guessproof principle** (FrontierMath): puzzles with small answer spaces
(one letter, a two-name choice) get `guessable: true` and are listed outside
the main table. Large numeric answers (the 13,682,882 class) resist guessing
by nature.

Report presentation: pass@k (k=3) ± SEM as primary + pass@1 + paired
differences (same-puzzle pairs, 95% CI) + clustered SE (puzzle series form
clusters) + pre/post-cutoff strata + memorization-excluded sensitivity +
guessable listed separately. Secondary: cost, turns, tool calls, pip-install
behavior.

*(The v2 same-session feedback retry remains as the `max_attempts>1`
experimental flag, default 1 = off. To measure "feedback gain" as an extra
research arm later, change the config; it never enters the primary metric.)*

---

## 2. Puzzle library and the formal set

- The full archive of **148 puzzles** is scraped (2014-01 through 2026-06).
  Raw HTML / images / leaderboard JSON snapshots live in `data/raw/` with
  timestamps and SHA-256 hashes; reproducible offline.
- **Formal set = all 144 usable puzzles** (148 − 4 open puzzles without a
  fixed answer, marked `exclude_recommended`). (During grader review, 9 more
  open-competition puzzles were excluded; final set 134 — see the
  BENCH_PROGRAM change log, 2026-07-19.)

---

## 3. Runtime environment (one disposable container per run)

```
Host (Windows) ── orchestrator (asyncio, concurrency 3)
   │  per run: docker compose run --rm agent …   ← new container, destroyed after use, never reused
   ▼
Container (node:20-slim, runs as the node user)
   ├─ Claude Code CLI 2.1.215 (bundled by the SDK 0.2.123 wheel; version double-pinned)
   ├─ Python3 + preinstalled: numpy scipy sympy pandas z3-solver ortools networkx pillow matplotlib
   ├─ the agent can install more: pip install any PyPI package
   │  (philosophy: give a solid base; the agent evolves its own environment)
   └─ egress: only through the tinyproxy sidecar
```

**Network: blocklist model (v2, default-allow + empirical blocks)** — per the
operator's addendum item 7: the agent may consult math/programming
references; block only "the places where solutions can exist". The container
network is internal (no external gateway); tinyproxy is the only exit; each
request passes the filter and **each request is logged in full**.

- **Allowed** (tested, HTTP 200): Wikipedia, OEIS, Wolfram MathWorld, Python
  docs, arXiv, StackOverflow, PyPI, the Anthropic API — everything not on the
  blocklist.
- **Blocked** (tested, HTTP 000; `docker/proxy/filter`):
  - The source site: janestreet.com
  - Code hosting (known solution repositories — gowen100 / miguelbper /
    iamzr…): github.com, *.github.io, githubusercontent, gist, gitlab,
    bitbucket, codeberg, sourceforge
  - Search engines (the discovery layer; stops a title search from finding a
    solution page): google / bing / duckduckgo / yandex / baidu / brave /
    ecosia / startpage / qwant / kagi / you.com / perplexity / phind
  - Video / social / blog platforms: youtube, reddit, twitter/x, medium,
    substack, quora
  - The Jane Street solution area: puzzling.stackexchange.com
  - Other LLM endpoints (stops outsourced solving): openai, googleapis,
    deepseek, mistral
- **WebSearch / WebFetch tools stay disabled**: these are Anthropic
  server-side tools and **bypass the container proxy** (the blocklist cannot
  see them). With the tools disabled, the network block is real. The agent
  reaches the network through Bash (curl / python) — that path obeys the
  proxy blocklist and leaves a full trace.
- Direct connections (around the proxy) have no route. Verification script
  `docker/verify_isolation.sh`: last run — allow 8/8, block 12/12, direct
  egress blocked, pip OK. All green.

**Residual risk (stated honestly)**: a site not on the blocklist could host a
solution to some puzzle (a personal blog, for example); the agent can reach
it in theory. Without search engines, discovery of such a URL is hard. **The
operator accepts this trade-off** ("do your best, I have logs post hoc"); the
transcript records every Bash network access for post-hoc audit.

---

## 4. Single-sample flow (v3: independent session, no feedback)

```
1. The orchestrator makes a run_id and starts a disposable container (--rm).
2. The harness copies data/puzzles/<id>/ into a private workdir and makes an empty output/.
3. First message: [image base64 blocks] + [problem text + TASK_RULES]
   → images go through the model's native vision channel; the agent loop
   (bare mode) works autonomously; it can self-verify with code
   (FrontierMath style); it writes output/answer.json and stops.
   Tools: Bash, Read, Write, Edit, Glob, Grep; WebSearch/WebFetch disabled.
   Caps: max_turns (SDK) + max_budget_usd + 45min wall clock.
4. The session ends; the container is destroyed; grading happens off-stage
   (the agent never learns the result). The k samples for one
   (puzzle, model) pair are fully isolated from each other — zero
   information flow.
```

The full prompt text is in `harness/prompts.py` (SYSTEM_APPEND +
TASK_RULES). Each run records the SHA-256 of both — drift is detectable.

---

## 5. Anti-leak controls ("give the puzzle itself, and not one bit more")

**Bundle contents** (everything the agent can see): `problem.md` (original
wording) + `images/` (problem-page images only) + `metadata.json` (id / date
/ title / answer-format hint). The controls, item by item:

| # | Control | Mechanism |
|---|---|---|
| 1 | Answer/solution isolation | graders live in `data/graders/`, never enter the bundle; no solution-page content enters packaging |
| 2 | Hyperlink stripping | every `<a>` in the problem keeps its visible text only; no URL is emitted (extract layer) |
| 3 | janestreet token wash | submission emails / literal URLs become `[removed]` (package layer) |
| 4 | Image source | only problem-page `<img>`; a filename that contains "sol" raises an error |
| 5 | Image URL hiding | metadata holds filename + SHA-256 only; no source_url |
| 6 | Answer-string scan | validate scans the whole bundle: an answer string (≥4 chars) present = FAIL; unavoidable hits (role names) need a human `answer_in_problem_ok` |
| 7 | Feedback minimization | a wrong answer returns one bit ("wrong") + the rejected value; no "where/why"; a correct answer ends the session |
| 8 | Environment isolation | a new container per run (pip state / temp files do not cross runs); bare mode masks host configuration |
| 9 | answer_format hint | format only (e.g. "integer"), taken from the problem statement, human-reviewed to carry no solution information |

**Status: all 144 puzzles (after open-puzzle exclusion) pass validate;
answer-checked puzzles pass strict mode.**

**Known residual risks (recorded honestly, not hidden)**:

- **Memorization**: a model can remember an old puzzle answer. Per the
  operator's decision this is permitted but must leave a trace: a zero-tool
  memorization probe (each puzzle × each model) is on file. Phase 0
  confirmed 1 case (fable × knight-moves: the probe emitted the correct
  answer directly) + 1 suspected case (the three main models submitted the
  identical sum-of-squares optimal grid). The report includes a sensitivity
  analysis that excludes probe hits.
- **PyPI side channel**: in theory a PyPI package can contain puzzle
  solutions (a personal solutions collection, for example). Accepted as low
  risk; **each pip install is recorded in run.json** for post-hoc audit.
- **Anthropic API side channel**: in theory the agent can call the
  server-side web_search tool by hand with the container's API key. The tool
  layer disables WebSearch/WebFetch; the audit layer scans tool inputs for
  patterns such as `api.anthropic.com` / `web_search` and raises
  `suspect_cheating` for human review.

---

## 6. Logging and auditability ("open to inspection by other agents later")

**Per-run directory** (`runs/<run_id>/`, kept permanently):

| File | Content |
|---|---|
| `initial_message.json` | verbatim first message to the model (every text block + each image's media_type / size / SHA-256 / block order) |
| `options.json` | every effective parameter: model, caps, tool allowlist, full system prompt, SDK/CLI versions, non-secret env |
| `transcript.jsonl` | the full SDK message stream: every assistant message, **every tool call with complete input and output**, thinking blocks, ResultMessage (tokens / cost / per-model usage) |
| `stderr.log` | raw CLI process stderr (error diagnosis) |
| `workdir/` | the agent's final working directory: every script it wrote, every intermediate file, output/answer.json |
| `run.json` | the structured record (below) |

**run.json fields**: run_id / puzzle / arm / model_requested /
**model_actual (per-model tokens; detects silent Fable handoff)** / harness
versions / bare_mode / prompt SHA-256 ×2 / timestamps / wall_time /
num_turns / tool_calls / four token counts / cost_usd / exit_reason /
image_delivered / **suspect_cheating + suspect_details (matched samples)** /
**pip_installs (package names)** / submitted_answer / correct / grade_method
/ **grader_snapshot (the answer / type / tolerance / verifier at grading
time — a later grader edit cannot hide what the verdict saw)**.

**Global ledgers**: `runs/runs.jsonl` (append-only lines; idempotent
resume), `runs/probes.jsonl` (memorization probes: the model's words,
UNKNOWN or not, hit or not), `runs/image_smoke.jsonl` (full description text
per image × model).

**Grading is replayable** (against "more puzzles = more grading bugs"):
grader_snapshot + preserved workdir = `analysis.regrade` can re-grade
everything at any time and list each verdict flip (proven in Phase 0: after
the equation-format bug fix, regrade flipped 3 wrong verdicts; the old
ledger was backed up). Audit tool: `analysis.audit_transcripts` (a review
sheet for all runs in ~20 seconds: answers / flags / tool stats / bash
samples).

---

## 7. Grading system (deterministic first + LLM judge backstop)

1. **Deterministic normalization chain** (`grading/normalize.py`, **the
   primary verdict**): cleanup (whitespace / thousands separators / currency
   / quotes) → integer → numeric (float or sympy exact expression, supports
   `sqrt/π/^`) → tolerance compare (exact/rel/abs) → sympy symbolic
   equivalence → casefold string + aliases. Special cases: `exact form =
   decimal` equations accept either side; the `multi` type splits on commas
   and compares item by item (order-sensitive).
2. **Certificate verifiers** (`grading/verifiers.py`): puzzles that demand a
   "work product" (e.g. sum-of-squares: the (total, 25-digit grid) pair) get
   programmatic verification — format / self-consistency / constraints /
   optimality checked item by item. This stops bare-number cheating.
3. **LLM judge backstop** (`grading/llm_judge.py`, **secondary, runs after
   each batch**, operator addendum 2): some answer formats are awkward (free
   text, many equivalent spellings, odd separators). The judge uses opus
   (thinking off, structured output) to test semantic/mathematical
   equivalence. It triggers only for "hard format" cases (grader marks
   `grading_mode: llm`, or answer_type ∈ {string, expression, multi}, or
   deterministic-wrong with a non-empty answer = possible miss). **The
   verdict goes to the separate field `llm_judge_correct` and never
   overrides the deterministic verdict**; the report shows both numbers, and
   each disagreement is listed. The judge must "answer no when unsure, give
   no partial credit" — this stops score inflation. Correct use: the judge
   finds a deterministic miss → a human fixes the grader (alias / tolerance)
   → `analysis.regrade` re-grades everything. Never trust the LLM blindly.
4. **Unit tests**: `grading/test_normalize.py`, 22 cases (with adversarial
   variants), all pass.
5. Every ground-truth answer has a human review record (review_note).

**Against "more puzzles = more grading bugs"**: (1) the judge backstop flags
possible deterministic misses automatically; (2) every run stores
grader_snapshot + full workdir → `analysis.regrade` re-grades all runs after
a grader fix and lists each verdict flip (3 flips corrected in Phase 0); (3) 
`analysis.audit_transcripts` generates a full review sheet in seconds. A
grading verdict stays traceable, replayable, and reviewable.

---

## 8. Orchestration and guardrails

- Concurrency 3 (rate-limit friendly); **budget breaker $190** (cumulative
  cost_usd in real time; over the line = stop the queue). (Historical v4
  values; the operational history — breaker $780→$900→$1000, concurrency
  experiments 3→8→24 that settled at 12 and later moved to 10 — is in the
  BENCH_PROGRAM change log.)
- Idempotent resume: a (puzzle, model, sample) key with a terminal record is
  skipped; after an interruption, the same command continues the run.
- Retries: infrastructure errors only, ≤2; a wrong answer is never retried.
- Three caps per run: max_turns (SDK) / max_budget_usd / 30min wall clock
  (inside the harness; later raised to 45min — see bench.yaml).

---

## 9. Execution sequence (checkpoint batches; details in BENCH_PROGRAM.md)

```bash
# 0) network-isolation gate (blocklist model)
docker compose -f docker/docker-compose.yml up -d proxy
docker compose -f docker/docker-compose.yml run --rm agent bash docker/verify_isolation.sh

# 1) build the batch plans
python -m orchestrate.checkpoints

# 2) per batch: launch -> gate audit -> pass before the next batch (cp0 canary shown)
python -m harness.probe          # memorization probes (batch puzzles x 3 models)
python -m harness.image_smoke    # image smoke test (batch puzzles x 3 models)
python -m orchestrate.runner --plan plans/checkpoints/cp0.json
python -m grading.llm_judge      # hard-format review
python -m analysis.checkpoint --batch plans/checkpoints/cp0.json --name cp0
#   PASS -> cp1; WARN -> handle, then continue; HARD-FAIL -> stop, fix, re-run the affected subset

# 3) after all batches
python -m analysis.report
python -m analysis.audit_transcripts
```

---

## 10. Budget and statistical power (v4 final: full three-model run approved)

**Chosen configuration: all usable puzzles (144) × 3 models
(Haiku/Sonnet/Opus, no Fable) × k=3** = 1,296 independent sample sessions.
Measured mean prices: haiku $0.30 / sonnet $0.79 / opus $0.55 per sample →
$4.92 per puzzle → **agentic total estimate ~$699** + probes/judge ~$10;
**circuit breaker $780**.

Why Fable is out: the most expensive ($0.82 per sample × $50/MTok output),
and the probe already confirmed memorization (knight-moves: the answer
recited with zero tools). The three-model comparison covers the product
tiers that matter most.

**Statistical power (P=144)**: paired MDE **±9pp** (a real gap between
adjacent tiers, such as Sonnet vs Opus, is detectable with high
probability); single-model pass@1 95% CI half-width ~±8pp; the post-cutoff
subgroup (~5 puzzles) gets descriptive reporting only. Wall clock: at
concurrency 3, about ~28h, run in batches across nights, resumable.
The Sonnet introductory price expires 2026-08-31; a run completed before
that date is billed at the introductory price (the estimate uses it).

---

## 11-bis. Checkpoint guardrails (v4, autoresearch-style batching)

The full run does not launch at once. It moves in **5 batches of increasing
cost, with an automatic gate between batches** (the detailed protocol is in
`BENCH_PROGRAM.md` — that file is the human-editable steering wheel; this is
the summary):

| Batch | Puzzles | k | Estimate | Role |
|---|---|---|---|---|
| cp0 | 3 (calibration) | 1 | ~$5 | infrastructure canary, not scored |
| cp1 | 12 (incl. calibration) | 3 | ~$59 | grading calibration + cost-model check |
| cp2 | 25 | 3 | ~$123 | first batch at scale |
| cp3 | 45 | 3 | ~$221 | main body |
| cp4 | 59 | 3 | ~$290 | completion |

Batches are stratified by era × difficulty in a round-robin (each batch is
representative; extrapolation is valid). Each gate (`analysis.checkpoint`)
audits automatically: error rate / timeout rate / submission rate / bare /
image delivery / transcript completeness (HARD level — a hit stops the
program), the judge-disagreement queue and wrong-answer samples (human
review per batch), per-model mean cost vs the forecast band [0.4×, 2.0×],
cumulative spend vs the $780 breaker, cheating flags / pip list. Correction
rules: a grader-level fix → regrade, no re-run; a harness-level fix → mark
the affected subset invalid and re-run it. Answer checks proceed with the
batches (before batch N launches, all its graders are reviewed). Milestone
reports to the operator at $400 / $600; protocol-level changes are asked
first, changed after.

## 11. Known biases and honest statements

- **Statistical power**: P=144 → paired MDE ≈ ±9pp; the report states this.
  Only model gaps above the threshold are reliably detectable; stratified
  subgroups (post-cutoff, ~5 puzzles) get descriptive reporting only.
- **Metric semantics**: solve@N ("solved within N feedback attempts") is not
  independent sampling; it cannot be compared with Chen pass@k or with the
  Phase 0 v1 data. The Phase 0 ledger is archived separately.
- **The two edges of feedback**: same-session retry lets an agent correct
  itself (closer to real solving), but the N attempts of one session are
  highly correlated; the SEM comes from puzzle variance only (P puzzles). If
  budget allows, several independent sessions per puzzle (replicates) narrow
  it further; the default is 1 session per puzzle so the budget covers more
  puzzles. (Moot in v3/v4: feedback is off.)
- **The network blocklist is empirical**: a site not on the list can host a
  solution and stays reachable in theory (hard to discover without search
  engines). The operator accepts this trade-off; the transcript keeps a full
  trace for post-hoc audit.
- The Sonnet 5 introductory price expires 2026-08-31; the run completed
  before that date is billed at the introductory price.
- A probe cannot fully falsify "the model recalled the answer while
  solving". The certificate verifiers + LLM judge + transcript audit are
  additional defense layers; the report presents the memorization-excluded
  sensitivity split.

---

## Addendum — GPT (Codex) arm, added 2026-07-22

The GPT-5.6 arm (sol / terra / luna) mirrors this design for a native-agent
product comparison. Differences from the Claude arm, in full:

- Harness: Codex CLI 0.145.0 (`codex exec --json`) instead of Claude Code;
  runner `harness/run_agent_codex.py`; image `docker/Dockerfile.codex`.
- Egress proxy: same blocklist, with the vendor block mirrored — the Codex
  filter (`docker/proxy/filter.codex`) blocks anthropic.com and allows
  api.openai.com. Verification: `docker/verify_isolation_codex.sh`.
- Per-run budget caps mirror the Claude tiers: sol $3.00 / terra $1.50 /
  luna $0.75. Cost is computed from streamed token usage × public prices.
- Everything else is identical: bundles, task text, k=3, host-side grading,
  run-record schema, tmpfs answer masks, /out output isolation, default
  (never overridden) reasoning effort.

See `config/models.json` for the tier mapping and prices, and the
BENCH_PROGRAM change log (2026-07-22 onward) for the run history.
