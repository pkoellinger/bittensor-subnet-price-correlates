# Shared helpers for the wave 1 analyses. Base R only; glmnet and randomForest are loaded
# only by 06_cross_validation.R. Every numbered script starts with source("00_functions.R")
# and is run from this folder (Code/analysis), for example:  Rscript 01_descriptives.R
#
# Contents: locations, reading the data, saving outputs with the Output/OLD versioning rule,
# transformations, composites, robust standard errors, grouped folds, prediction metrics.

options(stringsAsFactors = FALSE, width = 120, warn = 1)

# ---- locations ------------------------------------------------------------------------------
script_dir <- function() {
  args <- commandArgs(trailingOnly = FALSE)
  file <- sub("^--file=", "", args[grepl("^--file=", args)])
  if (length(file)) dirname(normalizePath(file[1], winslash = "/")) else normalizePath(getwd(), winslash = "/")
}
HERE     <- script_dir()                                           # Code/analysis
PROJECT  <- normalizePath(file.path(HERE, "..", ".."), winslash = "/")
INPUT    <- file.path(PROJECT, "Input")
OUTPUT   <- file.path(PROJECT, "Output")
DATASET  <- file.path(INPUT, "subnets_wave1_2026-09-30.csv")
CODEBOOK <- file.path(INPUT, "codebook.csv")
BLOCKS   <- file.path(HERE, "feature_blocks.csv")
SEED     <- 20261002                                               # every random step uses it
PREFIX   <- "wave1_"                                               # every output file starts with it

# packages installed by install_packages.R live in the user library
user_lib <- Sys.getenv("R_LIBS_USER")
if (user_lib == "") {
  user_lib <- file.path(Sys.getenv("LOCALAPPDATA"), "R", "win-library",
                        paste(R.version$major, sub("\\..*$", "", R.version$minor), sep = "."))
}
if (dir.exists(user_lib)) .libPaths(c(user_lib, .libPaths()))

# ---- reading --------------------------------------------------------------------------------
read_dataset  <- function() read.csv(DATASET, check.names = FALSE, na.strings = "", encoding = "UTF-8")
read_codebook <- function() read.csv(CODEBOOK, check.names = FALSE, na.strings = character(0), encoding = "UTF-8")
read_blocks   <- function() read.csv(BLOCKS, check.names = FALSE, na.strings = character(0), encoding = "UTF-8")

# ---- saving: a changed file moves the previous version to Output/OLD/<stem>_v<N>.<ext> ---------
save_output <- function(write_fun, filename) {
  dir.create(OUTPUT, showWarnings = FALSE)
  path <- file.path(OUTPUT, filename)
  ext <- tools::file_ext(filename)
  tmp <- file.path(OUTPUT, paste0(".", filename, ".tmp"))
  write_fun(tmp)
  if (file.exists(path)) {
    if (unname(tools::md5sum(tmp)) == unname(tools::md5sum(path))) {
      file.remove(tmp)
      return(invisible(path))
    }
    old_dir <- file.path(OUTPUT, "OLD")
    dir.create(old_dir, showWarnings = FALSE)
    stem <- sub("\\.[^.]*$", "", filename)
    n <- length(list.files(old_dir, pattern = paste0("^", stem, "_v[0-9]+\\.", ext, "$"))) + 1
    old <- sprintf("%s_v%d.%s", stem, n, ext)
    file.rename(path, file.path(old_dir, old))
    message("previous version moved to Output/OLD/", old)
  }
  file.rename(tmp, path)
  invisible(path)
}
save_csv <- function(df, filename) {
  save_output(function(p) write.csv(df, p, row.names = FALSE, na = "", fileEncoding = "UTF-8"), paste0(PREFIX, filename))
}
save_text <- function(lines, filename) {
  save_output(function(p) writeLines(lines, p, useBytes = TRUE), paste0(PREFIX, filename))
}
save_png <- function(filename, plot_fun, width = 2400, height = 2400, res = 150) {
  save_output(function(p) { png(p, width = width, height = height, res = res, type = "cairo"); on.exit(dev.off()); plot_fun() },
              paste0(PREFIX, filename))
}
round_df <- function(df, digits = 6) {
  for (v in names(df)) if (is.numeric(df[[v]])) df[[v]] <- signif(df[[v]], digits)
  df
}

