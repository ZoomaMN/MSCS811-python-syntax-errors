# Sample report

Frozen seed: `20261114`  |  evaluation pairs: 300  |  development pairs: 0

The sample is not re-drawn for any reason. Pair IDs are fixed in `sample_manifest.json`.

Contamination guards: **0** previously used pair_ids excluded (listed in `excluded_ids.txt`), and **0** literal-identical pairs excluded.

## Allocation

| family | pool | floor | allocated | drawn | pool share | sample share |
|---|---:|---:|---:|---:|---:|---:|
| QUOTATION | 1480 | 40 | 79 | 79 | 64.8% | 26.3% |
| MISSING_CLOSER | 403 | 40 | 51 | 51 | 17.6% | 17.0% |
| PRINT_STATEMENT | 201 | 40 | 45 | 45 | 8.8% | 15.0% |
| MISSING_COMMA | 80 | 40 | 42 | 42 | 3.5% | 14.0% |
| MISSING_COLON | 68 | 40 | 42 | 42 | 3.0% | 14.0% |
| BRACKET_MISMATCH | 53 | 40 | 41 | 41 | 2.3% | 13.7% |

## family x length tertile (evaluation sample)

| family | short | medium | long | total |
|---|---:|---:|---:|---:|
| QUOTATION | 27 | 26 | 26 | 79 |
| MISSING_CLOSER | 17 | 17 | 17 | 51 |
| PRINT_STATEMENT | 15 | 15 | 15 | 45 |
| MISSING_COMMA | 14 | 14 | 14 | 42 |
| MISSING_COLON | 14 | 14 | 14 | 42 |
| BRACKET_MISMATCH | 15 | 13 | 13 | 41 |

## Length tertile boundaries (computed inside each family, on the pool)

| family | short <= | medium <= | long > |
|---|---:|---:|---:|
| QUOTATION | 2 | 7 | 7 |
| MISSING_CLOSER | 2 | 5 | 5 |
| PRINT_STATEMENT | 3 | 8 | 8 |
| MISSING_COMMA | 2 | 9 | 9 |
| MISSING_COLON | 11 | 19 | 19 |
| BRACKET_MISMATCH | 2 | 4 | 4 |

## Continuous length in the evaluation sample

| Quantity | lines | characters |
|---|---:|---:|
| median | 5.0 | 168.5 |
| p10 | 1 | 56 |
| p90 | 21 | 654 |
| max | 147 | 5799 |

## Why this sample is not prevalence-representative

The floor gives every family at least 40 pairs, so large families are under-weighted relative to the pool. Any overall success rate is therefore a **balanced-sample** estimate, not a corpus-level estimate. Family-level rates are descriptive; the confirmatory test is the paired contrast.
