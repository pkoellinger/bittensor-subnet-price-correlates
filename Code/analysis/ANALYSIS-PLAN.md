# Pre-analysis plan: wave 1 of the Bittensor subnet price dataset

Written 2 Oct 2026, before any correlation between a feature and the price was computed.
Choices made by Philipp Koellinger on 2 Oct 2026; design and text by Claude. The commit that
freezes this plan is named in `Output/wave1_results_summary.md` and in `PLAN.md` (phase 6).
Anything that deviates from this plan in the scripts or the results is a deviation and is
listed as such in the results summary.

## 1. Question and data

What co-moves with the token price of a Bittensor subnet in a cross-section of 128 subnets
at the end of September 2026, how much of the variation a handful of interpretable
characteristics account for, and how well subnet characteristics predict the price of a
subnet that was not used for fitting. Data: `Input/subnets_wave1_2026-09-30.csv` (frozen,
tag `wave1`, sha256 `9793e83f…`), 171 columns documented in `Input/codebook.csv`.

What the cross-section cannot show: causes. Features measured at the same time as the price
move with it; the clean time order inside wave 1 is August features against the September
price, and the real forward test is the wave 2 return (section 9).

## 2. Sample

- Descriptives and feature correlations: all 128 subnets.
- Regressions and cross-validation: the 124 subnets observed for the whole September window
  (`window_days_observed_30d` = 30). The four others (netuids 35, 76, 82, 108) were registered
  inside the window: their lagged values do not exist and their 30-day average price covers 5
  to 26 days. The spot-price regression is repeated on all 128 as a robustness line.
- Subnets of one team (`team_id`, 8 teams with 2 or 3 subnets) share organisation-level
  GitHub and X numbers. They stay together in every cross-validation fold, and the regressions
  report team-clustered standard errors next to HC3.

## 3. Outcomes

- `log(price_tao_avg30)`: log of the mean alpha price in TAO over the 30 daily snapshot
  blocks of September. Primary outcome (it averages out end-of-month moves).
- `log(price_tao)`: log of the spot price at block 9,184,186. Secondary.
- `logret_30d = log(price_tao / price_tao_lag30)`: the September price change, used only in the
  rehearsal of the wave 2 forward test (section 7, specification R).
- `price_usd` is `price_tao` times a constant and `tao_usd` is constant: both unused.

## 4. Features: transformation and missing values

Rules are applied by `04_prepare_analysis_table.R` from `feature_blocks.csv`, one row per
variable with its transform, block, sign, applicability, specification and prediction set.

- Transform: counts, amounts and day counts → `log1p`; flows that can be negative
  (`owner_net_buy_tao_30d`, `owner_net_buy_tao_90d`, `basket_net_buy_tao_30d`,
  `owner_net_buy_tao_lag30`) → `asinh`; shares, indices, ratios and binaries unchanged. Then
  every numeric feature is clipped at its 1st and 99th percentile, computed once on the subnets
  where it is defined (features only; no outcome enters).
- Missing values are almost all "not applicable". Each such block gets an indicator and the
  feature is set to 0 where it does not apply: `has_repo` (GitHub status found or owner-only,
  104 subnets), `has_x` (X account found, 92), `miner_paid` (a miner was paid in September,
  105), `has_holders` (a stake position exists, 125), `started` (emissions have started, 124),
  `miner_paid_lag` and `started_lag` for the August versions. Clocks that never ran become
  dummies: `owner_changed_180d`, `identity_changed_180d`. `podcast_days_since_last` (undefined
  for 74) is dropped; the episode counts carry it. The four white paper features (defined for
  23 to 32 subnets) are not used; `whitepaper_available` is.
- Variables with no usable variance are not used: `doc_readme` (103 of 104), `kol_neg_*`
  (14 mentions in 8 subnets), `podcast_bittensor_guru_12m` (2 subnets), `liquid_alpha_on` (8),
  `mech_count` (6), `max_neurons` (6), `miners_distinct_ips_30d` (defined for 31).
- Of two near-duplicates (12 pairs with |Spearman| ≥ 0.95, 77 pairs ≥ 0.8 among the 141
  features, `Output/wave1_correlation_pairs_redundant.csv`) one enters the composite and the
  other only the prediction sets. The cross-block overlaps are known: miner-pay days correlate
  0.86 with the share of the window with TAO emission (subnets whose emission was off paid
  nobody), and scale and concentration of miner pay are inversely related (−0.80 to −0.87).

## 5. Composites

A composite is the mean of its members' z-scores, each member standardised on the subnets
where the block applies, with the sign from the block table; subnets where the block does not
apply get 0, and the indicator carries the absence. A member missing on an applicable subnet
is left out of that subnet's mean. The first principal component of the same signed z-scores
(`<block>_pc1`, sign aligned with the mean) is kept for one robustness row per specification.
Within-block Spearman correlations, after signing, have a positive median in every block
(0.21 for presence to 0.79 for miner concentration; lowest single pair −0.05).

