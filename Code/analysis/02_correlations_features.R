# Step 2: correlations among the features, without any outcome column (the blinded step).
#
# Features are transformed and winsorised as feature_blocks.csv says. Correlations are
# pairwise complete. Written for every pair: Spearman's rho, Pearson's r, and the number of
# subnets both values are defined for.
#
# Writes  Output/wave1_correlations_features_spearman.csv   141 x 141, ordered by block
#         Output/wave1_correlations_features_pearson.csv
#         Output/wave1_correlations_features_n.csv           pairwise n
#         Output/wave1_correlation_pairs_redundant.csv       pairs with |rho| >= 0.8 and n >= 30
#         Output/wave1_correlation_heatmap_features.png      Spearman, ordered by block

source("00_functions.R")

d  <- read_dataset()
fb <- read_blocks()
fb <- fb[fb$role %in% c("feature", "feature_lag") & fb$type %in% c("number", "integer", "binary"), ]   # 141 numeric features
stopifnot(!any(fb$variable %in% c("price_tao", "price_usd", "price_tao_avg30", "price_tao_lag30", "price_tao_avg30_lag30", "logret_30d", "tao_usd")))
fb <- fb[order(fb$block_order, fb$variable), ]

X <- feature_matrix(d, fb, fb$variable)
S <- cor(X, use = "pairwise.complete.obs", method = "spearman")
P <- cor(X, use = "pairwise.complete.obs", method = "pearson")
N <- crossprod(!is.na(X))

as_table <- function(M) {
  out <- data.frame(variable = colnames(M), block = fb$block[match(colnames(M), fb$variable)], round(M, 4), check.names = FALSE)
  rownames(out) <- NULL
  out
}
save_csv(as_table(S), "correlations_features_spearman.csv")
save_csv(as_table(P), "correlations_features_pearson.csv")
save_csv(as_table(N), "correlations_features_n.csv")

pairs <- which(upper.tri(S) & abs(S) >= 0.8 & N >= 30, arr.ind = TRUE)
redundant <- data.frame(variable_1 = colnames(S)[pairs[, 1]], variable_2 = colnames(S)[pairs[, 2]],
                        block_1 = fb$block[pairs[, 1]], block_2 = fb$block[pairs[, 2]],
                        spearman = round(S[pairs], 3), pearson = round(P[pairs], 3), n = N[pairs])
redundant <- redundant[order(-abs(redundant$spearman)), ]
rownames(redundant) <- NULL
save_csv(redundant, "correlation_pairs_redundant.csv")

save_png("correlation_heatmap_features.png", width = 3000, height = 3000, res = 150, plot_fun = function() {
  p <- ncol(S)
  palette <- colorRampPalette(c("#185FA5", "#FFFFFF", "#A32D2D"))(41)
  par(mar = c(14, 14, 2, 2))
  image(1:p, 1:p, S[, p:1], col = palette, zlim = c(-1, 1), axes = FALSE, xlab = "", ylab = "",
        main = "Spearman correlations among the 141 features (transformed), ordered by block")
  axis(1, at = 1:p, labels = colnames(S), las = 2, cex.axis = 0.45, tick = FALSE)
  axis(2, at = 1:p, labels = rev(colnames(S)), las = 2, cex.axis = 0.45, tick = FALSE)
  edges <- cumsum(table(factor(fb$block, levels = unique(fb$block))))
  abline(v = edges + 0.5, h = p - edges + 0.5, col = "grey40", lwd = 0.6)
})

cat(sprintf("features: %d; pairs with |rho| >= 0.8 (n >= 30): %d; pairs with |rho| >= 0.95: %d\n",
            ncol(S), nrow(redundant), sum(abs(redundant$spearman) >= 0.95)))
