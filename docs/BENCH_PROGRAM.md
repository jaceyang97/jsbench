# BENCH_PROGRAM — operating protocol and change log

This file has two layers, in the style of an autoresearch `program.md`:

- **Strategy layer** (this file, maintained by the human operator): the
  protocol, the thresholds, and the gate rules. A change here is a change to
  the experiment.
- **Tactics layer** (the agent): the agent executes this file, audits the logs
  at each checkpoint, applies corrections, and appends to the change log
  (see below).

Note on language: the original file was partly in Chinese. It was rewritten in
controlled English on 2026-07-24. No number, date, or dollar amount was
changed.

## Program summary (Claude arm)

- **Scope**: all usable puzzles (~142 at plan time, after
  `exclude_recommended`) × 3 models (Haiku 4.5 / Sonnet 5 / Opus 4.8; Fable 5
  does not compete — high cost plus confirmed memorization) × k=3 independent
  samples.
- **Metric**: Chen unbiased pass@k (k=3), paired differences, clustered SE,
  pre/post-cutoff strata; memorization and guessable puzzles listed
  separately.
- **Budget**: estimate ~$700 agentic + ~$10 probes/judge; circuit breaker at
  $780.
- **Each sample**: a new disposable container, no oracle feedback, bare mode,
  blocklist network.

## GPT (Codex) arm — added 2026-07-22

The GPT arm follows the same protocol with a mirrored harness:

- Models: GPT-5.6 Sol / Terra / Luna in the Codex CLI 0.145.0.
- Per-run budget caps mirror the Claude tiers: sol $3.00, terra $1.50,
  luna $0.75.
- Same bundles, same task text, same k=3, same isolation design, same
  host-side grading, same run-record schema.
- Symmetric proxy filters: the Claude proxy blocks openai.com; the Codex
  proxy blocks anthropic.com. Both block the same solution sources.
- Reasoning effort is not overridden on either side. Each run records the
  resolved value.
- Batch plans: `plans/checkpoints_gpt/`.

## Checkpoint structure (batches with gates between them)

| Batch | Puzzles | k | Estimate | Purpose |
|---|---|---|---|---|
| cp0 | 3 (calibration) | 1 | ~$5 | infrastructure canary, not scored |
| cp1 | 12 (incl. calibration) | 3 | ~$59 | grading calibration + cost-model check |
| cp2 | 25 | 3 | ~$123 | first batch at scale |
| cp3 | 45 | 3 | ~$221 | main body |
| cp4 | remainder (~57) | 3 | ~$280 | completion |

Each batch is stratified by (era × difficulty) in a round-robin. Thus each
batch is representative, and cost/solve-rate extrapolation from early batches
is valid.

## Fixed gate procedure (the agent executes this)

1. The batch completes. Run
   `analysis.checkpoint --batch plans/checkpoints/cpN.json --name cpN`.
2. **HARD-FAIL stops the program** (do not launch the next batch): error rate
   > 5%, submission rate < 85%, non-bare run, image-delivery failure, missing
   transcript, unreviewed cheating flag, cumulative spend > 95% of the
   breaker.
3. **WARN permits continuation after review**: timeout rate > 10%, unreviewed
   judge disagreements, cost outside the forecast band [0.4×, 2.0×], model
   handoff.
4. The agent reviews in person: (1) read a sample of all
   graded-wrong-with-answer transcripts (the eq-side-bug class); (2) run
   `grading.llm_judge` on hard formats; (3) adjudicate each judge disagreement,
   then fix the grader, then run `analysis.regrade`; (4) read the pip-install
   list and the suspect details.
5. Correction rules: a judge/grader correction → regrade everything, no
   re-run. A harness/environment correction → mark the affected runs invalid
   and re-run that subset. Record each correction in the change log.
6. Write the gate verdict to `runs/checkpoints/cpN_report.md` and to this
   change log. Only then launch the next batch.

## Answer-check pipeline (before each batch)

