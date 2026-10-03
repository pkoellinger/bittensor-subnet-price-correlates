# Step 4 (second half): the regressions of ANALYSIS-PLAN.md, section 6.
#
# Ordinary least squares on the 124 subnets observed for the whole September window.
# Outcomes: log 30-day average price (primary), log spot price, logret_30d (rehearsal).
# Specifications 1 (August state), 2 (September state without a known price link),
# 3 (plus two-way and mechanical features), 2+ (plus category8), R (rehearsal).
#
# Writes  Output/wave1_regressions_coefficients.csv   every model: term, estimate, HC3 and team-clustered SE,
#                                                     p-value (HC3), standardised coefficient, drop-one delta R2, VIF
#         Output/wave1_regressions_fit.csv            n, slopes, R2, adjusted R2, AIC, residual SD, F-tests, Breusch-Pagan
#         Output/wave1_regressions_importance.csv     drop-one delta R2 ranking of the primary models
#         Output/wave1_regressions_diagnostics.csv    largest VIF, the five most influential subnets, their effect on R2
#         Output/wave1_regressions_coefficient_plot.png

source("00_functions.R")

d  <- read_dataset()
fb <- read_blocks()
prep <- prepare_features(d, fb)
tab <- prep$table
reg <- tab[tab$full_window == 1, ]
stopifnot(nrow(reg) == 124)

# composites replaced by their first principal component (robustness)
pc1_version <- function(xs) ifelse(xs %in% COMPOSITES, paste0(xs, "_pc1"), xs)

fit_one <- function(data, y, xs, model, outcome_label, note = "") {
  xs <- unique(xs)
  f <- reformulate(sprintf("`%s`", xs), response = sprintf("`%s`", y))
  fit <- lm(f, data = data)
  aliased <- names(coef(fit))[is.na(coef(fit))]
  if (length(aliased)) {                                  # perfectly collinear in this sample: dropped and noted
    xs <- setdiff(xs, gsub("`", "", aliased))
    f <- reformulate(sprintf("`%s`", xs), response = sprintf("`%s`", y))
    fit <- lm(f, data = data)
    note <- paste(note, "dropped as collinear:", paste(aliased, collapse = ", "))
  }
  X <- model.matrix(fit)
  est <- coef(fit); se3 <- hc3_se(fit); secl <- cluster_se(fit, data$team_id)
  p3 <- 2 * pt(-abs(est / se3), df = fit$df.residual)
  sdy <- sd(data[[y]]); sdx <- apply(X, 2, sd); sdx[1] <- NA
  r2 <- summary(fit)$r.squared
  drop_one_by_x <- sapply(xs, function(x) {                   # a factor is dropped as a whole
    r2 - summary(lm(reformulate(sprintf("`%s`", setdiff(xs, x)), response = sprintf("`%s`", y)), data = data))$r.squared
  })
  drop_one <- c(NA, drop_one_by_x[attr(X, "assign")[-1]])     # the term each model-matrix column belongs to
  v <- vif(fit)
  coefs <- data.frame(model = model, outcome = outcome_label, term = gsub("`", "", names(est)), estimate = est, se_hc3 = se3,
                      p_hc3 = p3, se_cluster_team = secl, beta_standardised = est * sdx / sdy,
                      delta_r2_drop_one = drop_one, vif = c(NA, v), row.names = NULL)
  e <- residuals(fit)
  aux <- summary(lm(e^2 ~ X[, -1]))$r.squared                     # Breusch-Pagan (Koenker form)
  bp <- nrow(X) * aux; bp_p <- pchisq(bp, df = ncol(X) - 1, lower.tail = FALSE)
  fs <- summary(fit)$fstatistic
  fitstats <- data.frame(model = model, outcome = outcome_label, n = nrow(X), slopes = ncol(X) - 1, r2 = r2,
                         adj_r2 = summary(fit)$adj.r.squared, aic = AIC(fit), residual_sd = summary(fit)$sigma,
                         f_overall = unname(fs[1]), p_f_overall = pf(fs[1], fs[2], fs[3], lower.tail = FALSE),
                         breusch_pagan = bp, p_breusch_pagan = bp_p, max_vif = max(v), note = trimws(note))
  cooks <- cooks.distance(fit)
  top <- order(-cooks)[1:5]
  list(fit = fit, coefs = coefs, fitstats = fitstats, xs = xs,
       influential = data.frame(model = model, outcome = outcome_label, rank = 1:5, netuid = data$netuid[top],
                                subnet_name = data$subnet_name[top], cooks_distance = cooks[top], row.names = NULL))
}

outcomes <- c(log_price_avg30 = "log 30-day average price", log_price_spot = "log spot price")
results <- list()
run <- function(key, ...) results[[key]] <<- fit_one(...)