| Composite | Members (sign) | Applies to |
|---|---|---|
| development | gh_commits_30d_org +, gh_authors_30d_org +, gh_prs_merged_30d_org +, gh_contributors_alltime_repo +, gh_releases_repo +, gh_days_since_push −, doc_score + | has_repo |
| presence | website_live, product_live, api_public, mcp_server, team_named, whitepaper_available (all +; unread site = 0) | all |
| miner_scale | miners_paid_coldkeys_30d +, miners_active_now +, miner_paid_days_30d + | all |
| miner_concentration | miner_hhi_coldkey_30d +, miner_hhi_lineage_best_30d + | miner_paid |
| validator_dispersion | validators_n +, validator_stake_hhi −, stake_share_owner_validator −, owner_validator_div_share − | started |
| owner_commitment | ownerhk_lock_share_issued +, owner_lock_share_owner_alpha +, owner_alpha_share_issued +, owner_lock_perpetual + | started |
| attention | kol_posts_90d +, podcast_episodes_12m +, exploit26_mentions_n +, exploit26_presented + | all |
| x_reach | x_followers +, x_posts_original_30d + | has_x |
| dev_popularity | gh_stars_org +, gh_forks_repo + | has_repo |
| holder_dispersion | holders_positions_n +, holders_top10_share −, holders_hhi − | has_holders |
| development_lag | gh_commits_lag30_org +, gh_authors_lag30_org +, gh_prs_merged_lag30_org + | has_repo |
| miner_scale_lag | miners_paid_coldkeys_lag30 +, miner_paid_days_lag30 + | all |
| miner_concentration_lag | miner_hhi_coldkey_lag30 | miner_paid_lag |
| validator_dispersion_lag | validators_n_lag30 +, validator_stake_hhi_lag30 −, stake_share_owner_validator_lag30 −, owner_validator_div_share_lag30 − | started_lag |
| owner_commitment_lag | ownerhk_lock_share_issued_lag30 +, owner_lock_share_owner_alpha_lag30 +, owner_alpha_share_issued_lag30 + | started_lag |
| attention_lag | kol_posts_lag30 +, podcast_episodes_12m_lag30 + | all |

Single variables that enter a specification on their own: `burn_mean_30d` and `burn_mean_lag30`
(a validator choice that enters the emission gate, not a mechanical response to the price),
`yuma3_on`, `commit_reveal_on`, `owner_changed_180d`, `identity_changed_180d`,
`x_posts_original_lag30`, and the two-way and mechanical singles of specification 3 (section 6).

Controls in every specification: `log_age` = log1p(days since registration), read as dilution
of the alpha reserve, which grows with time by construction; `renamed_project` (the current
project took over a running netuid); `flag_placeholder_identity`; `startup_mode`; the
indicators of the blocks in the specification (`has_repo`, `has_x`, `miner_paid`, ...).
`flag_full_burn_30d` is a September state and enters specifications 2 and 3 only.

## 6. Regressions (step 4 of the brief)

Ordinary least squares on the 124 full-window subnets, for the primary and the secondary
outcome. Three specifications on identical rows:

- **Specification 1, August state:** development_lag, miner_scale_lag, miner_concentration_lag,
  burn_mean_lag30, validator_dispersion_lag, owner_commitment_lag, attention_lag,
  x_posts_original_lag30, and the controls (log_age, renamed_project,
  flag_placeholder_identity, startup_mode, has_repo, has_x, miner_paid_lag, started_lag).
  About 16 slopes. Everything was measured a month before the outcome. Not included:
  `tao_emission_on_share_lag30` and `emission_flag_on_share_lag30` (they depend on the August
  price) and the August owner flows (mechanical).
- **Specification 2, September state without a known price link:** development, presence,
  miner_scale, miner_concentration, burn_mean_30d, validator_dispersion, owner_commitment,
  yuma3_on, commit_reveal_on, owner_changed_180d, identity_changed_180d, and the controls
  (log_age, renamed_project, flag_placeholder_identity, startup_mode, flag_full_burn_30d,
  has_repo, miner_paid, started). About 19 slopes. Specification 2 is specification 1 measured
  in September, with the features that exist only at T added.
- **Specification 3, plus two-way and mechanical features:** specification 2 plus attention,
  x_reach, has_x, dev_popularity, holder_dispersion, has_holders, owner_net_buy_tao_30d,
  owner_cut_sold_ratio_30d, owner_bought_any_90d, baskets_net_buyers_n_30d,
  basket_net_buy_tao_30d, basket_alpha_share_issued, tao_emission_on_share_30d,
  emission_flag_on_share_30d, registrations_30d, reg_cost_tao_now. About 35 slopes. Its R² is
  a description of what moves with the price, not of what predicts it.
- **Specification 2+:** specification 2 plus `category8` (7 dummies), with an F-test of the
  category block.
- **Specification R (rehearsal of the wave 2 test):** `logret_30d` on the regressors of
  specification 1 plus `log(price_tao_lag30)`. Expected: an R² near zero; it is reported as
  the rehearsal of the forward test, with that reading stated.

