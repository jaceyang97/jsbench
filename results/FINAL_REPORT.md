# jsbench results

## PRIMARY: pass@k (unbiased estimator) ± SEM

| model | k | pass@k | SEM | pass@1 | puzzles | runs | excl. memorized pass@k | suspect runs |
|---|---|---|---|---|---|---|---|---|
| claude-haiku-4-5-20251001 | 3 | 24.6% | 3.7% | 16.7% | 134 | 402 | 24.6% (n=134) | 8 |
| claude-opus-4-8 | 3 | 70.1% | 4.0% | 61.4% | 134 | 402 | 68.8% (n=128) | 0 |
| claude-sonnet-5 | 3 | 47.8% | 4.3% | 41.3% | 134 | 402 | 47.4% (n=133) | 12 |
| gpt-5.6-luna | 3 | 55.2% | 4.3% | 41.5% | 134 | 402 | 55.2% (n=134) | 0 |
| gpt-5.6-sol | 3 | 81.3% | 3.4% | 72.1% | 134 | 402 | 81.3% (n=134) | 0 |
| gpt-5.6-terra | 3 | 65.7% | 4.1% | 57.2% | 134 | 402 | 65.7% (n=134) | 0 |

## cross-model pass@3 (common k)

- claude-haiku-4-5-20251001: 24.6% ± 3.7% (134 puzzles)
- claude-opus-4-8: 70.1% ± 4.0% (134 puzzles)
- claude-sonnet-5: 47.8% ± 4.3% (134 puzzles)
- gpt-5.6-luna: 55.2% ± 4.3% (134 puzzles)
- gpt-5.6-sol: 81.3% ± 3.4% (134 puzzles)
- gpt-5.6-terra: 65.7% ± 4.1% (134 puzzles)

## paired differences (A − B, same puzzles)

| A | B | Δ | SEM | 95% CI | corr | sig? |
|---|---|---|---|---|---|---|
| claude-haiku-4-5-20251001 | claude-opus-4-8 | -44.8pp | 3.8pp | [-52.2, -37.3] | 0.36 | YES |
| claude-haiku-4-5-20251001 | claude-sonnet-5 | -24.6pp | 3.3pp | [-31.2, -18.1] | 0.56 | YES |
| claude-haiku-4-5-20251001 | gpt-5.6-luna | -24.9pp | 3.1pp | [-30.9, -18.9] | 0.59 | YES |
| claude-haiku-4-5-20251001 | gpt-5.6-sol | -55.5pp | 3.7pp | [-62.8, -48.1] | 0.29 | YES |
| claude-haiku-4-5-20251001 | gpt-5.6-terra | -40.5pp | 3.8pp | [-47.9, -33.2] | 0.42 | YES |
| claude-opus-4-8 | claude-sonnet-5 | +20.1pp | 3.1pp | [+14.1, +26.2] | 0.69 | YES |
| claude-opus-4-8 | gpt-5.6-luna | +19.9pp | 3.1pp | [+13.8, +26.0] | 0.66 | YES |
| claude-opus-4-8 | gpt-5.6-sol | -10.7pp | 2.8pp | [-16.3, -5.1] | 0.70 | YES |
| claude-opus-4-8 | gpt-5.6-terra | +4.2pp | 2.9pp | [-1.5, +10.0] | 0.72 | no |
| claude-sonnet-5 | gpt-5.6-luna | -0.2pp | 2.5pp | [-5.1, +4.6] | 0.79 | no |
| claude-sonnet-5 | gpt-5.6-sol | -30.8pp | 3.6pp | [-37.8, -23.9] | 0.55 | YES |
| claude-sonnet-5 | gpt-5.6-terra | -15.9pp | 3.0pp | [-21.7, -10.1] | 0.72 | YES |
| gpt-5.6-luna | gpt-5.6-sol | -30.6pp | 3.2pp | [-36.9, -24.3] | 0.60 | YES |
| gpt-5.6-luna | gpt-5.6-terra | -15.7pp | 2.7pp | [-20.9, -10.5] | 0.76 | YES |
| gpt-5.6-sol | gpt-5.6-terra | +14.9pp | 2.8pp | [+9.5, +20.4] | 0.73 | YES |

## pre/post reliable-cutoff split

