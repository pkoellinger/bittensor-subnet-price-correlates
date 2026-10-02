"""Join the waves into one panel and add what happened to each subnet by the next wave.

Reads   config/snapshot.json, config/snapshot_wave<N>.json        the waves that exist
        data/final/subnets_wave<N>_<date>.csv                     one file per wave
        data/chain/grid_wave<N+1>.csv                             last observed price of evicted subnets
Writes  data/final/subnets_panel.csv              one row per subnet and wave (key: subnet_uid, wave)
        data/final/subnets_panel_codebook.csv     codebook.csv plus the outcome columns added here
        (then: Rscript build/build_rds.R data/final/subnets_panel.csv data/final/subnets_panel_codebook.csv)

Rows of a wave that has a successor carry the forward outcomes (snprice.panel.forward_outcomes):
evicted_fwd30, price_tao_fwd30, logret_fwd30, price_tao_last, last_block, logret_to_last.
Rows of the latest wave have them missing.

Check: consecutive snapshot blocks lie one window apart, so the lagged window of a wave is the
feature window of the wave before it. The script compares them (snprice.panel.tiling_problems).
Columns read from the chain at a pinned block must agree, or the script stops with exit
status 1. Columns from sources that can change after the fact (GitHub, X, Taostats event
indexes) are compared and differences are listed.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.io import read_table, write_table  # noqa: E402
from snprice.panel import forward_outcomes, last_seen, tiling_problems  # noqa: E402

PINNED = [(a, b) for a, b in (
    ("price_tao", "price_tao_lag30"), ("price_tao_avg30", "price_tao_avg30_lag30"),
    ("tao_emission_on_share_30d", "tao_emission_on_share_lag30"),
    ("emission_flag_on_share_30d", "emission_flag_on_share_lag30"),
    ("reg_cost_tao_mean_30d", "reg_cost_tao_mean_lag30"),
    ("owner_lock_share_owner_alpha", "owner_lock_share_owner_alpha_lag30"),
    ("ownerhk_lock_share_issued", "ownerhk_lock_share_issued_lag30"),
    ("stake_share_owner_validator", "stake_share_owner_validator_lag30"),
    ("owner_alpha_share_issued", "owner_alpha_share_issued_lag30"),
    ("alpha_burned_share", "alpha_burned_share_lag30"),
    ("validators_n", "validators_n_lag30"),
    ("validator_stake_hhi", "validator_stake_hhi_lag30"),
)]
# burn and miner pay depend on when a subnet's first payout happened, which is worked out with the
# tempo read at each wave's own snapshot; a changed tempo can move one sample of a young subnet
LISTED = [(a, b) for a, b in (
    ("burn_mean_30d", "burn_mean_lag30"), ("burn_time_share_ge50_30d", "burn_time_share_ge50_lag30"),
    ("miners_paid_hotkeys_30d", "miners_paid_hotkeys_lag30"), ("miners_paid_coldkeys_30d", "miners_paid_coldkeys_lag30"),
    ("miner_paid_days_30d", "miner_paid_days_lag30"), ("miner_hhi_coldkey_30d", "miner_hhi_coldkey_lag30"),
    ("miner_top1_share_30d", "miner_top1_share_lag30"),
    ("owner_validator_div_share", "owner_validator_div_share_lag30"),
    ("owner_net_buy_tao_30d", "owner_net_buy_tao_lag30"), ("owner_cut_sold_ratio_30d", "owner_cut_sold_ratio_lag30"),
    ("registrations_30d", "registrations_lag30"),
    ("gh_commits_30d_repo", "gh_commits_lag30_repo"), ("gh_commits_30d_org", "gh_commits_lag30_org"),
    ("gh_authors_30d_org", "gh_authors_lag30_org"), ("gh_prs_merged_30d_org", "gh_prs_merged_lag30_org"),
    ("gh_active_days_30d_org", "gh_active_days_lag30_org"),
    ("x_posts_30d", "x_posts_lag30"), ("x_posts_original_30d", "x_posts_original_lag30"),
    ("kol_posts_30d", "kol_posts_lag30"), ("kol_pos_posts_30d", "kol_pos_posts_lag30"),
    ("kol_neg_posts_30d", "kol_neg_posts_lag30"),
)]
FORWARD = (   # name, label, type, unit
    ("evicted_fwd30", "Subnet lost its netuid before the next wave", "binary", ""),
    ("price_tao_fwd30", "Alpha price in TAO at the next wave", "number", "TAO per alpha"),
    ("logret_fwd30", "Log change of the alpha price to the next wave", "number", "log points"),
    ("price_tao_last", "Last alpha price observed up to the next wave", "number", "TAO per alpha"),
    ("last_block", "Block of the last observed price", "integer", "block"),
    ("logret_to_last", "Log change of the alpha price to the last observed price", "number", "log points"),
)


def waves():
    found = []
    for path in sorted(paths.CONFIG.glob("snapshot*.json")):
        cfg = json.loads(path.read_text(encoding="utf-8"))
        data = paths.FINAL / f"subnets_wave{cfg['wave']}_{cfg['snapshot_date']}.csv"
        if data.exists():
            found.append((cfg, data))
    return sorted(found, key=lambda w: w[0]["wave"])


def main():
    found = waves()
    if len(found) < 2:
        raise SystemExit(f"a panel needs two waves; found {len(found)} dataset(s) in data/final")
    codebook = read_table(paths.ROOT / "codebook.csv")
    columns = [c["name"] for c in codebook]
    tables = [(cfg, read_table(path)) for cfg, path in found]
    for cfg, rows in tables:
        if list(rows[0].keys()) != columns:
            raise SystemExit(f"wave {cfg['wave']} does not have the columns of codebook.csv; build it again")

    panel, failed = [], False
    for i, (cfg, rows) in enumerate(tables):
        nxt = tables[i + 1] if i + 1 < len(tables) else None
        outcomes = {}
        if nxt:
            span = cfg["window_days"] * cfg["blocks_per_day"]
            if nxt[0]["t_block"] - cfg["t_block"] != span:
                raise SystemExit(f"waves {cfg['wave']} and {nxt[0]['wave']} are not {span} blocks apart")
            grid = read_table(paths.CHAIN / f"grid_wave{nxt[0]['wave']}.csv")
            outcomes = forward_outcomes(rows, nxt[1], last_seen(grid))
            present = [(a, b) for a, b in PINNED + LISTED if a in columns and b in columns]
            hard = tiling_problems(rows, nxt[1], [p for p in present if p in PINNED])
            soft = tiling_problems(rows, nxt[1], [p for p in present if p in LISTED], tolerance=1e-6)
            evicted = sum(o["evicted_fwd30"] for o in outcomes.values())
            print(f"wave {cfg['wave']} -> {nxt[0]['wave']}: {len(rows) - evicted} subnets in both, {evicted} evicted; "
                  f"pinned columns that differ: {len(hard)}; other lagged values that differ: {len(soft)}")
            for uid, a, va, b, vb in hard[:40]:
                print(f"  PINNED {uid}: {a} = {va} but {b} = {vb}")
            for uid, a, va, b, vb in soft[:40]:
                print(f"  listed {uid}: {a} = {va}, {b} = {vb}")
            failed = failed or bool(hard)
        for r in rows:
            panel.append({**r, **outcomes.get(r["subnet_uid"], {})})

    names = columns + [f[0] for f in FORWARD]
    write_table(paths.FINAL / "subnets_panel.csv", panel, columns=names)
    extra = [{"name": name, "label": label, "type": kind, "unit": unit, "window": "to the next wave", "role": "outcome",
              "asof": "next wave", "source": "chain", "script": "build/build_panel.py", "price_link": "",
              "notes": "Missing in the latest wave."} for name, label, kind, unit in FORWARD]
    write_table(paths.FINAL / "subnets_panel_codebook.csv", codebook + extra, columns=list(codebook[0].keys()))
    print(f"wrote data/final/subnets_panel.csv: {len(panel)} rows, {len(names)} columns, "
          f"waves {[cfg['wave'] for cfg, _ in tables]}")
    if failed:
        print("columns pinned to a block differ between the waves: the panel must not be used before this is explained")
        sys.exit(1)


if __name__ == "__main__":
    main()