# ---- transformations ------------------------------------------------------------------------
# feature_blocks.csv names the transform of every variable: log1p for counts, amounts and
# days; asinh for flows that can be negative; none for shares, indices, ratios and binaries.
transform_values <- function(x, how) {
  switch(how, log1p = log1p(x), asinh = asinh(x), none = x, stop("unknown transform: ", how))
}
# clip at the 1st and 99th percentile of the rows where the variable is defined
winsorise <- function(x, probs = c(0.01, 0.99)) {
  if (sum(!is.na(x)) < 10) return(x)
  q <- quantile(x, probs, na.rm = TRUE, names = FALSE)
  pmin(pmax(x, q[1]), q[2])
}
skewness <- function(x) {
  x <- x[!is.na(x)]
  if (length(x) < 3) return(NA_real_)
  s <- sqrt(mean((x - mean(x))^2))
  if (!is.finite(s) || s == 0) return(NA_real_)
  mean((x - mean(x))^3) / s^3
}
# the matrix of transformed and winsorised features named in the block table
feature_matrix <- function(d, fb, variables = NULL) {
  rows <- fb[fb$role %in% c("feature", "feature_lag"), ]
  if (!is.null(variables)) rows <- rows[rows$variable %in% variables, ]
  X <- sapply(seq_len(nrow(rows)), function(i) {
    x <- as.numeric(d[[rows$variable[i]]])
    winsorise(transform_values(x, rows$transform[i]))
  })
  colnames(X) <- rows$variable
  X
}

# ---- composites -----------------------------------------------------------------------------
# standardise on the rows where the block applies (others become 0); the sign comes from the
# block table. A missing member on an applicable row is left out of that row's mean.
zscore_where <- function(x, applies) {
  z <- rep(0, length(x))
  ok <- applies & !is.na(x)
  if (sum(ok) > 1) {
    m <- mean(x[ok]); s <- sd(x[ok])
    z[ok] <- if (s > 0) (x[ok] - m) / s else 0
  }
  z[applies & is.na(x)] <- NA
  z
}
# unit-weighted composite and the first principal component of the same signed z-scores
composite <- function(Z, signs, applies) {
  Zs <- sweep(Z, 2, signs, `*`)
  unit <- rowMeans(Zs, na.rm = TRUE)
  unit[!applies] <- 0
  unit[is.nan(unit)] <- 0
  Zf <- Zs; Zf[is.na(Zf)] <- 0                               # missing member = block mean
  pc1 <- rep(0, nrow(Z))
  if (ncol(Z) > 1 && sum(applies) > ncol(Z)) {
    p <- prcomp(Zf[applies, , drop = FALSE], center = TRUE, scale. = FALSE)
    score <- Zf[applies, , drop = FALSE] %*% p$rotation[, 1]
    if (cor(score, unit[applies]) < 0) score <- -score        # same direction as the unit weights
    pc1[applies] <- as.numeric(score)
  } else pc1 <- unit
  list(unit = unit, pc1 = pc1)
}

# ---- inference ------------------------------------------------------------------------------
# HC3 heteroskedasticity-robust standard errors (MacKinnon and White 1985)
hc3_se <- function(fit) {
  X <- model.matrix(fit); e <- residuals(fit); h <- hatvalues(fit)
  bread <- solve(crossprod(X))
  meat <- crossprod(X * (e / (1 - h)))
  sqrt(diag(bread %*% meat %*% bread))
}
# cluster-robust standard errors with the usual small-sample correction (CR1)
cluster_se <- function(fit, cluster) {
  X <- model.matrix(fit); e <- residuals(fit)
  n <- nrow(X); k <- ncol(X); g <- length(unique(cluster))
  bread <- solve(crossprod(X))
  meat <- Reduce(`+`, lapply(split(seq_len(n), cluster), function(i) {
    s <- colSums(X[i, , drop = FALSE] * e[i]); tcrossprod(s)
  }))
  adj <- g / (g - 1) * (n - 1) / (n - k)
  sqrt(diag(adj * bread %*% meat %*% bread))
}
vif <- function(fit) {
  X <- model.matrix(fit)[, -1, drop = FALSE]
  sapply(seq_len(ncol(X)), function(j) 1 / (1 - summary(lm(X[, j] ~ X[, -j]))$r.squared))
}

# ---- cross-validation -----------------------------------------------------------------------
# folds that keep every group (team) in one fold; one column per repeat
grouped_folds <- function(groups, k = 10, repeats = 20, seed = SEED) {
  set.seed(seed)
  ids <- unique(groups)
  out <- matrix(NA_integer_, nrow = length(groups), ncol = repeats)
  for (r in seq_len(repeats)) {
    shuffled <- sample(ids)
    fold_of_group <- setNames(rep(seq_len(k), length.out = length(shuffled)), shuffled)
    out[, r] <- unname(fold_of_group[as.character(groups)])
  }
  out
}
rmse <- function(y, yhat) sqrt(mean((y - yhat)^2))
mae  <- function(y, yhat) mean(abs(y - yhat))
# out-of-sample R squared: 1 - MSE of the model / MSE of the training-fold mean, pooled over folds
r2_oos <- function(y, yhat, null_hat) 1 - mean((y - yhat)^2) / mean((y - null_hat)^2)
