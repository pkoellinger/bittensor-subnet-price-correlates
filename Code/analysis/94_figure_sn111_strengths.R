# Publication figure (exploratory, outside the pre-analysis plan): where SN111 (Claims) stands out.
# SN111's percentile among the 124 subnets of the regression sample on five characteristics,
# end of September 2026, from the profile written by 90_exploratory_sn111.R. A percentile is the
# share of the 124 subnets at or below SN111's value; a subnet without a GitHub repository or an
# X account counts as the weakest case (ANALYSIS-PLAN.md, amendment 1).
#
# Characteristics were chosen by Philipp Koellinger on 5 Oct 2026 from those at or above the 70th
# percentile. Left out on purpose: holder and miner-pay dispersion (measured by wallet, which
# overstates dispersion for Claims: few entities hold most of its alpha, and miner farms rotate
# coldkeys), registration cost (repeats miner registrations) and miner scale (repeats miner pay).
#
# Writes  Output/wave1_figure_sn111_strengths.csv        the five values
#         Output/wave1_figure_sn111_strengths_x.html     X version (Claims brand: Alice Blue, Fraunces, Inter)
#         Output/wave1_figure_sn111_strengths_x.png      3200 x 1800, rendered with headless Chrome if present
#         Output/wave1_figure_sn111_strengths_deck.svg   deck version (Inter, deck tokens), inlined in the
#                                                        Claims – SN111 deck as the slide "Where Claims stands out."

source("00_functions.R")

REPO_URL <- "github.com/pkoellinger/bittensor-subnet-price-correlates"
items <- data.frame(stringsAsFactors = FALSE,
  variable = c("presence", "registrations_30d", "attention", "x_reach", "development"),
  label = c("Public presence", "Miner registrations", "Commentator and summit attention", "Activity on X", "Development activity"),
  members = c("website, product, API, MCP server, named team, white paper",
              "miner registrations in September",
              "commentator posts, podcast episodes, Exploit 26 talk and mentions",
              "followers and original posts on X",
              "commits, authors, pull requests, contributors, releases, recency, documentation"))
profile <- read.csv(file.path(OUTPUT, paste0(PREFIX, "exploratory_sn111_profile.csv")), check.names = FALSE)
items$percentile <- profile$percentile_of_sn111[match(items$variable, profile$variable)]
stopifnot(!anyNA(items$percentile))
items$shown <- round(items$percentile)
items <- items[order(-items$shown, match(items$variable, items$variable)), ]
save_csv(round_df(items, 6), "figure_sn111_strengths.csv")

esc <- function(x) gsub("&", "&amp;", x, fixed = TRUE)
num <- function(x) sprintf("%.1f", x)

# ---- X version: 1600 x 900 CSS px, Claims brand -------------------------------------------------------
logo <- paste(readLines(file.path(HERE, "assets", "claims-logo-landscape-dark.svg"), warn = FALSE), collapse = "\n")
logo <- sub("<svg ", "<svg class=\"logo\" ", logo, fixed = TRUE)
x0 <- 620; w <- 740; top <- 56; band <- 100; bar <- 60
y_axis <- top + band * nrow(items)
grid <- vapply(c(0, 25, 50, 75, 100), function(v) {
  gx <- x0 + w * v / 100
  if (v == 50) sprintf('<line x1="%s" x2="%s" y1="%s" y2="%s" stroke="#4D69A9" stroke-width="2" stroke-dasharray="7 7"/>', num(gx), num(gx), top - 14, y_axis)
  else sprintf('<line x1="%s" x2="%s" y1="%s" y2="%s" stroke="#9CBEED" stroke-width="1.5" opacity=".7"/>', num(gx), num(gx), top - 14, y_axis)
}, "")
ticks <- vapply(c(0, 25, 50, 75, 100), function(v)
  sprintf('<text class="ax" x="%s" y="%s" text-anchor="middle">%d</text>', num(x0 + w * v / 100), y_axis + 38, v), "")
bars <- vapply(seq_len(nrow(items)), function(i) {
  yc <- top + band * (i - 0.5); bw <- w * items$percentile[i] / 100
  paste0(sprintf('<text class="lab" x="%s" y="%s" text-anchor="end">%s</text>', x0 - 26, num(yc + 10), esc(items$label[i])),
         sprintf('<rect x="%s" y="%s" width="%s" height="%s" rx="6" fill="#4D69A9"/>', x0, num(yc - bar / 2), num(bw), bar),
         sprintf('<text class="val" x="%s" y="%s">%d</text>', num(x0 + bw + 16), num(yc + 13), items$shown[i]))
}, "")
x_html <- c(
  '<!doctype html><html><head><meta charset="utf-8">',
  '<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght,SOFT@9..144,400,0;9..144,600,100&family=Inter:wght@400;500&display=swap" rel="stylesheet">',
  '<style>',
  '*{margin:0;box-sizing:border-box}',
  'body{width:1600px;height:900px;background:#F0FBFF;color:#060A13;font-family:Inter,sans-serif;padding:64px 96px 52px;display:flex;flex-direction:column}',
  '.logo{height:36px;width:184px;display:block;align-self:flex-start}',
  'svg.chart{margin-top:36px;display:block}',
  '.lab{font-family:Fraunces,serif;font-weight:600;font-variation-settings:"SOFT" 100;font-size:28px;fill:#121F3A}',
  '.val{font:500 34px Inter;fill:#121F3A}',
  '.ax{font:400 22px Inter;fill:#4D69A9}',
  '.med{font:400 20px Inter;fill:#4D69A9}',
  '.cap{font:400 21px Inter;fill:#33415e}',
  '.src{margin-top:auto;font-size:20px;line-height:1.45;color:#4D69A9}',
  '</style></head><body>',
  logo,
  sprintf('<svg class="chart" width="1408" height="%d" viewBox="0 0 1408 %d">', y_axis + 92, y_axis + 92),
  grid,
  sprintf('<text class="med" x="%s" y="%d" text-anchor="middle">Median subnet</text>', num(x0 + w / 2), top - 24),
  bars, ticks,
  sprintf('<text class="cap" x="%s" y="%d" text-anchor="middle">Percentile among 124 Bittensor subnets, end of September 2026 (100 = highest)</text>', num(x0 + w / 2), y_axis + 82),
  '</svg>',
  sprintf('<p class="src">Data and code to reproduce this analysis: %s</p>', REPO_URL),
  '</body></html>')
