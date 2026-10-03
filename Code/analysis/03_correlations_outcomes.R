# Step 3: correlations of every feature and composite with the price. Run after the
# pre-analysis plan was committed (ANALYSIS-PLAN.md, section 7).
#
# Writes  Output/wave1_correlations_with_price.csv     per feature or composite and outcome: Pearson r,
#                                                      Spearman rho, pairwise n, p-value (Spearman),
#                                                      Benjamini-Hochberg adjusted p; sorted by |rho|
#         Output/wave1_correlations_all_spearman.csv   the complete Spearman matrix: outcomes, composites,
#                                                      indicators and transformed features
# Features are transformed and winsorised; a feature is correlated on the subnets where it
# applies (not zero-filled), a composite on the subnets where its block applies.

source("00_functions.R")

d  <- read_dataset()
fb <- read_blocks()
prep <- prepare_features(d, fb)
tab <- prep$table
rows <- prep$rows
der <- derived_columns(d)

outcomes <- c(log_price_avg30 = "log 30-day average price", log_price_spot = "log spot price", logret_30d = "log return over September")
X <- feature_matrix(d, fb[fb$role %in% c("feature", "feature_lag") & fb$type %in% c("number", "integer", "binary"), ])

cases <- list()
for (v in colnames(X)) {
  a <- applies_vector(fb$applies_to[match(v, fb$variable)], der)
  x <- X[, v]; x[!a] <- NA
  cases[[v]] <- list(kind = "feature", block = fb$block[match(v, fb$variable)], x = x)
}
for (cname in COMPOSITES) {
  a <- applies_vector(prep$applies[[cname]], der)
  x <- tab[[cname]]; x[!a] <- NA
  cases[[cname]] <- list(kind = "composite", block = cname, x = x)
}
for (v in c("has_repo", "has_x", "miner_paid", "has_holders", "started", "owner_changed_180d", "identity_changed_180d", "log_age", "renamed_project")) {
  cases[[v]] <- list(kind = "indicator or control", block = "derived", x = tab[[v]])
}

out <- list()
for (o in names(outcomes)) {
  y <- tab[[o]]
  for (v in names(cases)) {
    x <- cases[[v]]$x
    ok <- !is.na(x) & !is.na(y)
    if (sum(ok) < 10 || sd(x[ok]) == 0) next
    s <- suppressWarnings(cor.test(x[ok], y[ok], method = "spearman", exact = FALSE))
    out[[length(out) + 1]] <- data.frame(outcome = o, variable = v, kind = cases[[v]]$kind, block = cases[[v]]$block,
                                         n = sum(ok), pearson_r = cor(x[ok], y[ok]), spearman_rho = unname(s$estimate),
                                         p_spearman = s$p.value)
  }
}
res <- do.call(rbind, out)
res$p_bh <- ave(res$p_spearman, res$outcome, FUN = function(p) p.adjust(p, method = "BH"))
res <- res[order(res$outcome, -abs(res$spearman_rho)), ]
rownames(res) <- NULL
save_csv(round_df(res, 4), "correlations_with_price.csv")

all_cols <- cbind(tab[, names(outcomes)], tab[, COMPOSITES], tab[, c("has_repo", "has_x", "miner_paid", "has_holders", "started", "log_age")],
                  X)
S <- suppressWarnings(cor(all_cols, use = "pairwise.complete.obs", method = "spearman"))   # NA where a pair leaves no variance
S_table <- data.frame(variable = colnames(S), round(S, 4), check.names = FALSE)
save_csv(S_table, "correlations_all_spearman.csv")

top <- res[res$outcome == "log_price_avg30", ][1:10, c("variable", "n", "spearman_rho", "p_bh")]
cat("strongest Spearman correlations with the log 30-day average price:\n"); print(top, row.names = FALSE)
cat(sprintf("largest |r| expected among %d null features at n = 128: about %.2f\n", ncol(X), qnorm(1 - 0.5 / ncol(X)) / sqrt(128 - 1)))
