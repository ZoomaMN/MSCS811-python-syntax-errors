# Natural vs. rule-generated Python syntax errors: a paired evaluation of two LLM services

Code, data, model responses and analysis for the MSCS811 course paper
*"Do LLM Services Repair Natural and Rule-Generated Python Syntax Errors Equally?
A Paired Evaluation with Verified Error Pairs"* (H. M. Alhazmi, Taibah University, 2026).

Each of 300 pairs contains a natural syntax error from Stack Overflow, a rule-generated
error injected into the same human-corrected code, and that human correction as the shared
reference. Before sampling, both errors in every pair were verified to require one isolated
repair of the same error family. DeepSeek and Claude each received all 600 snippets in
separate requests, and their repairs were compared with the reference by AST agreement.

## Main results (300 pairs per arm)

| Outcome | DeepSeek natural / synthetic | Δ [95% CI], p | Claude natural / synthetic | Δ [95% CI], p |
|---|---|---|---|---|
| Reference AST agreement (primary) | 96.3% / 94.3% | +2.00 [−1.00, +5.00], 0.29 | 94.3% / 96.3% | −2.00 [−4.67, +0.67], 0.21 |
| Parsing success | 99.3% / 99.0% | +0.33 [−0.67, +1.67], 1.00 | 99.3% / 99.7% | −0.33 [−1.67, +0.67], 1.00 |
| Normalized text agreement | 82.7% / 89.3% | −6.67 [−11.33, −2.00], 0.0078 | 82.3% / 92.0% | −9.67 [−14.00, −5.67], 9.0e−6 |

Δ = natural minus synthetic, in percentage points; p = exact McNemar test.
All figures are in `results/stats.json`.

## Repository layout

```
src/        pipeline, scoring and figure scripts (Python standard library; matplotlib for figures)
data/       validated pairs, eligible pool, evaluation sample and rendered prompts
results/    raw model responses, run manifests, per-pair outcomes and stats.json
figures/    Figures 1-3 of the paper
```

| Step | Script | Output |
|---|---|---|
| 1. Load the corpus and recheck it under Python 3.12 | `src/data_loader.py` | `pairs.jsonl` |
| 2. Assign families, inject synthetic errors, apply thresholds | `src/validate_pairs.py` | `data/validated_pairs.jsonl` (6,327 pairs) |
| 3. Exclude previously used pairs and the keyword family; verify isolated repairs | `src/build_pool.py`, `src/verifier.py` | `data/eligible_pairs.jsonl` (2,285 pairs), `data/pool_report.json` |
| 4. Draw the sample (seed 20261114) | `src/sample_pairs.py` | `data/sample.jsonl` (300 pairs) |
| 5. Render prompts | `src/build_prompts.py`, `src/prompt.txt` | `data/eval_prompts_{natural,synthetic}.jsonl` |
| 6. Query the services | `src/run_deepseek.py`, `src/run_claude.py`, `src/run_claude_parallel.py` | `results/*/eval_results.jsonl`, `eval_run_manifest.json` |
| 7. Score responses | `src/score_results.py`, `src/output_parser.py` | `results/*/eval_pair_outcomes.csv` |
| 8. Paired statistics and figures | `src/compute_stats.py`, `src/make_figures.py`, `src/make_framework_figure.py` | `results/stats.json`, `figures/` |

`data/excluded_ids.txt` lists previously used pairs, excluded to prevent reuse.

Six third-party access tokens that appear in public Stack Overflow snippets in
`data/validated_pairs.jsonl` were replaced with `REDACTED_TOKEN`. None of these pairs is in the
eligible pool, and the pool, sample and results are unchanged.

## Reproducing the analysis (no API key needed)

Python 3.12 is recommended. Run from the repository root:

```
python src/build_pool.py data/validated_pairs.jsonl data
python src/sample_pairs.py --matched data/eligible_pairs.jsonl --out data
python src/build_prompts.py --out data
python src/score_results.py --out results/deepseek --sample data/sample.jsonl --matched data/eligible_pairs.jsonl
python src/score_results.py --out results/claude   --sample data/sample.jsonl --matched data/eligible_pairs.jsonl
python src/compute_stats.py
pip install matplotlib
python src/make_figures.py
python src/make_framework_figure.py figures/fig1_framework.png
```

These commands regenerate the eligible pool, sample, prompts, per-pair outcomes and
`results/stats.json` byte-for-byte from the files in this repository.

To rebuild `data/validated_pairs.jsonl` from the original corpus, download
*Python3.6 Natural Syntax Errors and Corrections* (version 1,
doi:10.6084/m9.figshare.8244686.v1) into `raw/`, then run
`python src/data_loader.py --data raw --out work` and
`python src/validate_pairs.py --pairs work/pairs.jsonl --out work`; the resulting
`work/matched_pairs.jsonl` corresponds to `data/validated_pairs.jsonl`.

## Re-running the model requests (optional)

Requires your own API keys, set as environment variables (never commit keys):

```
DEEPSEEK_API_KEY=...  python src/run_deepseek.py --set eval --out <folder with prompts>
ANTHROPIC_API_KEY=... python src/run_claude_parallel.py <folder with prompts>
```

Settings: DeepSeek `deepseek-flash`, temperature 0, thinking disabled; Claude
`claude-sonnet-5-5`, provider default temperature, high effort; 4,096 output tokens for both.
New requests will not reproduce the archived responses exactly.

The run manifests are kept as recorded; `run_claude_parallel.py` appears there under its
run-time name `par_claude.py`.

## Data source

Natural errors and human corrections come from A. Wong, A. Salimi, S. Chowdhury and
A. Hindle, *Python3.6 Natural Syntax Errors and Corrections*, figshare, 2019,
doi:10.6084/m9.figshare.8244686.v1. Please cite the original dataset when reusing it.
