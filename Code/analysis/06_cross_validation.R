# Step 5: out-of-sample accuracy by repeated, team-grouped 10-fold cross-validation
# (ANALYSIS-PLAN.md, section 8). Takes about half an hour.
#
# Sample: the 124 full-window subnets. Outcomes: log 30-day average price (primary), log spot
# price. Feature sets F1 (August state), F2 (plus September features without a known price
# link), F3 (everything usable). Models: null, OLS on the composites of the matching
# specification, ridge, lasso, elastic net, random forest, ensemble (mean of ridge and forest).
# Everything that is estimated from data (winsorising limits, z-scores, PC loadings, lambda)
# is estimated on the training fold only.
#
# Writes  Output/wave1_cv_results_by_repeat.csv      RMSE, MAE and out-of-sample R2 per outcome, feature set, model, repeat
#         Output/wave1_cv_summary.csv                mean and SD over the 20 repeats, paired differences, share of wins
#         Output/wave1_cv_selection_frequency.csv    lasso: share of the 200 training folds in which a variable was kept (F2, primary)
#         Output/wave1_cv_rf_importance.csv          random forest: mean permutation importance over the folds (F2, primary)
#         Output/wave1_cv_folds.csv                  the fold of every subnet in every repeat
#         Output/wave1_cv_plot.png

source("00_functions.R")
suppressPackageStartupMessages({ library(glmnet); library(randomForest) })

d  <- read_dataset()
fb <- read_blocks()
d  <- d[d$window_days_observed_30d >= 30, ]
stopifnot(nrow(d) == 124)

K <- 10; REPEATS <- 20
folds <- grouped_folds(d$team_id, k = K, repeats = REPEATS, seed = SEED)
outcomes <- c("log_price_avg30", "log_price_spot")
sets <- c("F1", "F2", "F3")
spec_of <- c(F1 = "spec1", F2 = "spec2", F3 = "spec3")
models <- c("null", "ols_composites", "ridge", "lasso", "elastic_net", "random_forest", "ensemble_ridge_rf")

pred <- list()                                        # pred[[outcome]][[set]][[model]]: matrix n x repeats
for (o in outcomes) for (s in sets) for (m in models) pred[[o]][[s]][[m]] <- matrix(NA_real_, nrow(d), REPEATS)
null_pred <- list(); for (o in outcomes) null_pred[[o]] <- matrix(NA_real_, nrow(d), REPEATS)
lasso_kept <- list(); rf_importance <- list()

ols_predict <- function(train_tab, test_tab, y, xs) {
  f <- reformulate(sprintf("`%s`", xs), response = sprintf("`%s`", y))
  fit <- suppressWarnings(lm(f, data = train_tab))
  suppressWarnings(as.numeric(predict(fit, newdata = test_tab)))
}

t0 <- Sys.time()
for (r in seq_len(REPEATS)) {
  for (f in seq_len(K)) {
    train <- which(folds[, r] != f); test <- which(folds[, r] == f)
    prep <- prepare_features(d, fb, fit = train)
    tab <- prep$table
    inner <- grouped_folds(d$team_id[train], k = K, repeats = 1, seed = SEED + 1000 * r + f)[, 1]
    for (o in outcomes) {
      y <- tab[[o]]
      null_pred[[o]][test, r] <- mean(y[train])
      pred[[o]][["F1"]][["null"]][test, r] <- mean(y[train])
      for (s in sets) {
        pred[[o]][[s]][["null"]][test, r] <- mean(y[train])
        pred[[o]][[s]][["ols_composites"]][test, r] <- ols_predict(tab[train, ], tab[test, ], o, SPECS[[spec_of[s]]])
        M <- prediction_set(fb, tab, s)
        M <- M[, apply(M[train, , drop = FALSE], 2, sd) > 0, drop = FALSE]
        fits <- list()
        for (m in c("ridge", "lasso", "elastic_net")) {
          alpha <- c(ridge = 0, lasso = 1, elastic_net = 0.5)[[m]]
          set.seed(SEED + r)
          cvf <- cv.glmnet(M[train, ], y[train], alpha = alpha, foldid = inner, nfolds = K, standardize = TRUE)
          pred[[o]][[s]][[m]][test, r] <- as.numeric(predict(cvf, newx = M[test, , drop = FALSE], s = "lambda.min"))
          if (m == "lasso" && s == "F2" && o == outcomes[1]) {
            kept <- rownames(coef(cvf, s = "lambda.min"))[as.numeric(coef(cvf, s = "lambda.min")) != 0]
            lasso_kept[[length(lasso_kept) + 1]] <- setdiff(kept, "(Intercept)")
          }
        }
        set.seed(SEED + 100 * r + f)
        want_importance <- s == "F2" && o == outcomes[1]
        rf <- randomForest(x = M[train, , drop = FALSE], y = y[train], ntree = 1000, mtry = max(1, floor(ncol(M) / 3)),
                           nodesize = 5, importance = want_importance)
        pred[[o]][[s]][["random_forest"]][test, r] <- as.numeric(predict(rf, newdata = M[test, , drop = FALSE]))
        if (want_importance) rf_importance[[length(rf_importance) + 1]] <- importance(rf, type = 1)[, 1]
        pred[[o]][[s]][["ensemble_ridge_rf"]][test, r] <- (pred[[o]][[s]][["ridge"]][test, r] + pred[[o]][[s]][["random_forest"]][test, r]) / 2
      }
    }
  }
  cat(sprintf("repeat %d of %d done (%.1f min)\n", r, REPEATS, as.numeric(difftime(Sys.time(), t0, units = "mins")))); flush(stdout())
}

