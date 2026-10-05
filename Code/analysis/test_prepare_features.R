# Tests of the feature preparation (00_functions.R, prepare_features), base R only.
# Run from this folder:  Rscript test_prepare_features.R      (exit status 1 if a test fails)
#
# What they pin down (ANALYSIS-PLAN.md, amendment 1 of 5 Oct 2026):
#   - a subnet without a GitHub repository or an X account gets, on every repository or X
#     variable, the weakest value observed among the subnets that have one (the fewest
#     commits, followers, documentation items, ...; the longest time since the last push);
#   - its composites therefore sit at or below every subnet whose members are all observed;
#   - the OLS fits of the plan's specifications do not depend on that fill, because every
#     such composite enters together with its indicator (has_repo, has_x);
#   - blocks where a measure is undefined for structural reasons (no miner paid, no stake
#     position, emissions not started) keep the previous coding: 0 plus the indicator.

source("00_functions.R")

failures <- 0
check <- function(name, ok) {
  cat(sprintf("%-80s %s\n", name, if (isTRUE(ok)) "ok" else "FAILED"))
  if (!isTRUE(ok)) failures <<- failures + 1
}

d  <- read_dataset()
fb <- read_blocks()
d  <- d[d$window_days_observed_30d >= 30, ]                   # the regression sample, 124 subnets
prep <- prepare_features(d, fb)
tab <- prep$table
rows <- prep$rows
der <- derived_columns(d)

# ---- 1. the block table marks exactly the repository and X variables ---------------------------
check("feature_blocks.csv has an absent_fill column", "absent_fill" %in% names(fb))
if ("absent_fill" %in% names(fb)) {
  team_choice <- fb$applies_to %in% c("has_repo", "has_x") & fb$prediction_set != "none"
  check("every repository and X variable has absent_fill min or max", all(fb$absent_fill[team_choice] %in% c("min", "max")))
  check("no other variable has an absent_fill", all(fb$absent_fill[!team_choice] == ""))
  check("time since the last push is filled with its maximum", fb$absent_fill[fb$variable == "gh_days_since_push"] == "max")
}

# ---- 2. absent subnets get the weakest observed value ---------------------------------------------
worst_ok <- sapply(which(rows$applies_to %in% c("has_repo", "has_x")), function(i) {
  v <- rows$variable[i]
  a <- applies_vector(rows$applies_to[i], der)
  observed <- tab[[v]][a & !is.na(transform_values(as.numeric(d[[v]]), rows$transform[i]))]
  worst <- if (v == "gh_days_since_push") max(observed) else min(observed)
  all(abs(tab[[v]][!a] - worst) < 1e-12)
})
check(sprintf("absent subnets carry the weakest observed value (%d variables)", length(worst_ok)), all(worst_ok))

# ---- 3. composites put absent subnets at the bottom ----------------------------------------------
for (cname in c("development", "dev_popularity", "x_reach", "development_lag")) {
  a <- applies_vector(prep$applies[[cname]], der)
  members <- sub("^[+-]", "", strsplit(prep$members[[cname]], " ")[[1]])
  complete <- a & stats::complete.cases(d[, members])
  absent_value <- unique(round(tab[[cname]][!a], 12))
  check(sprintf("%s: one value for all absent subnets", cname), length(absent_value) == 1)
  check(sprintf("%s: absent subnets at or below every fully observed subnet", cname),
        all(tab[[cname]][complete] >= absent_value[1] - 1e-12))
  check(sprintf("%s: subnets with the block keep mean 0", cname), abs(mean(tab[[cname]][a])) < 0.05)
}

# ---- 4. the OLS fits do not depend on the fill ------------------------------------------------------
neutral <- tab                                             # the coding before amendment 1
for (cname in c("development", "dev_popularity", "x_reach", "development_lag"))
  neutral[[cname]][!applies_vector(prep$applies[[cname]], der)] <- 0
for (v in rows$variable[rows$applies_to %in% c("has_repo", "has_x")])
  neutral[[v]][!applies_vector(rows$applies_to[rows$variable == v], der)] <- 0
for (s in names(SPECS)) {
  f <- reformulate(sprintf("`%s`", SPECS[[s]]), response = "log_price_avg30")
  r2_new <- summary(lm(f, data = tab))$r.squared
  r2_old <- summary(lm(f, data = neutral))$r.squared
  check(sprintf("%s: R2 identical under both fills (%.6f vs %.6f)", s, r2_new, r2_old), abs(r2_new - r2_old) < 1e-10)
  p_new <- fitted(lm(f, data = tab)); p_old <- fitted(lm(f, data = neutral))
  check(sprintf("%s: fitted values identical under both fills", s), max(abs(p_new - p_old)) < 1e-9)
}

# ---- 5. structural blocks keep the previous coding --------------------------------------------------
for (cname in c("miner_concentration", "validator_dispersion", "owner_commitment", "holder_dispersion")) {
  a <- applies_vector(prep$applies[[cname]], der)
  check(sprintf("%s: rows where it does not apply stay at 0", cname), all(tab[[cname]][!a] == 0))
}
for (v in c("miner_hhi_coldkey_30d", "holders_top10_share", "validators_n")) {
  a <- applies_vector(rows$applies_to[rows$variable == v], der)
  check(sprintf("%s: rows where it does not apply stay at 0", v), all(tab[[v]][!a] == 0))
}

cat(sprintf("\n%d failure(s)\n", failures))
if (failures > 0) quit(status = 1)
