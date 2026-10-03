# Installs the two CRAN packages the analyses need (glmnet for ridge, lasso and elastic net;
# randomForest for the random forest) into the user's library, and prints their versions.
# Everything else is base R. Run once:  Rscript install_packages.R
#
# The versions used for the committed results are recorded in Output/wave1_r_session_info.txt.

user_lib <- Sys.getenv("R_LIBS_USER")
if (user_lib == "") {
  user_lib <- file.path(Sys.getenv("LOCALAPPDATA"), "R", "win-library",
                        paste(R.version$major, sub("\\..*$", "", R.version$minor), sep = "."))
}
dir.create(user_lib, recursive = TRUE, showWarnings = FALSE)
.libPaths(c(user_lib, .libPaths()))

needed <- c("glmnet", "randomForest")
missing <- needed[!needed %in% rownames(installed.packages())]
if (length(missing)) {
  install.packages(missing, lib = user_lib, repos = "https://cloud.r-project.org", quiet = TRUE)
}
for (p in needed) cat(sprintf("%-13s %s\n", p, as.character(packageVersion(p))))
cat("library:", user_lib, "\n")