for (o in names(outcomes)) {
  run(paste(o, "spec1"), reg, o, SPECS$spec1, "spec1_august_state", outcomes[o])
  run(paste(o, "spec2"), reg, o, SPECS$spec2, "spec2_september_no_price_link", outcomes[o])
  run(paste(o, "spec3"), reg, o, SPECS$spec3, "spec3_plus_two_way_and_mechanical", outcomes[o])
  run(paste(o, "spec2plus"), transform(reg, category8 = factor(category8)), o, c(SPECS$spec2, "category8"), "spec2plus_category8", outcomes[o])
  run(paste(o, "spec2_pc1"), reg, o, pc1_version(SPECS$spec2), "spec2_pc1_composites", outcomes[o], "composites replaced by their first principal component")
  run(paste(o, "spec3_pc1"), reg, o, pc1_version(SPECS$spec3), "spec3_pc1_composites", outcomes[o], "composites replaced by their first principal component")
  for (s in c("spec2", "spec3")) {                        # refit without the five most influential subnets
    drop <- results[[paste(o, s)]]$influential$netuid
    run(paste(o, s, "no_top5"), reg[!reg$netuid %in% drop, ], o, SPECS[[s]], paste0(s, "_without_5_most_influential"), outcomes[o],
        paste("without netuids", paste(drop, collapse = ", ")))
  }
}
run("spot all128 spec2", tab, "log_price_spot", SPECS$spec2, "spec2_all_128_subnets", "log spot price", "all 128 subnets, partial windows included")
run("raw spec2", reg, "price_tao", SPECS$spec2, "spec2_raw_price", "price in TAO (not logged)", "robustness: raw price")
run("rehearsal", reg, "logret_30d", c(SPECS$spec1, "log_price_lag30"), "specR_rehearsal_wave2_test", "log return over September",
    "rehearsal of the wave 2 forward test: August state plus the lagged log price")

coefficients <- do.call(rbind, lapply(results, `[[`, "coefs"))
fitstats <- do.call(rbind, lapply(results, `[[`, "fitstats"))
influential <- do.call(rbind, lapply(results, `[[`, "influential"))

# F-test of the category block, classical, nested models on identical rows
for (o in names(outcomes)) {
  a <- anova(results[[paste(o, "spec2")]]$fit, results[[paste(o, "spec2plus")]]$fit)
  i <- which(fitstats$model == "spec2plus_category8" & fitstats$outcome == outcomes[o])
  fitstats$note[i] <- sprintf("category8 block: F(%d, %d) = %.2f, p = %.3f", a$Df[2], a$Res.Df[2], a$F[2], a$`Pr(>F)`[2])
}

importance <- coefficients[coefficients$model %in% c("spec2_september_no_price_link", "spec3_plus_two_way_and_mechanical", "spec1_august_state") &
                           coefficients$term != "(Intercept)", c("model", "outcome", "term", "beta_standardised", "delta_r2_drop_one", "p_hc3")]
importance <- importance[order(importance$outcome, importance$model, -importance$delta_r2_drop_one), ]
importance$rank <- ave(-importance$delta_r2_drop_one, importance$outcome, importance$model, FUN = rank)

diagnostics <- merge(fitstats[, c("model", "outcome", "n", "r2", "max_vif", "p_breusch_pagan")],
                     aggregate(cbind(netuid = netuid) ~ model + outcome, data = influential,
                               FUN = function(x) paste(x, collapse = " ")), by = c("model", "outcome"), all.x = TRUE)
names(diagnostics)[names(diagnostics) == "netuid"] <- "five_most_influential_netuids"
diagnostics$r2_without_five <- NA_real_
for (o in names(outcomes)) for (s in c("spec2", "spec3")) {
  i <- which(diagnostics$model == results[[paste(o, s)]]$fitstats$model & diagnostics$outcome == outcomes[o])
  diagnostics$r2_without_five[i] <- results[[paste(o, s, "no_top5")]]$fitstats$r2
}

save_csv(round_df(coefficients, 5), "regressions_coefficients.csv")
save_csv(round_df(fitstats, 5), "regressions_fit.csv")
save_csv(round_df(importance, 5), "regressions_importance.csv")
save_csv(round_df(diagnostics, 5), "regressions_diagnostics.csv")

save_png("regressions_coefficient_plot.png", width = 2000, height = 1700, res = 150, plot_fun = function() {
  par(mfrow = c(1, 2), mar = c(4, 14, 3, 1))
  for (s in c("spec2", "spec3")) {
    r <- results[[paste("log_price_avg30", s)]]
    cf <- r$coefs[r$coefs$term != "(Intercept)", ]
    sdx <- apply(model.matrix(r$fit), 2, sd)[-1]; sdy <- sd(reg$log_price_avg30)
    se_std <- cf$se_hc3 * sdx / sdy
    o <- order(cf$beta_standardised)
    plot(cf$beta_standardised[o], seq_along(o), xlim = range(c(cf$beta_standardised - 1.96 * se_std, cf$beta_standardised + 1.96 * se_std)),
         yaxt = "n", ylab = "", xlab = "standardised coefficient (HC3 95% interval)", pch = 19,
         main = sprintf("%s: R2 %.2f, adj. %.2f", r$fitstats$model, r$fitstats$r2, r$fitstats$adj_r2), cex.main = 0.9)
    segments(cf$beta_standardised[o] - 1.96 * se_std[o], seq_along(o), cf$beta_standardised[o] + 1.96 * se_std[o], seq_along(o))
    abline(v = 0, lty = 2, col = "grey50")
    axis(2, at = seq_along(o), labels = cf$term[o], las = 2, cex.axis = 0.75)
  }
})

cat("fit statistics:\n")
print(fitstats[, c("model", "outcome", "n", "slopes", "r2", "adj_r2")], row.names = FALSE, digits = 3)
