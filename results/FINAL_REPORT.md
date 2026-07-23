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
