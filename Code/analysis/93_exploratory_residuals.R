# Exploratory (outside the pre-analysis plan): which subnets are priced above or below what the
# models assign to their characteristics, and does such a gap mean anything?
#
# Part A  Out-of-fold predictions of the log 30-day average price at the end of September for every
#         subnet (feature set F2: no known price link; the same folds, models and settings as
#         06_cross_validation.R; a subnet is always predicted by models that never saw it or its
#         team). Residual = actual - predicted, per model and averaged over the models.
# Part B  The test the data allow today: the same exercise one month earlier (end-of-August price
#         on August features, F1), and whether those August residuals predicted the September
#         return. If "priced below the model" meant "undervalued", low-residual subnets should have
#         outperformed in September.
#
# Writes  Output/wave1_exploratory_residuals_by_subnet.csv      Part A: one row per subnet
#         Output/wave1_exploratory_residuals_august_test.csv    Part B: correlations and regressions
#         Output/wave1_exploratory_residuals.png                both parts in one figure
# Takes about ten minutes.

source("00_functions.R")
suppressPackageStartupMessages({ library(glmnet); library(randomForest) })

d  <- read_dataset()
fb <- read_blocks()
d  <- d[d$window_days_observed_30d >= 30, ]
K <- 10; REPEATS <- 20
folds <- grouped_folds(d$team_id, k = K, repeats = REPEATS, seed = SEED)          # the folds of step 5
models <- c("ols_composites", "ridge", "lasso", "elastic_net", "random_forest")

out_of_fold <- function(outcome, set, spec) {
  pred <- lapply(setNames(models, models), function(m) matrix(NA_real_, nrow(d), REPEATS))
  for (r in seq_len(REPEATS)) for (f in seq_len(K)) {
    train <- which(folds[, r] != f); test <- which(folds[, r] == f)
    tab <- prepare_features(d, fb, fit = train)$table
    y <- tab[[outcome]]
    inner <- grouped_folds(d$team_id[train], k = K, repeats = 1, seed = SEED + 1000 * r + f)[, 1]
    fit <- suppressWarnings(lm(reformulate(sprintf("`%s`", SPECS[[spec]]), response = outcome), data = tab[train, ]))
    pred$ols_composites[test, r] <- suppressWarnings(as.numeric(predict(fit, newdata = tab[test, ])))
    M <- prediction_set(fb, tab, set); M <- M[, apply(M[train, , drop = FALSE], 2, sd) > 0, drop = FALSE]
    for (m in c("ridge", "lasso", "elastic_net")) {
      set.seed(SEED + r)
      cvf <- cv.glmnet(M[train, ], y[train], alpha = c(ridge = 0, lasso = 1, elastic_net = 0.5)[[m]], foldid = inner)
      pred[[m]][test, r] <- as.numeric(predict(cvf, newx = M[test, , drop = FALSE], s = "lambda.min"))
    }
    set.seed(SEED + 100 * r + f)
    rf <- randomForest(x = M[train, , drop = FALSE], y = y[train], ntree = 1000, mtry = max(1, floor(ncol(M) / 3)), nodesize = 5)
    pred$random_forest[test, r] <- as.numeric(predict(rf, newdata = M[test, , drop = FALSE]))
  }
  sapply(pred, rowMeans)                                         # mean out-of-fold prediction per subnet and model
}

oc <- outcome_columns(d)

# ---- Part A: end of September, feature set F2 ---------------------------------------------------
pa <- out_of_fold("log_price_avg30", "F2", "spec2")
res_a <- oc$log_price_avg30 - pa
clean <- c("ridge", "lasso", "elastic_net", "random_forest")      # the four models that predict out of sample
by_subnet <- data.frame(netuid = d$netuid, subnet_name = d$subnet_name, category8 = d$category8,
                        price_tao_avg30 = d$price_tao_avg30, log_price_avg30 = oc$log_price_avg30,
                        setNames(as.data.frame(pa), paste0("predicted_", models)),
                        setNames(as.data.frame(res_a), paste0("residual_", models)),
                        residual_mean_4_models = rowMeans(res_a[, clean]),
                        models_agreeing_on_sign = pmax(rowSums(res_a[, clean] > 0), rowSums(res_a[, clean] < 0)),
                        price_over_model_value = exp(rowMeans(res_a[, clean])))
by_subnet <- by_subnet[order(by_subnet$residual_mean_4_models), ]
by_subnet$rank_low_to_high <- seq_len(nrow(by_subnet))
save_csv(round_df(by_subnet, 5), "exploratory_residuals_by_subnet.csv")

