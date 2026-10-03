# Write the dataset as an R data frame (.rds) with variable labels, and check that it equals the CSV.
#
# Usage (from Code/collection): Rscript build/build_rds.R ../../Input/subnets_wave1_2026-09-30.csv ../../Input/codebook.csv
#
# Each column carries the attributes "label", "unit", "window", "role", "asof" and "price_link" from
# the codebook, so that  attr(d$price_tao, "label")  gives its description. Columns of type
# "category" become factors, "date" becomes Date. The whole codebook is attached to the data frame
# as attr(d, "codebook"). Base R only; no packages are needed.

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("usage: Rscript build/build_rds.R <dataset.csv> <codebook.csv>")
csv_path <- args[1]
codebook_path <- args[2]
rds_path <- sub("\\.csv$", ".rds", csv_path)

raw <- read.csv(csv_path, stringsAsFactors = FALSE, na.strings = "", check.names = FALSE,
                encoding = "UTF-8", colClasses = "character")
cb <- read.csv(codebook_path, stringsAsFactors = FALSE, na.strings = character(0), encoding = "UTF-8")
stopifnot(identical(names(raw), cb$name))

d <- raw
for (i in seq_len(nrow(cb))) {
  name <- cb$name[i]
  kind <- cb$type[i]
  v <- raw[[name]]
  v <- switch(kind,
              integer = as.integer(v),
              binary = as.integer(v),
              number = as.numeric(v),
              category = factor(v),
              date = as.Date(v),
              v)
  for (a in c("label", "unit", "window", "role", "asof", "price_link")) attr(v, a) <- cb[[a]][i]
  d[[name]] <- v
}
attr(d, "codebook") <- cb
saveRDS(d, rds_path)

# ---- the .rds must hold exactly what the CSV holds
back <- readRDS(rds_path)
stopifnot(nrow(back) == nrow(raw), identical(names(back), names(raw)))
for (i in seq_len(nrow(cb))) {
  name <- cb$name[i]
  a <- raw[[name]]
  b <- back[[name]]
  stopifnot(identical(is.na(a), is.na(b)))
  if (cb$type[i] %in% c("integer", "binary", "number")) {
    stopifnot(isTRUE(all.equal(as.numeric(a), as.numeric(b), tolerance = 1e-12)))
  } else {
    stopifnot(identical(a[!is.na(a)], as.character(b)[!is.na(b)]))
  }
  stopifnot(identical(attr(b, "label"), cb$label[i]))
}
cat(sprintf("wrote %s: %d rows, %d columns, labels on every column; contents equal to the CSV\n",
            rds_path, nrow(back), ncol(back)))
