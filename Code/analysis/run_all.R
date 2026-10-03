# Runs the wave 1 analyses in order, from this folder:  Rscript run_all.R
# Steps 1 to 5 take about a minute together; step 6 (cross-validation) about half an hour.
# Every step can also be run on its own:  Rscript 05_regressions.R

steps <- c("01_descriptives.R", "02_correlations_features.R", "03_correlations_outcomes.R",
           "04_prepare_analysis_table.R", "05_regressions.R", "06_cross_validation.R", "07_summary.R")
for (s in steps) {
  cat("\n==== ", s, " ====\n", sep = "")
  t0 <- Sys.time()
  source(s, echo = FALSE, local = new.env())
  cat(sprintf("(%s: %.1f minutes)\n", s, as.numeric(difftime(Sys.time(), t0, units = "mins"))))
}
cat("\nall steps done\n")
