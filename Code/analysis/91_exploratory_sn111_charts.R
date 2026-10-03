# Exploratory (outside the pre-analysis plan): SN111's percentile on the main characteristics,
# as two charts. Reads the profile written by 90_exploratory_sn111.R and the dataset.
# Percentile = share of the 124 full-window subnets at or below SN111's value; the two
# concentration measures are shown inverted, as dispersion, so that "higher" reads the same way
# for every bar.
#
# Writes  Output/wave1_exploratory_sn111_percentiles.png   all 16 characteristics
#         Output/wave1_exploratory_sn111_strengths.png     the characteristics at or above the 70th percentile

source("00_functions.R")

profile <- read.csv(file.path(OUTPUT, paste0(PREFIX, "exploratory_sn111_profile.csv")), check.names = FALSE)
pct <- setNames(profile$percentile_of_sn111, profile$variable)
d <- read_dataset()
s <- d[d$netuid == 111, ]
md <- function(v) median(as.numeric(d[[v]]), na.rm = TRUE)
f <- function(x, digits = 0) formatC(x, digits = digits, format = "f", big.mark = ",")

items <- data.frame(stringsAsFactors = FALSE, rbind(
  c("Holder dispersion (by wallet)*", pct[["holder_dispersion"]], sprintf("top-10 wallets hold %s%% of stake (median %s%%)", f(100 * s$holders_top10_share), f(100 * md("holders_top10_share")))),
  c("Miner pay dispersion", 100 - pct[["miner_concentration"]], sprintf("HHI of miner pay %s (median %s)", f(s$miner_hhi_coldkey_30d, 3), f(md("miner_hhi_coldkey_30d"), 3))),
  c("Miner registration cost", pct[["reg_cost_tao_now"]], sprintf("%s TAO (median %s)", f(s$reg_cost_tao_now, 2), f(md("reg_cost_tao_now"), 3))),
  c("Public presence", pct[["presence"]], "docs 8 of 8, white paper, named team; no API, MCP or product"),
  c("Commentator and summit attention", pct[["attention"]], sprintf("%d commentator posts in 90 days (median %s), a talk at Exploit 26", s$kol_posts_90d, f(md("kol_posts_90d"), 1))),
  c("Miner registrations", pct[["registrations_30d"]], sprintf("%d in 30 days (median %s)", s$registrations_30d, f(md("registrations_30d")))),
  c("Miner scale", pct[["miner_scale"]], sprintf("%d paid wallets (median %s)", s$miners_paid_coldkeys_30d, f(md("miners_paid_coldkeys_30d")))),
  c("X reach", pct[["x_reach"]], sprintf("%s followers (median %s), %d original posts (median %s)", f(s$x_followers), f(md("x_followers")), s$x_posts_original_30d, f(md("x_posts_original_30d"), 1))),
  c("Development activity", pct[["development"]], sprintf("%d commits (median %s), 1 author (median %s), docs 8 of 8", s$gh_commits_30d_org, f(md("gh_commits_30d_org")), f(md("gh_authors_30d_org")))),
  c("TAO emission on, share of window", pct[["tao_emission_on_share_30d"]], sprintf("%s%% of the window (median %s%%)", f(100 * s$tao_emission_on_share_30d), f(100 * md("tao_emission_on_share_30d")))),
  c("Age since registration", pct[["log_age"]], sprintf("%s days; current project %s days", f(s$days_since_registration), f(s$project_age_days))),
  c("Basket net purchases", pct[["basket_net_buy_tao_30d"]], sprintf("baskets sold %s TAO net (median %s)", f(-s$basket_net_buy_tao_30d, 1), f(md("basket_net_buy_tao_30d"), 1))),
  c("Share of miner emissions burned", pct[["burn_mean_30d"]], sprintf("0%% burned (median %s%%)", f(100 * md("burn_mean_30d")))),
  c("Development popularity", pct[["dev_popularity"]], sprintf("%d stars, %d forks (medians %s, %s)", s$gh_stars_org, s$gh_forks_repo, f(md("gh_stars_org"), 1), f(md("gh_forks_repo")))),
  c("Owner commitment", pct[["owner_commitment"]], sprintf("owner holds %s%% of alpha (median %s%%), locks %s%%", f(100 * s$owner_alpha_share_issued, 1), f(100 * md("owner_alpha_share_issued"), 1), f(100 * s$ownerhk_lock_share_issued, 2))),
  c("Validator dispersion", pct[["validator_dispersion"]], sprintf("%d validators (median %s); owner validator takes %s%% of dividends", s$validators_n, f(md("validators_n"), 1), f(100 * s$owner_validator_div_share)))))
names(items) <- c("label", "percentile", "note")
items$percentile <- as.numeric(items$percentile)
items <- items[order(items$percentile), ]

draw <- function(items, title, footnote) {
  col <- ifelse(items$percentile >= 75, "#2a78d6", ifelse(items$percentile <= 25, "#d85a30", "#b4b2a9"))
  par(mar = c(5, 20, 4, 1))
  mids <- barplot(items$percentile, names.arg = items$label, horiz = TRUE, las = 1, col = col, border = NA, xlim = c(0, 135),
                  xlab = "percentile of SN111 among the 124 subnets", main = title, cex.names = 0.95, cex.main = 1.1, axes = FALSE)
  axis(1, at = seq(0, 100, 25))
  abline(v = 50, lty = 2, col = "grey40")
  text(pmax(items$percentile, 0) + 1, mids, sprintf("%.0f", items$percentile), adj = 0, cex = 0.9, font = 2)
  text(items$percentile + 8, mids, items$note, adj = 0, cex = 0.72, col = "grey25")
  mtext(footnote, side = 1, line = 3.6, adj = 0, cex = 0.75, col = "grey30")
}
save_png("exploratory_sn111_percentiles.png", width = 2600, height = 1500, res = 150, plot_fun = function()
  draw(items, "SN111 (Claims) on the main characteristics, 30 September 2026",
       "* holder dispersion is measured by wallet and overstates dispersion by holder for Claims. Concentration measures shown inverted (as dispersion). Blue: top quarter; orange: bottom quarter."))
strengths <- items[items$percentile >= 70, ]
save_png("exploratory_sn111_strengths.png", width = 2600, height = 1050, res = 150, plot_fun = function()
  draw(strengths, "Where SN111 (Claims) stands out: characteristics at or above the 70th percentile",
       "* by wallet; our own holder map shows the same alpha sits with few holders. Percentile = share of the 124 subnets at or below SN111's value."))
cat("charts written:", nrow(items), "characteristics,", nrow(strengths), "strengths\n")
