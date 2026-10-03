# Step 4 (first half): the analysis table. Transformed and winsorised features, zero-filled
# where a block does not apply, the indicators and controls, the composites (unit weights) and
# their first principal components. Rules: ANALYSIS-PLAN.md sections 4 and 5, feature_blocks.csv.
# Standardisation uses all 128 subnets here; inside the cross-validation it uses the training
# fold only (00_functions.R, prepare_features).
#
# Writes  Output/wave1_analysis_table.csv            one row per subnet
#         Output/wave1_analysis_table_codebook.csv   what every column is

source("00_functions.R")

d  <- read_dataset()
fb <- read_blocks()
prep <- prepare_features(d, fb)
tab <- prep$table

codebook <- rbind(
  data.frame(column = c("netuid", "subnet_name", "team_id", "category8"), kind = "id",
             description = c("subnet number", "name at the snapshot", "team (subnets of one team stay together in CV folds)", "category, 8 groups")),
  data.frame(column = c("log_price_spot", "log_price_avg30", "log_price_lag30", "logret_30d", "price_tao", "full_window"), kind = "outcome or sample",
             description = c("log price in TAO at block T", "log of the 30-day mean price", "log price 30 days before T",
                             "log price change over September", "price in TAO (raw)", "1 if observed for the whole window: the regression sample (124)")),
  data.frame(column = names(derived_columns(d)), kind = "indicator or control",
             description = fb$note[match(names(derived_columns(d)), fb$variable)]),
  data.frame(column = names(prep$members), kind = "composite",
             description = paste("mean of signed z-scores:", unlist(prep$members))),
  data.frame(column = paste0(names(prep$members), "_pc1"), kind = "composite (PC1)",
             description = "first principal component of the same signed z-scores, sign aligned with the mean"),
  data.frame(column = prep$rows$variable, kind = "feature",
             description = paste0(prep$rows$transform, "; applies to ", prep$rows$applies_to, "; 0 where not applicable; block ", prep$rows$block)))
stopifnot(identical(codebook$column, names(tab)))

save_csv(round_df(tab, 6), "analysis_table.csv")
save_csv(codebook, "analysis_table_codebook.csv")

a_dev <- tab$has_repo == 1
cat(sprintf("analysis table: %d rows, %d columns; regression sample %d; composites %d; features %d\n",
            nrow(tab), ncol(tab), sum(tab$full_window), length(prep$members), nrow(prep$rows)))
cat(sprintf("check: development composite mean on repos %.3f, SD %.3f; cor(unit, PC1) %.3f\n",
            mean(tab$development[a_dev]), sd(tab$development[a_dev]), cor(tab$development[a_dev], tab$development_pc1[a_dev])))