| model | pre-cutoff pass@1 (n) | post-cutoff pass@1 (n) |
|---|---|---|
| claude-haiku-4-5-20251001 | 17.8% (118) | 8.3% (16) |
| claude-opus-4-8 | 63.3% (129) | 13.3% (5) |
| claude-sonnet-5 | 42.9% (129) | 0.0% (5) |
| gpt-5.6-luna | 42.8% (130) | 0.0% (4) |
| gpt-5.6-sol | 73.8% (130) | 16.7% (4) |
| gpt-5.6-terra | 59.0% (130) | 0.0% (4) |

## cost

| model | runs | total $ | mean $/run | mean turns |
|---|---|---|---|---|
| claude-haiku-4-5-20251001 | 402 | $109.24 | $0.27 | 22 |
| claude-opus-4-8 | 402 | $501.48 | $1.25 | 18 |
| claude-sonnet-5 | 402 | $377.07 | $0.94 | 25 |
| gpt-5.6-luna | 402 | $61.37 | $0.15 | 1 |
| gpt-5.6-sol | 402 | $228.89 | $0.57 | 1 |
| gpt-5.6-terra | 402 | $150.69 | $0.37 | 1 |

**Total agentic spend: $1428.74**

_Power note: with 134 puzzles, the paired-test MDE is roughly ±10pp — only differences larger than this are reliably detectable at this budget._

---

## Open-puzzle back-fill (2026-08-04)

Nine open-competition puzzles were previously excluded from the formal set
because they have no unique answer: four are best-known optimization
competitions (chain-reaction, hall-of-mirrors, polymath, almost-magic), one
is under-determined by Jane Street's own admission (middlylinks), and four
are open-ended scoring competitions where the top score is either not
published or set as a qualifying threshold (minesweeping, swing-time,
scraggle, altered-states-2). They were reinstated on 2026-08-04 under a
compound grader: a deterministic verifier over an envelope
`{"value": ..., "solution": ...}` plus a separate fable trace-check pass. All
runs used the same harness, bundles, and TASK_RULES as the frozen bc57392
set — the only change is the envelope submission form and the
certificate-verifier grader.

Canonical puzzle geometry (16×16 grid + 24 laser entries + 21 goals for
hall-of-mirrors; the 10×10 board of cell values for polymath; the 50 post
positions on the 20×20 board for swing-time; the four 3×3 sub-square anchors
for almost-magic) is pinned by the grader for the four geometry-heavy
puzzles. The deterministic verifier ignores any geometry that the agent
writes into its envelope. This closes the "fabricated geometry" cheating
vector that adversarial review flagged before back-fill launch.

Per-puzzle grading rules:

| puzzle | sense | reference | reference source |
|---|---|---|---|
| 2014-07-chain-reaction    | max   | 77                                 | JS best-known chain length |
| 2014-10-minesweeping      | max   | 38/39 (≈0.9744), P(target) < 1     | JS best received |
| 2015-04-hall-of-mirrors   | max   | 77 points                          | JS best received |
| 2015-06-polymath          | max   | 20,160                             | JS top score |
| 2016-08-swing-time        | none  | 0.7082 (informational)             | JS best received; arc-obstruction not enforced deterministically, so the gate is pass-on-legality only and cost is logged |
| 2017-08-middlylinks       | eq    | 4,293,120                          | JS-published answer; puzzle admitted as under-determined |
| 2019-07-scraggle          | none  | (unpublished top score)            | pass on legality; Scrabble product logged, dictionary check deferred to the trace pass |
| 2022-04-almost-magic      | min   | 470                                | JS best received |
| 2024-06-altered-states-2  | floor | 165,379,868 (JS leaderboard cutoff)| JS never published a top score; floor = half of the maximal 2020-census sum |

The back-fill is 9 puzzles × 6 tiers × k=3 = 162 independent samples.
Terminal spend: **$85.85** (mean-cost forecast was $96.39; worst-case
per-tier caps were $283.50). One OpenAI credit outage hit the GPT arm
mid-run; the runner re-queued the 21 affected keys idempotently and they
finished on retry after the credit was topped up. Per-tier pass rates
on the 9 open puzzles:

| tier | correct | runs | rate |
|---|---:|---:|---:|
| gpt-5.6-sol   | 25 | 26 | 96.2% |
| gpt-5.6-terra | 24 | 27 | 88.9% |
| gpt-5.6-luna  | 22 | 27 | 81.5% |
| claude-opus-4-8    | 20 | 27 | 74.1% |
| claude-sonnet-5    | 18 | 27 | 66.7% |
| claude-haiku-4-5   |  6 | 27 | 22.2% |

