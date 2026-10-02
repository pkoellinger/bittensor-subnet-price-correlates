"""Aggregate the 900-block chain samples to one row per subnet and window.

Price (Y1, Y2), miner burn (Y3), miner counts and concentration by wallet (Y4, D1),
emission flag (Y15), registration cost (C3).

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
from snprice.io import read_table, write_table  # noqa: E402
from snprice.metrics import hhi_from_amounts, pooled_shares  # noqa: E402
from snprice.windows import sample_blocks  # noqa: E402

IP_MIN_COVERAGE = 0.5


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


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
            row[f"samples_observed_{w}"] = len(samples)
            row[f"window_days_observed_{w}"] = len({day_of[int(s["block"])] for s in samples})
            row[f"price_tao_avg{'30' if w == '30d' else '30_lag30'}"] = mean(
                [float(s["price_tao"]) for s in samples if s["price_tao"]])
            burns = [float(s["miner_burned"]) for s in samples]
            row[f"burn_mean_{w}"] = mean(burns)
            row[f"burn_time_share_ge50_{w}"] = mean([float(b >= 0.5) for b in burns])
            row[f"emission_enabled_days_share_{w}"] = mean([float(s["emission_enabled"]) for s in samples])
            row[f"reg_cost_tao_mean_{w}"] = mean([float(s["reg_cost_tao"]) for s in samples if s["reg_cost_tao"]])

            rows = incentive[n][w]
            pooled = pooled_shares({"sample": r["block"], "wallet": r["coldkey"] or r["hotkey"],
                                    "value": float(r["weight"]), "owner": r["owner"] == "1"} for r in rows)
            paid = [r for r in rows if r["owner"] != "1"]
            hotkeys = {r["hotkey"] for r in paid}
            with_ip = {r["hotkey"] for r in paid if r["ip"]}
            coverage = len(with_ip) / len(hotkeys) if hotkeys else None
            shares = pooled["shares"]
            row.update({
                f"miners_paid_hotkeys_{w}": len(hotkeys),
                f"miners_paid_coldkeys_{w}": len(shares),
                f"miner_paid_days_{w}": len({day_of[int(r["block"])] for r in paid}),
                f"miner_hhi_coldkey_{w}": hhi_from_amounts(shares.values()),
                f"miner_top1_share_{w}": max(shares.values()) if shares else None,
                f"miners_ip_coverage_{w}": coverage,
                f"miners_distinct_ips_{w}": (len({r["ip"] for r in paid if r["ip"]})
                                             if coverage is not None and coverage >= IP_MIN_COVERAGE else None),
                f"owner_incentive_share_{w}": pooled["owner_share"],
            })
            first_reg, ips = {}, defaultdict(set)
            for r in paid:
                wallet = r["coldkey"] or r["hotkey"]
                if r["uid_registered_block"]:
                    first_reg[wallet] = min(first_reg.get(wallet, 10 ** 12), int(r["uid_registered_block"]))
                if r["ip"]:
                    ips[wallet].add(r["ip"])
            for wallet, share in sorted(shares.items(), key=lambda kv: -kv[1]):
                share_rows.append({"netuid": n, "window": w, "coldkey": wallet, "share": repr(share),
                                   "first_registered_block": first_reg.get(wallet),
                                   "ips": "|".join(sorted(ips[wallet]))})
            row[f"flag_no_miner_paid_{w}"] = int(not shares)
            row[f"flag_full_burn_{w}"] = int(bool(burns) and min(burns) >= 0.999)

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