# ---- metrics per repeat, pooled over the folds ---------------------------------------------
rows <- list()
for (o in outcomes) {
  y <- outcome_columns(d)[[o]]
  for (s in sets) for (m in models) for (r in seq_len(REPEATS)) {
    yhat <- pred[[o]][[s]][[m]][, r]
    rows[[length(rows) + 1]] <- data.frame(outcome = o, feature_set = s, model = m, repeat_ = r,
                                           rmse = rmse(y, yhat), mae = mae(y, yhat), r2_oos = r2_oos(y, yhat, null_pred[[o]][, r]))
  }
}
by_repeat <- do.call(rbind, rows)
names(by_repeat)[names(by_repeat) == "repeat_"] <- "repeat"

summary_rows <- list()
for (o in outcomes) for (s in sets) for (m in models) {
  x <- by_repeat[by_repeat$outcome == o & by_repeat$feature_set == s & by_repeat$model == m, ]
  ols <- by_repeat[by_repeat$outcome == o & by_repeat$feature_set == s & by_repeat$model == "ols_composites", ]
  summary_rows[[length(summary_rows) + 1]] <- data.frame(
    outcome = o, feature_set = s, model = m,
    r2_oos_mean = mean(x$r2_oos), r2_oos_sd = sd(x$r2_oos), r2_oos_min = min(x$r2_oos), r2_oos_max = max(x$r2_oos),
    rmse_mean = mean(x$rmse), rmse_sd = sd(x$rmse), mae_mean = mean(x$mae),
    share_repeats_above_zero = mean(x$r2_oos > 0),
    diff_r2_vs_ols_mean = mean(x$r2_oos - ols$r2_oos), diff_r2_vs_ols_sd = sd(x$r2_oos - ols$r2_oos),
    share_repeats_beats_ols = mean(x$r2_oos > ols$r2_oos))
}
cv_summary <- do.call(rbind, summary_rows)

# leave-one-team-out OLS on specification 2, primary outcome: a deterministic check
teams <- unique(d$team_id); y <- outcome_columns(d)$log_price_avg30
loto <- rep(NA_real_, nrow(d)); loto_null <- loto
for (t in teams) {
  test <- which(d$team_id == t); train <- setdiff(seq_len(nrow(d)), test)
  tab <- prepare_features(d, fb, fit = train)$table
  loto[test] <- ols_predict(tab[train, ], tab[test, ], "log_price_avg30", SPECS$spec2)
  loto_null[test] <- mean(y[train])
}
cv_summary <- rbind(cv_summary, data.frame(outcome = "log_price_avg30", feature_set = "F2", model = "ols_composites_leave_one_team_out",
                                           r2_oos_mean = r2_oos(y, loto, loto_null), r2_oos_sd = NA, r2_oos_min = NA, r2_oos_max = NA,
                                           rmse_mean = rmse(y, loto), rmse_sd = NA, mae_mean = mae(y, loto), share_repeats_above_zero = NA,
                                           diff_r2_vs_ols_mean = NA, diff_r2_vs_ols_sd = NA, share_repeats_beats_ols = NA))

selection <- sort(table(unlist(lasso_kept)) / length(lasso_kept), decreasing = TRUE)
selection <- data.frame(variable = names(selection), share_of_training_folds_kept = as.numeric(selection))
imp <- do.call(rbind, lapply(rf_importance, function(v) v[match(names(rf_importance[[1]]), names(v))]))
rf_imp <- data.frame(variable = colnames(imp), mean_increase_in_mse_percent = colMeans(imp, na.rm = TRUE),
                     sd_over_folds = apply(imp, 2, sd, na.rm = TRUE))
rf_imp <- rf_imp[order(-rf_imp$mean_increase_in_mse_percent), ]
fold_table <- data.frame(netuid = d$netuid, team_id = d$team_id, folds); names(fold_table)[-(1:2)] <- paste0("repeat_", seq_len(REPEATS))

save_csv(round_df(by_repeat, 5), "cv_results_by_repeat.csv")
save_csv(round_df(cv_summary, 5), "cv_summary.csv")
save_csv(round_df(selection, 4), "cv_selection_frequency.csv")
save_csv(round_df(rf_imp, 4), "cv_rf_importance.csv")
save_csv(fold_table, "cv_folds.csv")

save_png("cv_plot.png", width = 2200, height = 900, res = 150, plot_fun = function() {
  par(mfrow = c(1, 3), mar = c(9, 4, 3, 1))
  for (s in sets) {
    x <- cv_summary[cv_summary$outcome == "log_price_avg30" & cv_summary$feature_set == s & cv_summary$model %in% models, ]
    mids <- barplot(x$r2_oos_mean, names.arg = x$model, las = 2, ylim = c(min(0, min(x$r2_oos_mean - x$r2_oos_sd)) - 0.05, 1),
                    col = "#B5D4F4", main = sprintf("feature set %s, log 30-day average price", s), ylab = "out-of-sample R2 (mean over 20 repeats)")
    arrows(mids, x$r2_oos_mean - x$r2_oos_sd, mids, x$r2_oos_mean + x$r2_oos_sd, angle = 90, code = 3, length = 0.04)
    abline(h = 0, lty = 2)
  }
})

cat("\nout-of-sample R2, mean (SD) over 20 repeats, log 30-day average price:\n")
print(reshape(cv_summary[cv_summary$outcome == "log_price_avg30" & cv_summary$model %in% models, c("feature_set", "model", "r2_oos_mean")],
              idvar = "model", timevar = "feature_set", direction = "wide"), row.names = FALSE, digits = 3)