Per-puzzle × tier (correct / samples):

| puzzle | haiku | sonnet | opus | luna | terra | sol |
|---|---:|---:|---:|---:|---:|---:|
| 2014-07-chain-reaction    | 0/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 |
| 2014-10-minesweeping      | 0/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| 2015-04-hall-of-mirrors   | 0/3 | 1/3 | 0/3 | 0/3 | 0/3 | 2/3 |
| 2015-06-polymath          | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| 2016-08-swing-time        | 1/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| 2017-08-middlylinks       | 0/3 | 1/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| 2019-07-scraggle          | 1/3 | 2/3 | 2/3 | 2/3 | 3/3 | 3/3 |
| 2022-04-almost-magic      | 1/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| 2024-06-altered-states-2  | 1/3 | 0/3 | 0/3 | 3/3 | 3/3 | 2/2 |

Notes on the 9-puzzle set:

- chain-reaction, minesweeping, polymath, swing-time, middlylinks,
  almost-magic: broadly solved by 5 of 6 tiers; haiku is the outlier
  everywhere.
- hall-of-mirrors: hardest. sol reached 2/3; sonnet 1/3; the other four
  tiers 0/3. This puzzle demands both geometric reasoning (over the
  canonical laser + goal layout the grader ships) and combinatorial
  search over mirror placements.
- altered-states-2: split by arm. All three GPT tiers scored 3/3 or 2/2,
  but on the Claude side only haiku got 1/3 and both opus and sonnet went
  0/3. The task rewards state-name enumeration and small king-move search
  with a US-census scoring; the Codex CLI's default reasoning appears to
  drive this consistently.
- No submission beat the JS-published reference on any of the 161
  terminal runs. The BEATS-REF flag, if it fires, is what the write-up
  gallery will surface for insight review; its absence here says the
  9 open puzzles' JS-published references still stand across the six
  tiers.

Rank ordering on the 9 back-fill puzzles differs from the 134-puzzle
frozen ranking. On the main set the two arms interleave (sol > opus > terra
> luna > sonnet > haiku); on the open set the GPT arm sweeps the top three
places (sol > terra > luna > opus > sonnet > haiku). This is a small
sample (27 or 26 runs per tier) and the differences between adjacent
tiers on the open set are noisy; treat the ordering as suggestive only.

The 6-model ranking on the 134-puzzle formal set is unchanged. The
back-fill is a supplementary arm that reports separately, per methodology.md;
the tables above stay frozen at commit bc57392.

Star note on comparability: the 9 back-fill puzzles are graded by
recompute-from-solution certificate verifiers and, on scraggle and
swing-time, only by legality (see the sense column). Their pass rates are
NOT directly comparable to the deterministic-string grading on the 134 main
puzzles, and the two are not aggregated into a single pass@k.

## Trace check (fable, 2026-08-04)

Fable graded 1818 surviving transcripts on four dimensions from
methodology.md:

Self-verification form (of 1818):

| tag | count | share |
|---|---:|---:|
| two-method-crosscheck  | 575 | 31.6% |
| single-method-recheck  | 698 | 38.4% |
| no-verify              | 478 | 26.3% |
| not-enough-signal      |  67 |  3.7% |

Behavioral / memorization form (of 1818):

| tag | count | share |
|---|---:|---:|
| search-solve            | 1214 | 66.8% |
| multi-round-verifying   |  475 | 26.1% |
| hackiest                |   74 |  4.1% |
| one-shot                |   26 |  1.4% |
| not-enough-signal       |   29 |  1.6% |

Answer-in-turn (of 1818; roughly 275 runs had no submission):

| tag | count |
|---|---:|
| submitted                     | 1542 |
| no-answer-in-trace            |  239 |
| answer-only-in-search-trace   |   22 |
| wrong-conclusion              |   12 |
| answer-stated-as-conclusion   |    3 |

The very small "answer-stated-as-conclusion" bucket (3 runs across the
whole corpus) confirms methodology.md item 5's revised expectation:
rescuing unsubmitted-but-in-turn runs shifts almost nothing.

The Schoenfeld six-episode share and the per-run insight notes live in
`runs/trace_check.jsonl` (local — the file also carries the run's
puzzle-title, tier, and correctness for later slicing). 1192 of the 1818
runs came back with a non-empty insight note; that number is closer to a
"gallery candidate list" than a curated selection — the write-up will still
filter down to a small hand-picked set.
