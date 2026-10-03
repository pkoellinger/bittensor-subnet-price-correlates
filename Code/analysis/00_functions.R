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
read_blocks   <- function() {                      # every column as text ("" stays ""), block_order as integer
  fb <- read.csv(BLOCKS, check.names = FALSE, na.strings = character(0), colClasses = "character", encoding = "UTF-8")
  fb$block_order <- as.integer(fb$block_order)
  fb
}

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
save_csv <- function(df, filename) {              # binary connection: LF line ends on every platform
  save_output(function(p) { con <- file(p, open = "wb", encoding = "UTF-8"); on.exit(close(con))
                            write.csv(df, con, row.names = FALSE, na = "") }, paste0(PREFIX, filename))
}
save_text <- function(lines, filename) {
  save_output(function(p) { con <- file(p, open = "wb", encoding = "UTF-8"); on.exit(close(con))
                            writeLines(lines, con, useBytes = TRUE) }, paste0(PREFIX, filename))
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

# ---- the analysis table ---------------------------------------------------------------------
PRE_ANALYSIS_COMMIT <- "1d034af"       # the commit that froze ANALYSIS-PLAN.md and feature_blocks.csv

# indicators of applicability (structural missingness) and the controls, as ANALYSIS-PLAN.md defines them
derived_columns <- function(d) {
  data.frame(
    has_repo = as.integer(d$gh_status %in% c("found", "owner_only")),
    has_x = as.integer(d$x_status == "found"),
    miner_paid = as.integer(d$flag_no_miner_paid_30d == 0),
    miner_paid_lag = as.integer(!is.na(d$miners_paid_coldkeys_lag30) & d$miners_paid_coldkeys_lag30 > 0),
    has_holders = as.integer(d$holders_positions_n > 0),
    started = as.integer(d$startup_mode == 0),
    started_lag = as.integer(!is.na(d$days_since_first_emission) & d$days_since_first_emission > 30),
    owner_changed_180d = as.integer(!is.na(d$days_since_owner_change) & d$days_since_owner_change <= 180),
    identity_changed_180d = as.integer(!is.na(d$days_since_identity_change) & d$days_since_identity_change <= 180),
    log_age = log1p(d$days_since_registration),
    renamed_project = as.integer(d$project_age_days < d$days_since_registration - 1))
}
outcome_columns <- function(d) {
  data.frame(log_price_spot = log(d$price_tao), log_price_avg30 = log(d$price_tao_avg30),
             log_price_lag30 = log(d$price_tao_lag30), logret_30d = d$logret_30d, price_tao = d$price_tao,
             full_window = as.integer(d$window_days_observed_30d >= 30))
}
applies_vector <- function(name, der) if (name == "all") rep(TRUE, nrow(der)) else der[[name]] == 1

# Transformed, winsorised, zero-filled features, indicators and composites for every subnet.
# Winsorising limits, z-score means and SDs and PC1 loadings come from the rows in `fit`
# (all rows for the descriptive table, the training fold inside the cross-validation).
# Returns list(table, members): the table and the composite definitions used.
prepare_features <- function(d, fb, fit = seq_len(nrow(d))) {
  rows <- fb[fb$role %in% c("feature", "feature_lag", "flag") & fb$type %in% c("number", "integer", "binary") &
             fb$prediction_set != "none", ]
  der <- derived_columns(d)
  n <- nrow(d)
  X <- matrix(NA_real_, n, nrow(rows), dimnames = list(NULL, rows$variable))
  Z <- X                                            # z-scores on the applicable rows, 0 elsewhere, NA if missing
  applies <- matrix(FALSE, n, nrow(rows), dimnames = list(NULL, rows$variable))
  for (i in seq_len(nrow(rows))) {
    x <- transform_values(as.numeric(d[[rows$variable[i]]]), rows$transform[i])
    a <- applies_vector(rows$applies_to[i], der)
    ok <- a & !is.na(x)
    fit_ok <- intersect(fit, which(ok))
    if (length(fit_ok) >= 10) {
      q <- quantile(x[fit_ok], c(0.01, 0.99), names = FALSE)
      x <- pmin(pmax(x, q[1]), q[2])
    }
    m <- if (length(fit_ok)) mean(x[fit_ok]) else 0
    s <- if (length(fit_ok) > 1) sd(x[fit_ok]) else 0
    z <- rep(0, n)
    z[ok] <- if (is.finite(s) && s > 0) (x[ok] - m) / s else 0
    z[a & is.na(x)] <- NA
    x[!a] <- 0                                      # does not apply: the indicator carries it
    x[a & is.na(x)] <- m                            # missing on an applicable row: the fit mean
    X[, i] <- x; Z[, i] <- z; applies[, i] <- a
  }
  comps <- unique(rows$composite[rows$composite != "" & rows$direction != ""])
  C <- matrix(0, n, 2 * length(comps), dimnames = list(NULL, c(comps, paste0(comps, "_pc1"))))
  members <- list(); comp_applies <- list()
  for (cname in comps) {
    idx <- which(rows$composite == cname & rows$direction != "")
    signs <- as.numeric(rows$direction[idx])
    a <- applies[, idx[1]]
    Zs <- sweep(Z[, idx, drop = FALSE], 2, signs, `*`)
    unit <- rowMeans(Zs, na.rm = TRUE); unit[!a | is.nan(unit)] <- 0
    pc1 <- unit
    if (length(idx) > 1) {
      Zf <- Zs; Zf[is.na(Zf)] <- 0
      fit_a <- intersect(fit, which(a))
      if (length(fit_a) > length(idx)) {
        p <- prcomp(Zf[fit_a, , drop = FALSE], center = TRUE, scale. = FALSE)
        score <- as.numeric(scale(Zf, center = p$center, scale = FALSE) %*% p$rotation[, 1])
        if (cor(score[fit_a], unit[fit_a]) < 0) score <- -score
        pc1 <- score; pc1[!a] <- 0
      }
    }
    C[, cname] <- unit; C[, paste0(cname, "_pc1")] <- pc1
    members[[cname]] <- paste0(ifelse(signs > 0, "+", "-"), rows$variable[idx], collapse = " ")
    comp_applies[[cname]] <- rows$applies_to[idx[1]]
  }
  table <- data.frame(netuid = d$netuid, subnet_name = d$subnet_name, team_id = d$team_id, category8 = d$category8,
                      outcome_columns(d), der, C, X, check.names = FALSE)
  list(table = table, members = members, applies = comp_applies, rows = rows)
}

# the regressors of each specification (ANALYSIS-PLAN.md, section 6); composites by name
CONTROLS <- c("log_age", "renamed_project", "flag_placeholder_identity", "startup_mode")
SPECS <- list(
  # startup_mode is not in specification 1: started_lag nests it (every startup subnet had not started in
  # August either), and the one subnet that had started in September only would otherwise carry leverage 1
  spec1 = c("development_lag", "miner_scale_lag", "miner_concentration_lag", "burn_mean_lag30", "validator_dispersion_lag",
            "owner_commitment_lag", "attention_lag", "x_posts_original_lag30",
            setdiff(CONTROLS, "startup_mode"), "has_repo", "has_x", "miner_paid_lag", "started_lag"),
  spec2 = c("development", "presence", "miner_scale", "miner_concentration", "burn_mean_30d", "validator_dispersion",
            "owner_commitment", "yuma3_on", "commit_reveal_on", "owner_changed_180d", "identity_changed_180d",
            CONTROLS, "flag_full_burn_30d", "has_repo", "miner_paid", "started"))
SPECS$spec3 <- c(SPECS$spec2, "attention", "x_reach", "has_x", "dev_popularity", "holder_dispersion", "has_holders",
                 "owner_net_buy_tao_30d", "owner_cut_sold_ratio_30d", "owner_bought_any_90d",
                 "baskets_net_buyers_n_30d", "basket_net_buy_tao_30d", "basket_alpha_share_issued",
                 "tao_emission_on_share_30d", "emission_flag_on_share_30d", "registrations_30d", "reg_cost_tao_now")
COMPOSITES <- c("development", "presence", "miner_scale", "miner_concentration", "validator_dispersion", "owner_commitment",
                "attention", "x_reach", "dev_popularity", "holder_dispersion", "development_lag", "miner_scale_lag",
                "miner_concentration_lag", "validator_dispersion_lag", "owner_commitment_lag", "attention_lag")

# the variables of a prediction set (F1, F2 or F3) in the analysis table, category8 as dummies
prediction_set <- function(fb, table, set) {
  levels_in <- switch(set, F1 = "F1", F2 = c("F1", "F2"), F3 = c("F1", "F2", "F3"))
  vars <- fb$variable[fb$prediction_set %in% levels_in & fb$variable %in% names(table) & fb$type != "category"]
  M <- as.matrix(table[, vars, drop = FALSE])
  if (set != "F1") {
    dummies <- model.matrix(~ category8, data = transform(table, category8 = factor(category8)))[, -1, drop = FALSE]
    colnames(dummies) <- paste0("category8_", gsub("[^A-Za-z0-9]+", "_", sub("^category8", "", colnames(dummies))))
    M <- cbind(M, dummies)
  }
  M[, apply(M, 2, sd) > 0, drop = FALSE]
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
