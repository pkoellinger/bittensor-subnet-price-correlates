"""Miner registrations per subnet in the feature window and the lagged window (C4).

Source: Taostats /api/subnet/neuron/registration/v1 (the count is the endpoint's
`total_items` for the block range). For a subnet registered inside a window the count
starts at its registration block.

Writes  data/intermediate/registrations_wave<N>.csv   one row per subnet
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.io import read_table, taostats, write_table  # noqa: E402
from snprice.windows import bounds  # noqa: E402


def main():
    cfg = paths.snapshot()
    wave = cfg["wave"]
    roster = read_table(paths.CHAIN / f"roster_wave{wave}.csv")
    tao = taostats()

    def count(netuid, lo, hi, reg_block):
        lo = max(lo, reg_block - 1)
        if lo >= hi:
            return None
        body = tao.get("/api/subnet/neuron/registration/v1", netuid=netuid, block_start=lo + 1, block_end=hi, limit=1)
        total = (body.get("pagination") or {}).get("total_items")
        if total is None:
            raise SystemExit(f"netuid {netuid}: registration endpoint returned no total")
        return total

    rows = []
    for i, r in enumerate(roster, 1):
        n, reg_block = int(r["netuid"]), int(r["registered_block"])
        rows.append({
            "netuid": n,
            "registrations_30d": count(n, *bounds(cfg, "window"), reg_block),
            "registrations_lag30": count(n, *bounds(cfg, "lag"), reg_block),
        })
        if i % 16 == 0:
            print(f"  {i}/{len(roster)} subnets, Taostats {tao.stats}", flush=True)
    write_table(paths.INTERMEDIATE / f"registrations_wave{wave}.csv", rows)
    vals = sorted(r["registrations_30d"] for r in rows if r["registrations_30d"] is not None)
    print(f"wrote registrations; 30-day counts: median {vals[len(vals) // 2]}, max {vals[-1]}")


if __name__ == "__main__":
    main()
