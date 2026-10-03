# Reproducing the wave 1 analyses

Everything here runs in base R plus two CRAN packages, on the frozen dataset in `Input/`. The
plan the scripts follow is `ANALYSIS-PLAN.md` (committed before any correlation with the
price was computed); the block table that drives the feature engineering is
`feature_blocks.csv`.

## 1. What you need

- R 4.6 (used: 4.6.1). Base R for everything except ridge, lasso, elastic net (`glmnet`) and
  the random forest (`randomForest`).
- The three files in `Input/`: `subnets_wave1_2026-09-30.csv` (sha256 `9793e83f…`, full value
  in `PLAN.md`), `codebook.csv`, and nothing else.

## 2. Run

From this folder (`Code/analysis`), in a shell:

```bash
Rscript install_packages.R      # once; installs glmnet and randomForest into your user library
Rscript run_all.R               # steps 1 to 7 in order; about 35 minutes, of which the
                                # cross-validation takes 30
```

Or step by step, in this order:

| Script | What it does | Writes to `Output/` | Time |
|---|---|---|---|
| `01_descriptives.R` | mean, SD, variance, min, quartiles, max, skewness, missing per variable | `wave1_descriptives_numeric.csv`, `wave1_descriptives_categorical.csv` | seconds |
| `02_correlations_features.R` | Spearman and Pearson among the 141 features, pairwise n, redundant pairs, heatmap | `wave1_correlations_features_*.csv`, `wave1_correlation_pairs_redundant.csv`, `wave1_correlation_heatmap_features.png` | seconds |
| `03_correlations_outcomes.R` | every feature and composite against the three outcomes, with BH-adjusted p; the complete matrix | `wave1_correlations_with_price.csv`, `wave1_correlations_all_spearman.csv` | seconds |
| `04_prepare_analysis_table.R` | transformed, winsorised, zero-filled features; indicators; composites and their PC1 | `wave1_analysis_table.csv`, `wave1_analysis_table_codebook.csv` | seconds |
| `05_regressions.R` | the OLS specifications 1, 2, 3, 2+, R with HC3 and clustered SEs, importance, diagnostics | `wave1_regressions_*.csv`, `wave1_regressions_coefficient_plot.png` | seconds |
| `06_cross_validation.R` | repeated team-grouped 10-fold CV of seven models on three feature sets | `wave1_cv_*.csv`, `wave1_cv_plot.png` | 30 min |
| `07_summary.R` | the results on one page; R and package versions | `wave1_results_summary.md`, `wave1_r_session_info.txt` | seconds |

In RStudio: set the working directory to `Code/analysis` and `source()` the scripts in the
same order.

## 3. Check your run against the committed results

Every random step uses the seed `20261002` (`00_functions.R`), so a run on the same R and
package versions reproduces the committed CSV files exactly. Compare, for example:

```bash
sha256sum ../../Output/wave1_cv_summary.csv
git show HEAD:Output/wave1_cv_summary.csv | sha256sum
```

If a file differs, `Output/wave1_r_session_info.txt` says which versions produced the
committed one. The figures (PNG) can differ by a few bytes between platforms without any
difference in content.

## 4. How a result comes about (reading guide)

1. `feature_blocks.csv`: one row per variable; `transform` (log1p, asinh, none), `block`,
   `composite` and `direction` (sign in the composite), `applies_to` (the indicator that says
   whether the block applies to a subnet), `spec` (1, 2, 3, control, pred, none) and
   `prediction_set` (F1, F2, F3, none). Change nothing here without recording it in `PLAN.md`:
   this table is the pre-registration.
2. `00_functions.R`, `prepare_features()`: applies the table. Winsorising limits, z-scores and
   PC loadings are computed on the rows passed as `fit`; `04` passes all 128 subnets, `06`
   passes the training fold.
3. `00_functions.R`, `SPECS`: the regressors of each specification by name.
4. `05_regressions.R`, `fit_one()`: one OLS with HC3 standard errors (`hc3_se`), team-clustered
   standard errors (`cluster_se`), standardised coefficients, drop-one delta R2, VIF, Cook's
   distance and the Breusch-Pagan statistic, all in base R.
5. `06_cross_validation.R`: the loop over 20 repeats and 10 folds; `grouped_folds()` keeps a
   team in one fold; the inner `cv.glmnet` gets the same kind of grouped folds.

## 5. Output versions

A rerun that changes a file moves the previous version to `Output/OLD/<name>_v<N>.<ext>`
(`save_output()` in `00_functions.R`); a rerun that reproduces a file leaves it untouched.
`Output/OLD/` is not synced to GitHub.