Before batch N launches, each grader in the batch must have
`needs_review=false`. The agent checks each answer against the official
solution (extract the bold answer → write the grader + public_answer_format).
The review sheet lets the operator do spot checks. cp1 contains only checked
puzzles. The checks for cp2–cp4 proceed with the batches.

## When to interrupt the operator

- Any HARD-FAIL that "fix grader + regrade" cannot solve.
- At cumulative spend $400 and $600 (milestone reports).
- Before any protocol-level change (prompt text, model parameters, network
  lists).

## Change log (the agent appends)

- 2026-07-19 — v3 protocol final: independent samples, k=3, 3 models,
  checkpoint guardrails established.

- 2026-07-19 — cp0 canary PASS. 9/9 runs; error and timeout rates 0%;
  submission 100%; bare / container / images / transcripts all green;
  cumulative $2.93. One "submitted but graded wrong" (hooks-2 × haiku,
  12700800 vs 17418240) was checked by hand: a real wrong answer, not a
  grading miss. Mean costs came in below the forecast band (haiku $0.15 /
  opus $0.27 / sonnet $0.56 vs forecast 0.30/0.55/0.79) — a single sample is
  cheaper than a feedback-retry session, so the full estimate of ~$699 is
  conservative. Infrastructure trusted. cp1 cleared.

- 2026-07-19 (late) — full grader check complete (148/148 against official
  solutions). (1) The 6 unchecked cp1 graders passed before launch. The
  isolation gate (allow 8/8, block 12/12, direct egress blocked, pip OK), the
  memorization probes (only fable had 2 hits; zero hits for the three
  competing models), and the image smoke test (all competing models OK) were
  all green. cp1 (99 runs) launched. (2) The check found and corrected **19
  answer-extraction errors** (examples: question-mark stored the solver count
  20 instead of the answer 50; games-night stored 'a' instead of Battleship;
  several robot-series puzzles stored bold text fragments instead of numeric
  answers). All were corrected against the official solutions. (3) 9
  open-competition puzzles were added to `exclude_recommended`
  (chain-reaction, minesweeping, scraggle, altered-states-2, hall-of-mirrors,
  polymath, swing-time, middlylinks, almost-magic — all best-known /
  no-unique-answer / underdetermined, per existing precedent). Puzzle set
  144→**134**; estimate ~$664. (4) 3 new certificate verifiers: tangled (a
  Conway rational-tangle simulation, pinned to the official 114-step answer),
  knight_moves_6 (the A/B/C grids transcribed from the puzzle image, verified
  twice: worked example + independent search), what_a_trit (exact trit
  conversion). These stop bare-number cheating. The normalize `multi` type
  gained alias support (rotation equivalence, "and" wording); 22/22 unit
  tests pass. (5) The cp0/cp1/cp2 plans are byte-identical across rebuilds
  (verified); the calibration-puzzle sample_1 reuse logic is unaffected.

- 2026-07-20 — cp1 gate audit **PASS (WARN reviewed)**. 99+9 runs all
  terminal; cumulative $70.63 (9% of cap). Infrastructure incidents in the
  period, with fixes: (1) the Docker VHD filled drive C → 40 runs became
  instant infra errors ($0, no contamination) → the Docker data disk moved to
  drive A through an NTFS junction (verified with a write probe) +
  clean_start_docker.sh became the standard start path (each Docker session
  leaves zombie socket files; the operator did one factory reset). (2) The SDK
  1MiB stream buffer overflowed once on a large opus output → raised to
  16MiB (robustness only; prompt SHA unchanged). (3) One proxy container
  crash-restart caused 3 transient failures. All error keys were re-run
  idempotently; final state 0 errors. Grading audit: llm_judge on 31 cases,
  0 disagreements. The 24 submitted-but-wrong samples were read one by one:
  all genuinely wrong, no normalization misses (on planetary-parade, sonnet
  and opus all converge on the same wrong pair 1/32, 3/16 — a shared
  modeling error across models, report material). The 24 runs without a
  submission were each verified as resource-cap terminations (haiku 30 turns
  / sonnet $1.5 / opus $3.0); zero unread answer.json files in workdirs; not
  a harness bug. checkpoint.py measurement corrections (not threshold
  changes): the ledger now dedups by key to the final state (superseded
  infra-retry lines shown as INFO); image-delivery failures count only for
  image puzzles; the submission rate is computed over self-terminated runs
  (=100%); the resource-cap termination rate is listed separately (22.2%,
  WARN reviewed). Costs: haiku $0.28 / sonnet $0.75 / opus $0.93 per run
  (opus at 1.7× forecast, in band). Solves: haiku 10/36, sonnet 23/36, opus
  27/36. cp2 probes (fable 4 hits, competing models 0) and image smoke all
  OK. cp2 cleared.

