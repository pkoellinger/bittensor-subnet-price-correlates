# Exploratory, outside the pre-analysis plan (asked on 2 Oct 2026 after the results were in):
# where does subnet 111 (Claims) sit relative to what the models of steps 4 and 5 would assign
# to a subnet with its characteristics, and relative to the subnets most similar to it?
#
# Everything here is descriptive. A model's "fair value" is the price of subnets with similar
# measured characteristics, with the model's own out-of-sample error around it (RMSE in log
# points from wave1_cv_summary.csv); it is not a valuation.
#
# Writes  Output/wave1_exploratory_sn111_predictions.csv   leave-one-out predictions of every model for SN111
#         Output/wave1_exploratory_sn111_neighbours.csv    the ten most similar subnets and their prices
#         Output/wave1_exploratory_sn111_profile.csv       SN111's value and percentile on every regressor

source("00_functions.R")
suppressPackageStartupMessages({ library(glmnet); library(randomForest) })

d  <- read_dataset()
fb <- read_blocks()
d  <- d[d$window_days_observed_30d >= 30, ]
target <- which(d$netuid == 111)
stopifnot(length(target) == 1)
others <- setdiff(seq_len(nrow(d)), target)
cv <- read.csv(file.path(OUTPUT, paste0(PREFIX, "cv_summary.csv")), check.names = FALSE)

# ---- leave-one-out predictions: every model fitted on the other 123 subnets --------------------
prep <- prepare_features(d, fb, fit = others)
tab <- prep$table
inner <- grouped_folds(d$team_id[others], k = 10, repeats = 1, seed = SEED)[, 1]
rows <- list()
for (o in c("log_price_avg30", "log_price_spot")) {
  y <- tab[[o]]
  for (s in c("F1", "F2", "F3")) {
    spec <- c(F1 = "spec1", F2 = "spec2", F3 = "spec3")[[s]]
    f <- reformulate(sprintf("`%s`", SPECS[[spec]]), response = o)
    ols <- suppressWarnings(predict(lm(f, data = tab[others, ]), newdata = tab[target, , drop = FALSE]))
    M <- prediction_set(fb, tab, s); M <- M[, apply(M[others, , drop = FALSE], 2, sd) > 0, drop = FALSE]
    pen <- sapply(c(ridge = 0, lasso = 1, elastic_net = 0.5), function(alpha) {
      set.seed(SEED)
      as.numeric(predict(cv.glmnet(M[others, ], y[others], alpha = alpha, foldid = inner), newx = M[target, , drop = FALSE], s = "lambda.min"))
    })
    set.seed(SEED)
    rf <- randomForest(x = M[others, , drop = FALSE], y = y[others], ntree = 1000, mtry = max(1, floor(ncol(M) / 3)), nodesize = 5)
    rfp <- as.numeric(predict(rf, newdata = M[target, , drop = FALSE]))
    preds <- c(ols_composites = unname(ols), pen, random_forest = rfp, ensemble_ridge_rf = (pen[["ridge"]] + rfp) / 2)
    for (m in names(preds)) {
      rmse <- cv$rmse_mean[cv$outcome == o & cv$feature_set == s & cv$model == m]
      rows[[length(rows) + 1]] <- data.frame(outcome = o, feature_set = s, model = m, actual_log = y[target], predicted_log = preds[[m]],
                                             actual_tao = exp(y[target]), predicted_tao = exp(preds[[m]]),
                                             gap_log = y[target] - preds[[m]], gap_percent = 100 * (exp(y[target] - preds[[m]]) - 1),
                                             model_rmse_log = rmse, gap_in_rmse_units = (y[target] - preds[[m]]) / rmse)
    }
  }
}
predictions <- do.call(rbind, rows)