Reported per model: coefficients with HC3 standard errors and p-values, team-clustered
standard errors as a check, standardised coefficients (outcome and regressor in SD units),
drop-one ΔR² as the importance measure, R², adjusted R², AIC, residual SD, n. Diagnostics:
variance inflation factors; Cook's distance with the five most influential subnets named and
the model refitted without them; the Breusch–Pagan statistic. Robustness rows: PC1 composites
in place of unit weights; the spot-price model on all 128 subnets; the primary model on the
raw (unlogged) price. The whole table goes to `Output/wave1_regressions_coefficients.csv`,
the fit statistics to `wave1_regressions_fit.csv`, the importance ranking to
`wave1_regressions_importance.csv`, the diagnostics to `wave1_regressions_diagnostics.csv`,
and a coefficient plot to `wave1_regressions_coefficient_plot.png`.

Reading rule written down in advance: with 124 rows, a standardised coefficient below 0.2 is
not distinguishable from zero at 80% power even without collinearity; the importance ranking
is descriptive; p-values are not adjusted across specifications and are read as such.

## 7. Correlations with the price (step 2 of the brief, second half)

Computed only after this plan is committed: for every transformed feature and every
composite, Pearson's r and Spearman's rho with each of the three outcomes, the pairwise n,
the p-value and the Benjamini–Hochberg adjusted p-value, sorted by |rho|
(`Output/wave1_correlations_with_price.csv`), and the complete Spearman matrix including the
outcomes (`Output/wave1_correlations_all_spearman.csv`). Reading rule: among 141 features
with no true correlation, the largest |r| at n = 128 is about 0.26 in expectation; a single
feature's correlation is not evidence of relevance.

## 8. Out-of-sample prediction (step 5 of the brief)

- Sample: the 124 full-window subnets. Outcomes: log 30-day average price (primary), log spot
  price.
- Folds: 10 folds, 20 repeats, seed 20261002; teams are assigned whole to folds; the same fold
  assignment is used for every model and feature set, so differences between models are
  paired.
- Feature sets, from `feature_blocks.csv`: F1 = the August variables (specification 1's
  members and the other lagged variables marked F1) plus the controls; F2 = F1 plus every
  September variable without a known price link (marked F2), `category8` as dummies; F3 = F2
  plus the two-way and mechanical variables (marked F3) and the four excluded lagged ones.
  Penalised models and the forest use the underlying variables; OLS uses the composites of the
  matching specification.
- Models: null (training-fold mean); OLS on composites; ridge, lasso and elastic net (α = 0.5)
  with λ chosen by an inner 10-fold cross-validation grouped by team inside each training fold
  (`cv.glmnet`, `lambda.min`; glmnet standardises inside the training fold); random forest
  (`randomForest`, 1,000 trees, mtry = p/3 rounded, minimum node size 5, fixed in advance);
  ensemble = mean of the ridge and the random-forest prediction. Transformations, winsorising
  limits and composite means and SDs are computed on the training fold only.
- Metrics per repeat, pooled over the 10 folds: RMSE and MAE in log points, out-of-sample R² =
  1 − MSE(model) / MSE(null). Reported: mean and SD over the 20 repeats per model and feature
  set, paired differences against the null and against OLS, the share of repeats in which a
  model beats OLS, lasso selection frequency and random-forest permutation importance across
  the folds, and leave-one-team-out OLS as a deterministic check. Stated next to the table:
  the spread over repeats understates the uncertainty of a cross-validation estimate (Bates,
  Hastie and Tibshirani 2023), and the comparison is between models, not a confidence
  interval for any single R².
- Reading rule: a model "predicts" if its R² is above 0 by more than two SDs of the repeats;
  "best" is the model with the highest mean R² on F2, since F3 contains variables that move
  with the price by construction.

## 9. Wave 2 forward test (pre-registered)

Run after wave 2 (snapshot block 9,400,186, 31 Oct 2026) with `build/build_panel.py`'s output.
- Outcomes: `logret_fwd30` (log price change from wave 1 to wave 2) for every wave 1 subnet,
  with evicted subnets at their last observed price (`logret_to_last`); `evicted_fwd30`.
- Predictors measured in wave 1: the specification 2 composites and controls plus
  `log(price_tao)`.
- Confirmatory regression: OLS of `logret_fwd30` on those predictors, HC3 standard errors,
  two-sided tests, no adjustment across coefficients, the F-test of all slopes as the headline.
- Predictive comparison: the models and the protocol of section 8 with F2 and F3 plus
  `log(price_tao)`; metric out-of-sample R². For eviction: logistic regression and the same
  models where they apply, metric cross-validated AUC.
- Reading: the test is informative if the best pre-specified model's mean R² exceeds 0 by more
  than two SDs of the repeats. A near-zero R² is the expected result and will be reported as
  such; the wave 1 results of section 6 do not change the models or features of this section.

## 10. Reproducibility

Scripts `00` to `07` in `Code/analysis`, run in order by `run_all.R` from that folder; seeds
fixed; package versions in `Output/wave1_r_session_info.txt`; every output file starts with
`wave1_`; a rerun that changes a file moves the previous version to `Output/OLD/`. The
reproduction guide is `Code/analysis/README.md`.
