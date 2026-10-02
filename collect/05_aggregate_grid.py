"""Aggregate the 900-block chain samples to one row per subnet and window.

Price (Y1, Y2), miner burn (Y3), miner counts and concentration by wallet (Y4, D1),
emission flag and TAO injection (Y15), registration cost (C3). The arithmetic of a window
is in snprice/aggregate.py.

A sample is used for a subnet only if the subnet that occupies the netuid at T was
already registered at that block, so values of a previous occupant never enter.

Reads   data/chain/grid_wave<N>.csv, data/chain/blocks_wave<N>.csv,
        data/intermediate/incentive_wave<N>.csv.gz
Writes  data/intermediate/grid_agg_wave<N>.csv        one row per subnet
        data/intermediate/miner_shares_wave<N>.csv    wallet-level shares per subnet and window (not committed)
"""
import csv
import gzip
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.aggregate import window_summary  # noqa: E402
from snprice.io import read_table, write_table  # noqa: E402
from snprice.windows import sample_blocks  # noqa: E402


def main():
    cfg = paths.snapshot()
    wave, T = cfg["wave"], cfg["t_block"]
    roster = {int(r["netuid"]): r for r in read_table(paths.CHAIN / f"roster_wave{wave}.csv")}
    day_of = {int(r["block"]): r["utc"][:10] for r in read_table(paths.CHAIN / f"blocks_wave{wave}.csv")}
    window_blocks = {"30d": set(sample_blocks(cfg, "window")), "lag30": set(sample_blocks(cfg, "lag"))}
    lag_end = max(window_blocks["lag30"])

    grid = defaultdict(dict)                       # netuid -> block -> row
    for r in read_table(paths.CHAIN / f"grid_wave{wave}.csv"):
        n, b = int(r["netuid"]), int(r["block"])
        if int(r["registered_block"]) == int(roster[n]["registered_block"]):
            grid[n][b] = r                          # same occupant as at T

    incentive = defaultdict(lambda: defaultdict(list))   # netuid -> window -> rows
    with gzip.open(paths.INTERMEDIATE / f"incentive_wave{wave}.csv.gz", "rt", encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            n, b = int(r["netuid"]), int(r["block"])
            if b not in grid[n]:
                continue
            for w, blocks in window_blocks.items():
                if b in blocks:
                    incentive[n][w].append(r)

    out, share_rows = [], []
    for n in sorted(roster):
        row = {"netuid": n}
        at_t = grid[n].get(T)
        at_lag = grid[n].get(lag_end)
        row["price_tao"] = float(at_t["price_tao"]) if at_t and at_t["price_tao"] else None
        row["price_tao_lag30"] = float(at_lag["price_tao"]) if at_lag and at_lag["price_tao"] else None
        row["logret_30d"] = (math.log(row["price_tao"] / row["price_tao_lag30"])
                             if row["price_tao"] and row["price_tao_lag30"] else None)
        row["burn_now"] = float(at_t["miner_burned"]) if at_t else None
        row["reg_cost_tao_now"] = float(at_t["reg_cost_tao"]) if at_t and at_t["reg_cost_tao"] else None

        for w, blocks in window_blocks.items():
            samples = [grid[n][b] for b in sorted(blocks) if b in grid[n]]
            rows = incentive[n][w]
            summary = window_summary(samples, rows, day_of)
            shares = summary.pop("shares")
            for key, value in summary.items():
                name = f"price_tao_avg{'30' if w == '30d' else '30_lag30'}" if key == "price_tao_avg" else f"{key}_{w}"
                row[name] = value

            first_reg, ips = {}, defaultdict(set)
            for r in rows:
                if r["owner"] == "1":
                    continue
                wallet = r["coldkey"] or r["hotkey"]
                if r["uid_registered_block"]:
                    first_reg[wallet] = min(first_reg.get(wallet, 10 ** 12), int(r["uid_registered_block"]))
                if r["ip"]:
                    ips[wallet].add(r["ip"])
            for wallet, share in sorted(shares.items(), key=lambda kv: -kv[1]):
                share_rows.append({"netuid": n, "window": w, "coldkey": wallet, "share": repr(share),
                                   "first_registered_block": first_reg.get(wallet),
                                   "ips": "|".join(sorted(ips[wallet]))})

        now = [r for r in incentive[n]["30d"] if int(r["block"]) == T and r["owner"] != "1"]
        row["miners_active_now"] = len(now) if at_t else None
        out.append(row)

    write_table(paths.INTERMEDIATE / f"grid_agg_wave{wave}.csv", out)
    write_table(paths.INTERMEDIATE / f"miner_shares_wave{wave}.csv", share_rows)
    paid_any = sum(1 for r in out if r["miners_paid_coldkeys_30d"])
    traced = sum(1 for s in share_rows if s["window"] == "30d" and float(s["share"]) >= cfg["lineage_share_floor"])
    print(f"wrote grid aggregates for {len(out)} subnets; {paid_any} paid at least one miner in the 30-day window")
    print(f"  wallets paid in the 30-day window: {sum(1 for s in share_rows if s['window'] == '30d')}, "
          f"of which at or above the {cfg['lineage_share_floor']:.1%} share floor: {traced}")
    probe = next(r for r in out if r["netuid"] == 111)
    print("  SN111:", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in probe.items()
                       if k in ("price_tao", "price_tao_avg30", "burn_mean_30d", "miners_paid_coldkeys_30d",
                                "miner_hhi_coldkey_30d", "miner_top1_share_30d", "miner_paid_days_30d",
                                "miners_ip_coverage_30d", "miners_active_now")})


if __name__ == "__main__":
    main()
