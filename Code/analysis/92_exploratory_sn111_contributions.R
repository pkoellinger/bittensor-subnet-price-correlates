# Exploratory (outside the pre-analysis plan): what pulls SN111's model value up and down.
#
# For the OLS specifications of step 4, the contribution of regressor j to SN111's predicted
# log price, relative to the average subnet, is  b_j * (x_111,j - mean(x_j)). The deviations are
# known constants, so a 95% interval for a contribution is  b_j +/- 1.96 * HC3 SE_j  times the
# deviation. Contributions sum to the model's predicted deviation of SN111 from the mean log
# price; the difference to the actual deviation is the residual.
#
# Writes  Output/wave1_exploratory_sn111_contributions.csv   specifications 2 and 3: per term, SN111's value,
#                                                           the mean, coefficient, HC3 SE, contribution, interval
#         Output/wave1_exploratory_sn111_contributions.png   specification 2 (no known price link), log 30-day average price

source("00_functions.R")

d  <- read_dataset()
fb <- read_blocks()
tab <- prepare_features(d, fb)$table
reg <- tab[tab$full_window == 1, ]
i111 <- which(reg$netuid == 111)
stopifnot(length(i111) == 1)

labels <- c(development = "Development activity (composite)", presence = "Public presence (0 to 6)",
            miner_scale = "Miner scale (composite)", miner_concentration = "Miner pay concentration (composite)",
            burn_mean_30d = "Share of miner emissions burned", validator_dispersion = "Validator dispersion (composite)",
            owner_commitment = "Owner commitment (composite)", yuma3_on = "Yuma 3 on", commit_reveal_on = "Commit-reveal on",
            owner_changed_180d = "Owner key changed in 180 days", identity_changed_180d = "Identity changed in 180 days",
            log_age = "Age since registration (log)", renamed_project = "Took over a running netuid",
            flag_placeholder_identity = "Placeholder identity", startup_mode = "Startup mode", flag_full_burn_30d = "Full burn",
            has_repo = "Has a GitHub repository", has_x = "Has an X account", has_holders = "Has stake positions",
            attention = "Commentator and summit attention (composite)", x_reach = "X reach (composite)",
            dev_popularity = "GitHub stars and forks (composite)", holder_dispersion = "Holder dispersion by wallet (composite)",
            owner_net_buy_tao_30d = "Owner net purchases (asinh TAO)", owner_cut_sold_ratio_30d = "Owner cut sold, ratio",
            owner_bought_any_90d = "Owner bought in 90 days", baskets_net_buyers_n_30d = "Baskets buying, count",
            basket_net_buy_tao_30d = "Basket net purchases (asinh TAO)", basket_alpha_share_issued = "Basket holdings, share of alpha",
            tao_emission_on_share_30d = "TAO emission on, share of window", emission_flag_on_share_30d = "Emission flag on, share of window",
            registrations_30d = "Miner registrations (log)", reg_cost_tao_now = "Registration cost (log TAO)")

contributions <- function(spec, y = "log_price_avg30") {
  xs <- SPECS[[spec]]
  fit <- lm(reformulate(sprintf("`%s`", xs), response = y), data = reg)
  xs <- setdiff(xs, gsub("`", "", names(coef(fit))[is.na(coef(fit))]))          # exactly collinear in this sample
  fit <- lm(reformulate(sprintf("`%s`", xs), response = y), data = reg)
  X <- model.matrix(fit)[, -1, drop = FALSE]
  b <- coef(fit)[-1]; se <- hc3_se(fit)[-1]
  dev <- X[i111, ] - colMeans(X)
  data.frame(model = spec, outcome = y, term = gsub("`", "", names(b)), label = labels[gsub("`", "", names(b))],
             x_sn111 = X[i111, ], x_mean = colMeans(X), coefficient = b, se_hc3 = se,
             contribution = b * dev, ci_low = (b - 1.96 * se) * dev, ci_high = (b + 1.96 * se) * dev,
             predicted_deviation = sum(b * dev), actual_deviation = reg[[y]][i111] - mean(reg[[y]]),
             residual = residuals(fit)[i111], row.names = NULL)
}
out <- rbind(contributions("spec2"), contributions("spec3"), contributions("spec2", "log_price_spot"))
out$ci_low2 <- pmin(out$ci_low, out$ci_high); out$ci_high <- pmax(out$ci_low, out$ci_high); out$ci_low <- out$ci_low2; out$ci_low2 <- NULL
save_csv(round_df(out, 5), "exploratory_sn111_contributions.csv")