# ---- in-sample residual rank of SN111 in the plan's regressions --------------------------------
full <- prepare_features(d, fb)$table
resid_rank <- sapply(c("spec1", "spec2", "spec3"), function(s) {
  fit <- lm(reformulate(sprintf("`%s`", SPECS[[s]]), response = "log_price_avg30"), data = full)
  r <- residuals(fit); c(residual = unname(r[target]), percentile = 100 * mean(r <= r[target]))
})

# ---- most similar subnets in the space of specification 2 (the clean characteristics) ---------
xs <- setdiff(SPECS$spec2, c("miner_paid", "started"))
Z <- scale(as.matrix(full[, xs]))
Z[is.na(Z)] <- 0
dist_to_111 <- sqrt(rowSums((Z - matrix(Z[target, ], nrow(Z), ncol(Z), byrow = TRUE))^2))
nn <- order(dist_to_111)[2:11]
neighbours <- data.frame(netuid = d$netuid[nn], subnet_name = d$subnet_name[nn], category8 = d$category8[nn],
                         distance = dist_to_111[nn], price_tao_avg30 = d$price_tao_avg30[nn], price_tao_spot = d$price_tao[nn],
                         log_price_avg30 = full$log_price_avg30[nn],
                         development = full$development[nn], burn_mean_30d = full$burn_mean_30d[nn], miner_scale = full$miner_scale[nn],
                         presence = full$presence[nn], owner_commitment = full$owner_commitment[nn], log_age = full$log_age[nn],
                         attention = full$attention[nn])
sn111_row <- data.frame(netuid = 111, subnet_name = d$subnet_name[target], category8 = d$category8[target], distance = 0,
                        price_tao_avg30 = d$price_tao_avg30[target], price_tao_spot = d$price_tao[target], log_price_avg30 = full$log_price_avg30[target],
                        development = full$development[target], burn_mean_30d = full$burn_mean_30d[target], miner_scale = full$miner_scale[target],
                        presence = full$presence[target], owner_commitment = full$owner_commitment[target], log_age = full$log_age[target],
                        attention = full$attention[target])
neighbours <- rbind(sn111_row, neighbours)

# ---- SN111's profile on every regressor of specifications 2 and 3 ------------------------------
vars <- unique(c(SPECS$spec3, "log_price_avg30", "log_price_spot"))
profile <- data.frame(variable = vars,
                      sn111 = sapply(vars, function(v) full[[v]][target]),
                      median_all = sapply(vars, function(v) median(full[[v]], na.rm = TRUE)),
                      percentile_of_sn111 = sapply(vars, function(v) 100 * mean(full[[v]] <= full[[v]][target], na.rm = TRUE)),
                      row.names = NULL)

save_csv(round_df(predictions, 5), "exploratory_sn111_predictions.csv")
save_csv(round_df(neighbours, 5), "exploratory_sn111_neighbours.csv")
save_csv(round_df(profile, 5), "exploratory_sn111_profile.csv")

cat(sprintf("SN111: 30-day average price %.5f TAO (log %.2f), rank %d of %d\n", d$price_tao_avg30[target], full$log_price_avg30[target],
            sum(d$price_tao_avg30 >= d$price_tao_avg30[target]), nrow(d)))
cat("in-sample residual (log points) and percentile:\n"); print(round(resid_rank, 2))
cat("\nleave-one-out predictions, log 30-day average price:\n")
print(predictions[predictions$outcome == "log_price_avg30", c("feature_set", "model", "predicted_tao", "gap_percent", "gap_in_rmse_units")], row.names = FALSE, digits = 3)
cat("\nten most similar subnets (specification 2 space):\n")
print(neighbours[, c("netuid", "subnet_name", "distance", "price_tao_avg30", "development", "burn_mean_30d", "miner_scale", "attention")], row.names = FALSE, digits = 3)
cat(sprintf("\nneighbours' median 30-day average price: %.5f TAO; SN111: %.5f TAO\n", median(neighbours$price_tao_avg30[-1]), d$price_tao_avg30[target]))
