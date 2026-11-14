# Results — eval set

Calls scored: 300 pairs. Prompt template frozen. Malformed output is counted as a failure (intention-to-treat).

**Primary outcome.** Structural match with the reference fix: both snippets parse and their syntax trees are identical, ignoring line numbers, column offsets, formatting and comments. This measures agreement with the reference repair, not semantic correctness — an alternative but equally valid repair counts as a non-match.

## Per-arm outcomes

| measure | natural | synthetic |
|---|---:|---:|
| calls present | 300 | 300 |
| **structural match with reference fix (primary)** | 289 | 283 |
| parses (syntactic validity) | 298 | 297 |
| detection: family correct | 289 | 282 |
| detection: line correct | 226 | 236 |
| detection: family and line | 219 | 225 |
| text match to reference fix | 248 | 268 |

Rates (denominator = calls present):

| measure | natural | synthetic |
|---|---:|---:|
| structural match with reference fix (primary) | 96.3% | 94.3% |
| parses (syntactic validity) | 99.3% | 99.0% |
| detection: family correct | 96.3% | 94.0% |
| detection: line correct | 75.3% | 78.7% |
| text match to reference fix | 82.7% | 89.3% |

## Detection-to-repair gap (per arm)

| arm | family detection | parses | structural match | gap vs match (pp) |
|---|---:|---:|---:|---:|
| natural | 96.3% | 99.3% | 96.3% | +0.0 |
| synthetic | 94.0% | 99.0% | 94.3% | -0.3 |

## Primary contrast — paired difference in structural match with the reference fix

| Quantity | Value |
|---|---:|
| complete non-identical pairs | 300 |
| natural match rate | 0.963 |
| synthetic match rate | 0.943 |
| **paired difference (natural − synthetic)** | **+0.020** |
| 95% CI (bootstrap percentile, 10k) | [-0.010, +0.050] |
| discordant: natural-only | 14 |
| discordant: synthetic-only | 8 |
| **McNemar exact p (confirmatory)** | **0.2863** |

No Wald interval is reported. It collapses to a single point when discordance is zero, and it diverges from the exact test at the boundary; reporting it would invite selecting whichever interval looks favourable.

## Pre-specified strata (paired risk difference)

### By within-family length tertile

| tertile | pairs | paired difference | 95% CI (bootstrap) |
|---|---:|---:|---|
| long | 99 | -0.020 | [-0.071, +0.030] |
| medium | 99 | +0.051 | [-0.010, +0.111] |
| short | 102 | +0.029 | [-0.020, +0.078] |

### By error family (descriptive, not confirmatory)

| family | pairs | paired difference | 95% CI (bootstrap) |
|---|---:|---:|---|
| BRACKET_MISMATCH | 41 | -0.073 | [-0.171, +0.000] |
| MISSING_CLOSER | 51 | +0.196 | [+0.078, +0.314] |
| MISSING_COLON | 42 | +0.000 | [+0.000, +0.000] |
| MISSING_COMMA | 42 | +0.000 | [+0.000, +0.000] |
| PRINT_STATEMENT | 45 | +0.000 | [+0.000, +0.000] |
| QUOTATION | 79 | -0.013 | [-0.076, +0.051] |

## Sensitivity: exclude snippets of 2 lines or fewer

| pairs | paired difference | 95% CI (bootstrap) | McNemar exact p |
|---:|---:|---|---:|
| 214 | +0.014 | [-0.019, +0.051] | 0.6072 |

## Note on interpretation

The evaluation sample is a **balanced analytical sample**, not a prevalence-weighted estimate of the 62,882-pair corpus: every family holds a floor of pairs, so the pooled rates describe this design rather than the corpus's natural mix.