save_text(x_html, "figure_sn111_strengths_x.html")

chrome <- "C:/Program Files/Google/Chrome/Application/chrome.exe"
if (file.exists(chrome)) {
  html_path <- normalizePath(file.path(OUTPUT, paste0(PREFIX, "figure_sn111_strengths_x.html")), winslash = "/")
  tmp_png <- file.path(tempdir(), "figure_x.png")
  system2(chrome, c("--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                    "--window-size=1600,900", "--virtual-time-budget=10000",
                    paste0("--screenshot=", normalizePath(tmp_png, winslash = "\\", mustWork = FALSE)),
                    paste0("file:///", utils::URLencode(html_path))), stdout = FALSE, stderr = FALSE)
  if (file.exists(tmp_png)) save_output(function(p) file.copy(tmp_png, p, overwrite = TRUE), paste0(PREFIX, "figure_sn111_strengths_x.png"))
  else message("Chrome did not write the PNG; open the HTML and screenshot it at 1600 x 900")
} else message("Chrome not found: open Output/wave1_figure_sn111_strengths_x.html and save it as an image at 1600 x 900")

# ---- deck version: inline SVG for the slide's content area (1712 px wide), deck tokens -------------------
dx0 <- 600; dw <- 1000; dtop <- 46; dband <- 88; dbar <- 52
dy_axis <- dtop + dband * nrow(items)
font <- "font-family: &#39;Inter&#39;, &#39;Segoe UI&#39;, system-ui, sans-serif"
dgrid <- vapply(c(0, 25, 50, 75, 100), function(v) {
  gx <- dx0 + dw * v / 100
  if (v == 50) sprintf('<line x1="%s" x2="%s" y1="%d" y2="%d" stroke="#4A5160" stroke-width="1.5" stroke-dasharray="6 6"/>', num(gx), num(gx), dtop - 12, dy_axis)
  else sprintf('<line x1="%s" x2="%s" y1="%d" y2="%d" stroke="#B5BAC4" stroke-width="1"/>', num(gx), num(gx), dtop - 12, dy_axis)
}, "")
dticks <- vapply(c(0, 25, 50, 75, 100), function(v)
  sprintf('<text style="font-weight: 400; font-size: 18px; %s; text-anchor: middle; fill: #4A5160; font-variant-numeric: tabular-nums" x="%s" y="%d">%d</text>', font, num(dx0 + dw * v / 100), dy_axis + 34, v), "")
dbars <- vapply(seq_len(nrow(items)), function(i) {
  yc <- dtop + dband * (i - 0.5); bw <- dw * items$percentile[i] / 100
  paste0(sprintf('<text style="font-weight: 500; font-size: 22px; %s; letter-spacing: 0.14em; text-anchor: end; fill: #4A5160" x="%d" y="%s">%s</text>', font, dx0 - 32, num(yc + 8), toupper(esc(items$label[i]))),
         sprintf('<rect x="%d" y="%s" width="%s" height="%d" rx="2" fill="#2D4F8E"/>', dx0, num(yc - dbar / 2), num(bw), dbar),
         sprintf('<text style="font-weight: 500; font-size: 30px; %s; fill: #0B1220; font-variant-numeric: tabular-nums" x="%s" y="%s">%d</text>', font, num(dx0 + bw + 16), num(yc + 11), items$shown[i]))
}, "")
deck_svg <- c(
  sprintf('<svg id="wcs-root" preserveAspectRatio="xMidYMid meet" viewBox="0 0 1712 %d" xmlns="http://www.w3.org/2000/svg" version="1.1">', dy_axis + 50),
  dgrid,
  sprintf('<text style="font-weight: 500; font-size: 14px; %s; letter-spacing: 0.14em; text-anchor: middle; fill: #4A5160" x="%s" y="%d">MEDIAN SUBNET</text>', font, num(dx0 + dw / 2), dtop - 22),
  dbars, dticks, '</svg>')
save_text(deck_svg, "figure_sn111_strengths_deck.svg")
cat("figure values:", paste(sprintf("%s %d", items$label, items$shown), collapse = "; "), "\n")
