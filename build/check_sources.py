"""Compare prices read from the chain with an independent source.

For six subnets, the pool reserve ratio SubnetTAO / SubnetAlphaIn read from the archive node
is compared with the price in Taostats' pool history, at the last block before T for which
Taostats holds a pool record. Exit status 1 if a price differs by more than half a unit of
the eighth decimal (Taostats publishes eight or nine decimals).

Needs TAOSTATS_API_KEY (six calls; none if the answers are already in the cache).
Usage: python build/check_sources.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import chain, paths  # noqa: E402
from snprice.io import archive, taostats  # noqa: E402

P = "SubtensorModule"
NETUIDS = (1, 4, 64, 75, 111, 120)
TOLERANCE = 5e-9            # half a unit of the eighth decimal


def main():
    cfg = paths.snapshot()
    T = cfg["t_block"]
    arch, tao = archive(), taostats()
    worst = 0.0
    for n in NETUIDS:
        rows = tao.get("/api/dtao/pool/history/v1", netuid=n, block_end=T, limit=1, order="block_number_desc")["data"]
        if not rows:
            raise SystemExit(f"Taostats has no pool record for netuid {n}")
        block, theirs = int(rows[0]["block_number"]), float(rows[0]["price"])
        raw = arch.read([chain.key(P, "SubnetTAO", chain.u16(n)), chain.key(P, "SubnetAlphaIn", chain.u16(n))], block)
        tao_in, alpha_in = (chain.decode_uint(v) for v in raw.values())
        ours = tao_in / alpha_in
        worst = max(worst, abs(ours - theirs))
        print(f"netuid {n:3d} block {block}: chain {ours:.9f}  Taostats {theirs:.9f}  difference {abs(ours - theirs):.1e}")
    print(f"largest difference {worst:.1e} (tolerance {TOLERANCE:.0e})")
    if worst > TOLERANCE:
        sys.exit(1)


if __name__ == "__main__":
    main()
