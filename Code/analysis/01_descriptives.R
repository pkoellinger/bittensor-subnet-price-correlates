# Step 1: descriptive statistics of every variable of the wave 1 dataset, raw values.
#
# Writes  Output/wave1_descriptives_numeric.csv      one row per numeric or binary variable:
#                                                    n, missing, coverage, mean, sd, variance,
#                                                    min, quartiles, max, skewness, distinct values
#         Output/wave1_descriptives_categorical.csv  frequency table of every categorical variable
# Identifiers (netuid, subnet_uid, wave, snapshot_date, subnet_name, team_id) are left out.

source("00_functions.R")

d  <- read_dataset()
cb <- read_codebook()
cb <- cb[cb$role != "id", ]

numeric_rows <- list()
categorical_rows <- list()
for (i in seq_len(nrow(cb))) {
  v <- cb$name[i]
  if (cb$type[i] %in% c("number", "integer", "binary")) {
    x <- as.numeric(d[[v]])
    ok <- !is.na(x)
    q <- if (any(ok)) quantile(x[ok], c(0.25, 0.5, 0.75), names = FALSE) else rep(NA_real_, 3)
    numeric_rows[[v]] <- data.frame(
      variable = v, label = cb$label[i], type = cb$type[i], unit = cb$unit[i], role = cb$role[i],
      window = cb$window[i], price_link = cb$price_link[i],
      n = sum(ok), n_missing = sum(!ok), coverage = sum(ok) / length(x),
      mean = mean(x[ok]), sd = sd(x[ok]), variance = var(x[ok]),
      min = min(x[ok]), p25 = q[1], median = q[2], p75 = q[3], max = max(x[ok]),
      skewness = skewness(x), distinct = length(unique(x[ok])),
      share_ones = if (cb$type[i] == "binary") mean(x[ok]) else NA_real_)
  } else {
    x <- d[[v]]
    tab <- table(ifelse(is.na(x), "(missing)", as.character(x)))
    tab <- tab[order(-tab, names(tab))]
    categorical_rows[[v]] <- data.frame(variable = v, label = cb$label[i], type = cb$type[i],
                                        value = names(tab), n = as.integer(tab), share = as.numeric(tab) / nrow(d))
  }
}
numeric_table <- round_df(do.call(rbind, numeric_rows))
categorical_table <- round_df(do.call(rbind, categorical_rows))
rownames(numeric_table) <- rownames(categorical_table) <- NULL

save_csv(numeric_table, "descriptives_numeric.csv")
save_csv(categorical_table, "descriptives_categorical.csv")
cat(sprintf("descriptives: %d numeric or binary variables, %d categorical variables (%d values); %d variables have missing values\n",
            nrow(numeric_table), length(categorical_rows), nrow(categorical_table), sum(numeric_table$n_missing > 0)))