s2 <- out[out$model == "spec2" & out$outcome == "log_price_avg30", ]
s2 <- s2[order(s2$contribution), ]
pct <- function(x) sprintf("%+.0f%%", 100 * (exp(x) - 1))
save_png("exploratory_sn111_contributions.png", width = 2600, height = 1600, res = 150, plot_fun = function() {
  par(mar = c(5, 24, 5, 2))
  col <- ifelse(s2$contribution >= 0, "#2a78d6", "#d85a30")
  names_two_lines <- sprintf("%s\nSN111 %.2f, mean %.2f", s2$label, s2$x_sn111, s2$x_mean)
  lim <- max(abs(c(s2$ci_low, s2$ci_high))) + 0.12
  mids <- barplot(s2$contribution, names.arg = names_two_lines, horiz = TRUE, las = 1, col = col, border = NA, xlim = c(-lim, lim),
                  xlab = "contribution to SN111's log price relative to the average subnet (log points; 95% HC3 interval)",
                  main = "What pulls SN111's model value up and down (specification 2: September state without a known price link)",
                  cex.names = 0.8, cex.main = 1.05, axes = FALSE)
  axis(1); abline(v = 0, lty = 1, col = "grey40")
  segments(s2$ci_low, mids, s2$ci_high, mids, lwd = 1.5)
  text(ifelse(s2$contribution >= 0, s2$ci_high, s2$ci_low) + ifelse(s2$contribution >= 0, 0.015, -0.015), mids,
       pct(s2$contribution), adj = ifelse(s2$contribution >= 0, 0, 1), cex = 0.8, font = 2, col = "grey20")
  mtext(sprintf("Sum of contributions: %+.2f log points (%s); actual: %+.2f (%s); residual: %+.2f (%s). In-sample fit, n = 124, R2 %.2f.",
                s2$predicted_deviation[1], pct(s2$predicted_deviation[1]), s2$actual_deviation[1], pct(s2$actual_deviation[1]),
                s2$residual[1], pct(s2$residual[1]), summary(lm(reformulate(sprintf("`%s`", setdiff(SPECS$spec2, c("miner_paid", "started"))), response = "log_price_avg30"), data = reg))$r.squared),
        side = 3, line = 0.3, cex = 0.85, col = "grey25")
  mtext("A contribution = coefficient x (SN111's value - the mean value); intervals use the coefficient's HC3 standard error. Correlates, not causes.",
        side = 1, line = 3.8, adj = 0, cex = 0.75, col = "grey30")
})

cat("specification 2, log 30-day average price:\n")
print(s2[order(-abs(s2$contribution)), c("label", "x_sn111", "x_mean", "coefficient", "contribution", "ci_low", "ci_high")], row.names = FALSE, digits = 3)
cat(sprintf("\npredicted deviation %+.2f, actual %+.2f, residual %+.2f\n", s2$predicted_deviation[1], s2$actual_deviation[1], s2$residual[1]))
s3 <- out[out$model == "spec3" & out$outcome == "log_price_avg30", ]
cat("\nspecification 3, largest contributions:\n")
print(s3[order(-abs(s3$contribution)), ][1:8, c("label", "contribution", "ci_low", "ci_high")], row.names = FALSE, digits = 3)
cat(sprintf("spec 3: predicted deviation %+.2f, actual %+.2f, residual %+.2f\n", s3$predicted_deviation[1], s3$actual_deviation[1], s3$residual[1]))
