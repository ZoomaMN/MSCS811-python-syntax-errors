# Results — eval set

Calls scored: 300 pairs. Prompt template frozen. Malformed output is counted as a failure (intention-to-treat).

**Primary outcome.** Structural match with the reference fix: both snippets parse and their syntax trees are identical, ignoring line numbers, column offsets, formatting and comments. This measures agreement with the reference repair, not semantic correctness — an alternative but equally valid repair counts as a non-match.

## Per-arm outcomes

| measure | natural | synthetic |
|---|---:|---:|
| calls present | 300 | 300 |
| **structural match with reference fix (primary)** | 283 | 289 |
| parses (syntactic validity) | 298 | 299 |
| detection: family correct | 297 | 291 |
| detection: line correct | 236 | 243 |
| detection: family and line | 235 | 235 |
| text match to reference fix | 247 | 276 |

Rates (denominator = calls present):

| measure | natural | synthetic |
|---|---:|---:|
| structural match with reference fix (primary) | 94.3% | 96.3% |
| parses (syntactic validity) | 99.3% | 99.7% |
| detection: family correct | 99.0% | 97.0% |
| detection: line correct | 78.7% | 81.0% |
| text match to reference fix | 82.3% | 92.0% |

## Detection-to-repair gap (per arm)

| arm | family detection | parses | structural match | gap vs match (pp) |
|---|---:|---:|---:|---:|
| natural | 99.0% | 99.3% | 94.3% | +4.7 |
| synthetic | 97.0% | 99.7% | 96.3% | +0.7 |

## Primary contrast — paired difference in structural match with the reference fix

| Quantity | Value |
|---|---:|
| complete non-identical pairs | 300 |
| natural match rate | 0.943 |
| synthetic match rate | 0.963 |
| **paired difference (natural − synthetic)** | **-0.020** |
| 95% CI (bootstrap percentile, 10k) | [-0.047, +0.007] |
| discordant: natural-only | 5 |
| discordant: synthetic-only | 11 |
| **McNemar exact p (confirmatory)** | **0.2101** |

No Wald interval is reported. It collapses to a single point when discordance is zero, and it diverges from the exact test at the boundary; reporting it would invite selecting whichever interval looks favourable.

## Pre-specified strata (paired risk difference)

### By within-family length tertile

| tertile | pairs | paired difference | 95% CI (bootstrap) |
|---|---:|---:|---|
| long | 99 | -0.051 | [-0.111, +0.010] |
| medium | 99 | -0.020 | [-0.061, +0.020] |
| short | 102 | +0.010 | [-0.020, +0.049] |

### By error family (descriptive, not confirmatory)

| family | pairs | paired difference | 95% CI (bootstrap) |
|---|---:|---:|---|
| BRACKET_MISMATCH | 41 | -0.024 | [-0.073, +0.000] |
| MISSING_CLOSER | 51 | +0.020 | [-0.059, +0.098] |
| MISSING_COLON | 42 | +0.000 | [+0.000, +0.000] |
| MISSING_COMMA | 42 | -0.024 | [-0.071, +0.000] |
| PRINT_STATEMENT | 45 | -0.022 | [-0.067, +0.000] |
| QUOTATION | 79 | -0.051 | [-0.127, +0.013] |

## Sensitivity: exclude snippets of 2 lines or fewer

| pairs | paired difference | 95% CI (bootstrap) | McNemar exact p |
|---:|---:|---|---:|
| 214 | -0.033 | [-0.065, +0.000] | 0.09229 |

## Note on interpretation

The evaluation sample is a **balanced analytical sample**, not a prevalence-weighted estimate of the 62,882-pair corpus: every family holds a floor of pairs, so the pooled rates describe this design rather than the corpus's natural mix.