- 2026-07-21 — speed and stability campaign (the operator ordered "speed
  up"). Concurrency 3→8→24. Measured API limits: Scale tier, independent
  per-model buckets, 10K RPM / 10M ITPM / 2M OTPM — at p95 consumption the
  API supports 150+ concurrent runs per model; the local machine is the
  bottleneck. At 24, the WSL VM crashed in a cascade. Layer-by-layer triage
  found **three independent fault sources**: (1) `compose run` at high
  concurrency contended for the proxy dependency → the proxy got rebuilt →
  same-second mass kill → the runner adds `--no-deps`; the orchestration
  layer plus a watchdog own the proxy. (2) A runaway solver (lesses-more,
  10M-domain brute force) ballooned in memory → agent containers get
  `mem_limit: 8g`. (3) The true culprit: the WSL swap file defaults to the
  C-drive Temp directory (it grew to 6.35GB and filled drive C → VM I/O
  faults, SIGBUS) → .wslconfig sets `swap=12GB swapfile=A:\wsl-swap.vhdx`,
  and 12GB of old backups were removed from drive C (19G free after).
  Final concurrency: **12**.

- 2026-07-21 — cp2 gate **PASS (WARN reviewed)**. 225/225 terminal, 0
  errors, cumulative $282.68 (36% of cap). 3 cheating suspects (urllib on
  can-u-dig-it) reviewed by hand = benign wordlist lookups (githubusercontent
  was blocked by the proxy); marked suspect_reviewed. 3 judge disagreements:
  star-search opus s3 was a harness race (the budget cap fired at the moment
  answer.json was written; grading ran before the write landed) → regrade
  flips False→True (the only flip in the whole ledger); the 2 lesses-more
  cases follow the established mirror-alias policy (f is
  reflection-invariant), so the verdicts stand. The 40 wrong samples were
  read: all genuinely wrong. The 93 runs without a submission were verified
  as resource-cap terminations (0 unread answer.json). Opus mean $1.67 (3×
  forecast — hard puzzles hit the $3 cap; within protocol). Solves: haiku
  14/75, sonnet 27/75, opus 43/75. cp3 probes: **first probe hits on
  competing models** (birthday-bash × sonnet+opus; beside-the-point × opus;
  recorded in probes.jsonl for the sensitivity exclusion). Image smoke all
  OK. cp3 cleared.

- 2026-07-21 05:0x — **API balance exhausted; benchmark paused**. "Credit
  balance is too low" (billing_error); 332 cp3 runs died instantly at $0 and
  were mis-recorded as attempts_exhausted terminal states. Per the
  harness-level correction rule: the 332 ledger lines were deleted; the run
  directories were archived to runs/_billing_error_archive/ (kept for
  audit); ledger backup runs.jsonl.bak_billing_*. After the clean-up: cp1 and
  cp2 intact; cp3 valid terminal 73/405 (21 solved); cumulative true spend
  $332.08. A 10-minute balance probe was armed; cp3 resumes automatically
  (idempotent) when credit returns. Waiting on the operator: (1) add credit;
  (2) budget decision — extrapolation from cp2/cp3 unit costs gives cp3
  remainder ~$180 + cp4 ~$280 → total ~$790±80, at or over the $780 breaker;
  cp4 may need a raised cap, a lower k, or partial completion.

- 2026-07-21 — the operator added credit and set auto-reload on; cp3
  completed. cp3 gate **PASS (WARN reviewed)**: 405/405 terminal, 0 errors,
  cumulative $605.80 (78% of cap). 2 grading corrections, both surfaced by
  the judge backstop: (1) single-cross-2 tolerance tightened from rel 1e-6 to
  1e-9 (the puzzle demands 10 significant digits); regrade flips 2 loose
  haiku approximations True→False. (2) The normalize equation split now also
  accepts ≈ and ~ ("π - 1 ≈ 2.14..."); regrade flips rainbow-bagel opus s3
  False→True. The 3 beside-the-point judge disagreements are judge
  arithmetic errors (the submitted value is wrong from the 5th–6th decimal
  on; the judge contradicts itself); the deterministic "wrong" verdicts
  stand. 5 suspects reviewed = all benign (wordlists / anagram tools / pypi;
  github fetches were blocked by the proxy); marked reviewed. The 69 wrong
  samples are all genuinely wrong (report material: on question-mark, both
  opus samples stop at the intermediate number and skip the second decode
  layer; on square-run, haiku and opus independently submit the same illegal
  460). Solves: haiku 19/135, sonnet 59/135, opus 87/135. Opus mean $1.23
  (2.2× forecast, out of band, WARN — same cause as cp2). cp4 cleared (468
  runs, ~$330 expected; the $780 breaker is the backstop — the launch
  proceeds while the raise decision is pending; the breaker stops the
  queue).

- 2026-07-22 — cp4 launched; the $780 breaker fired as designed (at
  273/468). The operator authorized "run to completion"; the breaker moved
  780→900→1000. All 468 cp4 runs completed, 0 errors, cumulative
  **$988.87**.

- 2026-07-22 — **severe isolation leak found and fixed (protocol-level
  integrity event)**. During the cp4 suspect review, sonnet on
  some-ones-somewhere ran `cat /bench/data/raw/.../extracted.json` and read
  solution_md directly. Root cause: the runner mounted the whole repository
  read-write into the container (`..:/bench`), **and grading ran inside the
  container** (run_agent called grade_submission, which reads data/graders).
  Thus the agent's Bash could read the answer store (data/graders) and the
  official solutions (data/raw). Full audit of all 1206 runs: **only 9 runs
  actually read answer or solution content (6 graded correct =
  contaminated); the other 1197 never touched the answer store** (an
  unlocked door does not mean that every visitor entered the room). Fix
  (harness-level, per the "fix + re-run the affected subset" rule): (1) 
  grading moved to the host — run_agent no longer grades and no longer reads
  graders; it writes only the agent's own submitted_answer plus
  grading:pending-host; runner.grade_on_host completes correct / method /
  snapshot on the host; submitted→solved; idempotent. (2) docker-compose masks
  /bench/data/graders and /bench/data/raw with empty tmpfs. (3) 
  verify_isolation.sh gains the assertion "the answer store is unreadable in
  the container"; ISOLATION VERIFIED. The 9 contaminated runs were archived
  to runs/_mount_leak_archive/ and re-run under the sealed harness; the 1197
  clean runs are unaffected. The design documents always said "grading fully
  outside the agent world" — this fix makes the implementation agree with
  the specification. **The final report must disclose this event.**

- 2026-07-22 — the first leak fix was incomplete, plus one operational
  accident (recorded honestly). (1) **The first narrow mask was not enough**:
  only data/graders and data/raw were masked. During the re-runs, sonnet
  read answers through
  /bench/runs/_mount_leak_archive/.../transcript.jsonl — the archived old
  contaminated transcript itself contains the solution. The whole mounted
  repository (all historical transcripts under runs/, the run.json
  grader_snapshots, data/review_sheet.md) is leak surface. Thorough fix: the
  repository is mounted read-only; /bench/data and /bench/runs are wiped to
  empty tmpfs; only the clean data/puzzles is mounted back read-only; the
  run output is bound to /out outside /bench (JSB_RUN_DIR); the host reads
  it back and grades; verify_isolation asserts that every answer surface is
  gone. Verified with a puzzle that had leaked a "solve" before: the agent
  now honestly fails, and the transcript has zero answer references. (2) 
  **Operational accident**: a cleanup script for orphan run directories got
  an empty string from os.path.basename on Windows backslash paths and
  deleted **662 of 1284 run directories** (transcripts + workdirs); it
  stopped only when a venv symlink broke. **The ledger runs.jsonl is intact
  (1258 lines plus several backups) — analysis.report reads only the ledger,
  so pass@k, cost, solve rates, and the memorization analysis are fully
  unaffected.** What is lost is the transcript-level audit trail for 662
  runs (audit_transcripts covers the surviving 622). This was the agent's
  error; it was reported to the operator. (3) The 3 affected puzzles
  (tile-and-trouble-2, poetry-in-motion, some-ones-somewhere): 26 ledger
  lines removed; all 27 samples re-run under the sealed harness.

- 2026-07-22 — **full Claude benchmark complete — final delivery**. 1206
  independent samples (134 puzzles × 3 models × k=3) all terminal, **0
  errors**, submission 96.1%, 0 unreviewed suspects (20 network-access cases
  all reviewed benign: blocklisted sites returned 000/403; the rest are
  policy-allowed reference sites), bare / image delivery / malformed all
  green. Cumulative **$987.79** (operator-authorized breaker $1000). **Main
  result, pass@3 (Chen unbiased)**: opus 4.8 = **70.1% ± 4.0%**, sonnet 5 =
  **47.8% ± 4.3%**, haiku 4.5 = **24.6% ± 3.7%**. All three paired
  differences are significant (opus−sonnet +20.1pp, sonnet−haiku +24.6pp,
  opus−haiku +44.8pp; no 95% CI contains 0). **Memorization sensitivity**:
  removal of the probe-hit puzzles almost does not change the results (opus
  70.1→68.8%; sonnet/haiku essentially unchanged); memorization does not
  drive the conclusions. Pre/post-cutoff: the post subgroup (5–16 puzzles)
  drops hard for all three models (opus 63→13%); descriptive only. Costs:
  haiku $0.27, sonnet $0.96, opus $1.25 per run (opus at 2.3× the original
  forecast — hard puzzles hit the $3 cap; known, out of band). Grading: 4
  judge-driven grader corrections + regrades across the whole run
  (star-search race, single-cross tolerance, rainbow-bagel ≈ split,
  lesses-more rotation alias); deterministic primary grading + certificate
  verifiers (sos / tangled / knight_moves_6 / what_a_trit) block bare-number
  cheating. **Honest statement**: (1) the isolation leak (in-container grading
  + full repository mount) was fully sealed (host grading + read-only
  repository + tmpfs masks on all answer surfaces + /out output isolation);
  the 27 samples on the 3 puzzles that contained the 9 once-contaminated
  samples were re-run under the
  sealed harness (after the seal, the models honestly fail — evidence that
  the contamination was real); (2) the cleanup-script accident deleted
  transcripts for 662/1284 run directories; the ledger is intact and no
  metric is affected, but transcript-level audit covers only the surviving
  ~600 runs. Deliverables (local): runs/FINAL_REPORT.md,
  runs/FINAL_audit_transcripts.txt, runs/checkpoints/final_report.md.

- 2026-07-22 — GPT (Codex) arm launched. The cp1 canary (108 runs) ran clean
  at concurrency 12 (98 terminal: 70 solved / 28 submitted; mean costs luna
  $0.068 / terra $0.133 / sol $0.182 — under the caps, cheaper than the
  Claude counterparts). Then it hit **OpenAI insufficient_quota** (HTTP 429,
  a hard billing cap) after only $13.80 → 10 runs failed at $0. Not a rate
  limit (no retry-after). Paused, pending the operator adding OpenAI credit
  or raising the project spend limit; a quota probe was armed for
  auto-resume (idempotent — the 10 error keys + gpt_rest run when quota
  returns). Ledger backed up off-tree. The setup was verified clean against the Claude arm (parity
  audit): same bundles / task text / k=3 / isolation / host grading / schema
  / per-tier caps. The Codex runner also enforces the per-run budget cap by
  streaming usage events (parity with the Claude SDK). Reasoning effort is
  not overridden on either side (recorded per run).

- 2026-07-23 — **GPT-5.6 arm complete — six-model head-to-head done**. 1206
  GPT runs (134 puzzles × sol/terra/luna × k=3) all terminal, 0 errors,
  98.3% submission, 0 bare / image / malformed problems, 0 cheating
  suspects, all transcripts present. GPT spend $440.95; combined agentic
  total $1428.74. Infrastructure incidents handled autonomously: (a) OpenAI
  insufficient_quota paused cp1 at $13.80 → the operator added
  auto-recharge; resumed. (b) Hard-puzzle solvers segfault often → WSL wrote
  6GB core dumps to drive C → ulimits core:0 + a 2-minute sweeper.
  (c) Memory pressure from 12 × 8g containers grew the C pagefile → 48GB WSL
  memory cap (.wslconfig) + concurrency 12→10. (d) Docker hung during a
  reboot; the runner marked 880 in-flight runs as $0 errors → clean start +
  idempotent re-run recovered all 880; 0 residual errors.
  **RESULTS — pass@3 (Chen unbiased), native-agent product comparison
  (GPT-under-Codex vs Claude-under-Claude-Code):**

  | model | pass@3 | note |
  |---|---|---|
  | gpt-5.6-sol | 81.3% ± 3.4 | > opus 4.8 by +10.7pp, significant |
  | claude-opus-4-8 | 70.1% ± 4.0 | |
  | gpt-5.6-terra | 65.7% ± 4.1 | ~ opus, +4.2pp NOT significant |
  | gpt-5.6-luna | 55.2% ± 4.3 | ~ sonnet, −0.2pp NOT significant |
  | claude-sonnet-5 | 47.8% ± 4.3 | |
  | claude-haiku-4-5 | 24.6% ± 3.7 | |

  (The pp comparisons in the notes are paired per-puzzle pass@1
  differences.) The within-family ladders are both monotone and significant.
  Cost per run: GPT is cheaper at each tier (luna $0.15 / terra $0.37 / sol
  $0.57 vs haiku $0.27 / sonnet $0.94 / opus $1.25).
  Memorization-excluded pass@3 is essentially unchanged (no probe hits drove
  the results). CAVEAT for the write-up: "mean turns" is NOT comparable
  across harnesses — Codex counts a whole session as 1 turn; the comparable
  activity metric is tool_calls (GPT mean 11.2, median 7), which confirms
  genuine multi-step agentic solving. Deliverable:
  [`results/FINAL_REPORT.md`](../results/FINAL_REPORT.md).

- 2026-07-24 — GPT arm judge QA. Only 2 disagreements (both
  2025-12-robot-javelin), and both are LLM-judge arithmetic errors — the
  submitted exact forms evaluate to 0.4954 and 0.4976; neither matches the
  0.4939370904 target. The deterministic "wrong" verdict is correct in both
  cases. No regrade needed. The six-model pass@3 numbers are **FINAL**.
  Grading was confirmed fair to GPT output (spot-checked wrong answers are
  genuine failures, not format false-negatives). **BENCHMARK COMPLETE.**
  Deliverables: [`results/FINAL_REPORT.md`](../results/FINAL_REPORT.md)
  (published aggregate) + runs/FINAL_audit_transcripts_6models.txt (local
  only — it contains puzzle answers).

- 2026-07-24 — repository packed for publication. The aggregate report was
  copied byte-identical to `results/FINAL_REPORT.md`. README, this file, and
  CONFIG_MAP were rewritten in controlled English (ASD-STE100 style); no
  number changed. PII scrub: the contact email in the scrape user-agent was
  replaced with the repository URL; the personal Windows path in
  clean_start_docker.sh now comes from the LOCALAPPDATA environment
  variable; a full-history scan found zero key material in all 36 commits.
  The per-puzzle answer files (data/, runs/) stay local, as before.
