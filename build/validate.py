"""Checks on the assembled dataset. Exit status 1 if any check fails.

  structure    128 rows, columns exactly as in codebook.csv, unique netuid and subnet_uid
  types        binary columns hold 0 or 1, integers are whole and not negative,
               shares and indices lie between 0 and 1, day counts are not negative
  identities   relations that must hold between columns (price_usd, logret_30d, doc_score,
               bounds, counts)
  anchors      values known from independent sources (see ANCHORS)
  report       missing values and constant columns (printed, not a failure)

Usage: python build/validate.py [--final]
With --final, columns that are still empty because a collection step has not run are an error.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.io import read_table  # noqa: E402

TOL = 1e-9
# (netuid, column, expected, tolerance, where the expected value comes from)
ANCHORS = (
    (64, "price_tao", 0.07043504, 5e-9, "pool reserves of SN64 at block 9,184,186, read independently in Phase 0"),
    (95, "burn_now", 1.0, 1e-9, "MinerBurned of SN95 at T"),
    (111, "project_age_days", 107.33, 0.05, "Claims took its name on 15 Jun 2026 (team vault)"),
    (111, "exploit26_presented", 1, 0, "Claims talk at Exploit 26 on 28 Sep 2026"),
    (111, "whitepaper_available", 1, 0, "claims111.ai/whitepaper"),
)


def num(value):
    return None if value in (None, "") else float(value)


def main():
    final = "--final" in sys.argv
    cfg = paths.snapshot()
    path = paths.FINAL / f"subnets_wave{cfg['wave']}_{cfg['snapshot_date']}.csv"
    rows = read_table(path)
    codebook = read_table(paths.ROOT / "codebook.csv")
    by = {int(r["netuid"]): r for r in rows}
    problems = []

    def check(ok, message):
        if not ok:
            problems.append(message)

    # ---- structure
    check(len(rows) == 128, f"{len(rows)} rows instead of 128")
    check(list(rows[0].keys()) == [c["name"] for c in codebook], "columns differ from codebook.csv")
    check(sorted(by) == list(range(1, 129)), "netuids are not exactly 1 to 128")
    check(len({r["subnet_uid"] for r in rows}) == len(rows), "subnet_uid is not unique")

    # ---- types and ranges
    for c in codebook:
        name, kind, unit = c["name"], c["type"], c["unit"] or ""
        values = [r[name] for r in rows]
        if kind in ("integer", "binary", "number"):
            for n, v in zip(sorted(by), values):
                x = num(v)
                if x is None:
                    continue
                if kind == "binary":
                    check(x in (0.0, 1.0), f"{name}[{n}] = {v} is not 0 or 1")
                if kind == "integer":
                    check(x == int(x) and x >= 0, f"{name}[{n}] = {v} is not a non-negative whole number")
                if unit.startswith(("share 0-1", "index 0-1")):
                    check(-TOL <= x <= 1 + 1e-6, f"{name}[{n}] = {v} is outside 0 to 1")
                if unit == "days":
                    check(x >= 0, f"{name}[{n}] = {v} is negative")
                check(math.isfinite(x), f"{name}[{n}] is not finite")

    # ---- identities
    show_columns = [c["name"] for c in codebook if c["name"].startswith("podcast_") and c["name"].endswith("_12m")
                    and c["name"] not in ("podcast_episodes_12m", "podcast_shows_12m")]
    for n, r in sorted(by.items()):
        g = lambda k: num(r[k])  # noqa: E731
        if g("price_tao") is not None:
            check(abs(g("price_usd") - g("price_tao") * g("tao_usd")) < 1e-9, f"price_usd[{n}]")
        if g("logret_30d") is not None:
            check(abs(g("logret_30d") - math.log(g("price_tao") / g("price_tao_lag30"))) < 1e-9, f"logret_30d[{n}]")
        if g("doc_score") is not None:
            items = [g(k) for k in ("doc_readme", "doc_license", "doc_contributing", "doc_miner_guide",
                                    "doc_validator_guide", "doc_incentive_desc", "doc_requirements", "doc_site")]
            check(sum(items) == g("doc_score"), f"doc_score[{n}]")
        for low, high in (("holders_top10_share", "holders_top10_share_upper"), ("holders_hhi", "holders_hhi_upper"),
                          ("miners_paid_coldkeys_30d", "miners_paid_hotkeys_30d"),
                          ("miners_lineage_clusters_lb_30d", "miners_lineage_clusters_best_30d"),
                          ("miners_lineage_clusters_best_30d", "miners_paid_coldkeys_30d"),
                          ("x_posts_original_30d", "x_posts_30d"), ("podcast_shows_12m", "podcast_episodes_12m"),
                          ("exploit26_presented", "exploit26_sessions_n")):
            if g(low) is not None and g(high) is not None:
                check(g(low) <= g(high) + 1e-9, f"{low}[{n}] = {r[low]} exceeds {high} = {r[high]}")
        check(g("podcast_shows_12m") <= 6, f"podcast_shows_12m[{n}]")
        check(g("window_days_observed_30d") <= 31, f"window_days_observed_30d[{n}]")
        shows = sum(g(k) for k in show_columns)
        check(shows == g("podcast_episodes_12m"), f"podcast show counts do not add up for subnet {n}")
        if g("whitepaper_available") != 1:
            for k in ("wp_pages", "wp_references", "wp_named_authors", "wp_formal_mechanism"):
                check(r[k] in (None, ""), f"{k}[{n}] is filled although there is no white paper")
        if g("flag_no_miner_paid_30d") == 1:
            check(r["miner_hhi_coldkey_30d"] in (None, ""), f"miner_hhi_coldkey_30d[{n}] filled though nobody was paid")
        if g("startup_mode") == 1:          # no emissions yet: the chain's burn of 0 is a default, not a measurement
            for k in ("burn_now", "burn_mean_30d", "burn_time_share_ge50_30d", "days_since_first_emission",
                      "owner_cut_sold_ratio_30d", "owner_validator_div_share"):
                check(r[k] in (None, ""), f"{k}[{n}] is filled although the subnet has not started emissions")
            check(g("flag_no_miner_paid_30d") == 1 and g("miners_active_now") == 0,
                  f"subnet {n} has not started emissions but shows paid miners")
        if g("flag_full_burn_30d") == 1:
            check(g("burn_mean_30d") is not None and g("burn_mean_30d") >= 0.999, f"flag_full_burn_30d[{n}] without a burn of 1")
            check(g("flag_no_miner_paid_30d") == 1, f"flag_full_burn_30d[{n}] although a miner was paid")
        for holders in ("holders_top10_share", "holders_hhi", "holders_untraced_share"):
            if g("holders_positions_n") == 0:
                check(r[holders] in (None, ""), f"{holders}[{n}] is filled although nobody holds a stake")

    # ---- anchors
    for n, column, expected, tolerance, source in ANCHORS:
        value = num(by[n][column])
        check(value is not None and abs(value - expected) <= tolerance,
              f"anchor {column}[{n}] = {by[n][column]}, expected {expected} ({source})")

    # ---- report
    print(f"{path.name}: {len(rows)} rows, {len(codebook)} columns")
    empty, constant, gaps = [], [], []
    for c in codebook:
        values = [r[c["name"]] for r in rows]
        present = [v for v in values if v not in (None, "")]
        if not present:
            empty.append(c["name"])
        elif len(present) < len(values):
            gaps.append((c["name"], len(values) - len(present)))
        if present and len(set(present)) == 1 and c["role"] not in ("id", "outcome"):
            constant.append((c["name"], present[0]))
    print(f"columns with missing values ({len(gaps)}):")
    for name, k in gaps:
        print(f"  {name}: {k} missing")
    print("constant columns:", constant or "none")
    print("columns still empty:", empty or "none")
    if final and empty:
        problems.append(f"empty columns in a final build: {empty}")

    if problems:
        print(f"\n{len(problems)} PROBLEMS")
        for p in problems[:60]:
            print("  -", p)
        sys.exit(1)
    print("\nall checks passed")


if __name__ == "__main__":
    main()