# ---- Part B: end of August on August features, then the September return ---------------------------
pb <- out_of_fold("log_price_lag30", "F1", "spec1")
res_b <- oc$log_price_lag30 - pb
aug <- rowMeans(res_b[, clean])
ret <- oc$logret_30d
tab_all <- prepare_features(d, fb)$table
tests <- list()
add <- function(name, x) {
  ct <- cor.test(x, ret); sp <- suppressWarnings(cor.test(x, ret, method = "spearman", exact = FALSE))
  fit <- lm(ret ~ x); se <- hc3_se(fit)[2]
  fit2 <- lm(ret ~ x + tab_all$log_age + tab_all$started_lag); se2 <- hc3_se(fit2)[2]
  tests[[length(tests) + 1]] <<- data.frame(
    predictor = name, n = length(x), pearson_r = unname(ct$estimate), p_pearson = ct$p.value, spearman_rho = unname(sp$estimate), p_spearman = sp$p.value,
    slope = coef(fit)[2], se_hc3 = se, p_slope = 2 * pt(-abs(coef(fit)[2] / se), fit$df.residual), r2 = summary(fit)$r.squared,
    slope_with_age_controls = coef(fit2)[2], se_hc3_with_controls = se2, p_with_controls = 2 * pt(-abs(coef(fit2)[2] / se2), fit2$df.residual), row.names = NULL)
}
add("August residual, mean of 4 models (F1)", aug)
for (m in models) add(paste("August residual,", m), res_b[, m])
add("log price at end of August (level, no model)", oc$log_price_lag30)
tests <- do.call(rbind, tests)
persistence <- cor(aug, by_subnet$residual_mean_4_models[match(d$netuid, by_subnet$netuid)])
tests$note <- sprintf("correlation of the August residual with the end-of-September residual: %.2f", persistence)
save_csv(round_df(tests, 5), "exploratory_residuals_august_test.csv")

# ---- figure ------------------------------------------------------------------------------------------
save_png("exploratory_residuals.png", width = 2800, height = 1500, res = 150, plot_fun = function() {
  layout(matrix(1:2, 1), widths = c(1.15, 1))
  n <- nrow(by_subnet); pick <- c(1:12, (n - 11):n); x <- by_subnet[pick, ]
  par(mar = c(5, 13, 4, 1))
  mids <- barplot(x$residual_mean_4_models, names.arg = sprintf("%s (SN%d)", ifelse(is.na(x$subnet_name), "unnamed", x$subnet_name), x$netuid), horiz = TRUE, las = 1,
                  col = ifelse(x$residual_mean_4_models > 0, "#d85a30", "#2a78d6"), border = NA, cex.names = 0.8, xlim = c(-2.2, 2.6),
                  xlab = "actual minus model log price (out of fold, mean of 4 models)",
                  main = "A. Priced furthest below (blue) and above (orange) the model value,\nend of September 2026, 12 each of 124", cex.main = 0.95)
  text(x$residual_mean_4_models + ifelse(x$residual_mean_4_models > 0, 0.05, -0.05), mids, sprintf("x%.1f", x$price_over_model_value),
       adj = ifelse(x$residual_mean_4_models > 0, 0, 1), cex = 0.75)
  abline(v = 0, col = "grey40")
  par(mar = c(5, 5, 4, 1))
  plot(aug, ret, pch = 19, col = "#5F5E5A", cex = 0.8, xlab = "August residual: end-of-August log price minus model value (out of fold)",
       ylab = "log return over September",
       main = sprintf("B. Did the August gap predict the September return?\nr = %.2f (p = %.2f), slope %.2f (HC3 SE %.2f), n = %d", tests$pearson_r[1], tests$p_pearson[1], tests$slope[1], tests$se_hc3[1], tests$n[1]),
       cex.main = 0.95)
  abline(lm(ret ~ aug), col = "#185FA5", lwd = 2); abline(h = 0, v = 0, lty = 3, col = "grey50")
})

cat(sprintf("Part A: residual SD %.2f log points; subnets with all 4 models on one side: %d of %d\n",
            sd(by_subnet$residual_mean_4_models), sum(by_subnet$models_agreeing_on_sign == 4), nrow(by_subnet)))
cat("lowest 12 (priced below the model value):\n"); print(by_subnet[1:12, c("netuid", "subnet_name", "price_tao_avg30", "residual_mean_4_models", "price_over_model_value", "models_agreeing_on_sign")], row.names = FALSE, digits = 3)
cat("highest 12 (priced above the model value):\n"); print(by_subnet[(nrow(by_subnet) - 11):nrow(by_subnet), c("netuid", "subnet_name", "price_tao_avg30", "residual_mean_4_models", "price_over_model_value", "models_agreeing_on_sign")], row.names = FALSE, digits = 3)
cat(sprintf("SN111: residual %.2f, rank %d of %d\n", by_subnet$residual_mean_4_models[by_subnet$netuid == 111], by_subnet$rank_low_to_high[by_subnet$netuid == 111], nrow(by_subnet)))
cat("\nPart B:\n"); print(tests[, c("predictor", "n", "pearson_r", "p_pearson", "spearman_rho", "slope", "se_hc3", "p_slope", "slope_with_age_controls", "p_with_controls")], row.names = FALSE, digits = 3)
cat(tests$note[1], "\n")
