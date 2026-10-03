"""Compare values read from the chain with an independent source (Taostats).

  prices    For six subnets, the pool reserve ratio SubnetTAO / SubnetAlphaIn read from the
            archive node against the price in Taostats' pool history, at the last block
            before T for which Taostats holds a pool record. Fails if a price differs by more
            than half a unit of the eighth decimal (Taostats publishes eight or nine decimals).
  settings  For twelve subnets, the protocol settings in the dataset (commit-reveal, Yuma 3,
            liquid alpha, number of mechanisms, maximum UIDs, registration block) against
            Taostats' subnet history at block T. Most subnets have no entry on chain for
            some of these settings (51 of 128 have none for commit-reveal), so the comparison
            also checks the defaults this project applies to absent entries.

Needs TAOSTATS_API_KEY (18 calls; none if the answers are already in the cache).
Usage: python build/check_sources.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import chain, paths  # noqa: E402
from snprice.io import archive, read_table, taostats  # noqa: E402

P = "SubtensorModule"
PRICE_NETUIDS = (1, 4, 64, 75, 111, 120)
TOLERANCE = 5e-9            # half a unit of the eighth decimal
SETTING_NETUIDS = (4, 16, 22, 26, 36, 47, 59, 64, 82, 86, 111, 120)
SETTINGS = (("commit_reveal_on", "commit_reveal_weights_enabled"), ("yuma3_on", "yuma3_on"),
            ("liquid_alpha_on", "liquid_alpha_enabled"), ("mech_count", "mech_count"), ("max_neurons", "max_neurons"))


def prices(cfg, arch, tao):
    T = cfg["t_block"]
    worst = 0.0
    for n in PRICE_NETUIDS:
        rows = tao.get("/api/dtao/pool/history/v1", netuid=n, block_end=T, limit=1, order="block_number_desc")["data"]
        if not rows:
            raise SystemExit(f"Taostats has no pool record for netuid {n}")
        block, theirs = int(rows[0]["block_number"]), float(rows[0]["price"])
        raw = arch.read([chain.key(P, "SubnetTAO", chain.u16(n)), chain.key(P, "SubnetAlphaIn", chain.u16(n))], block)
        tao_in, alpha_in = (chain.decode_uint(v) for v in raw.values())
        ours = tao_in / alpha_in
        worst = max(worst, abs(ours - theirs))
        print(f"netuid {n:3d} block {block}: chain {ours:.9f}  Taostats {theirs:.9f}  difference {abs(ours - theirs):.1e}")
    print(f"prices: largest difference {worst:.1e} (tolerance {TOLERANCE:.0e})")
    return worst <= TOLERANCE


def settings(cfg, tao):
    T = cfg["t_block"]
    data = {int(r["netuid"]): r for r in
            read_table(paths.FINAL / f"subnets_wave{cfg['wave']}_{cfg['snapshot_date']}.csv")}
    differences = []
    for n in SETTING_NETUIDS:
        rows = tao.get("/api/subnet/history/v1", netuid=n, block_end=T, frequency="by_day", limit=1,
                       order="block_number_desc")["data"]
        if not rows or int(rows[0]["block_number"]) != T:
            raise SystemExit(f"Taostats has no subnet record for netuid {n} at block {T}")
        theirs = rows[0]
        for ours_name, their_name in SETTINGS:
            if int(float(data[n][ours_name])) != int(theirs[their_name]):
                differences.append((n, ours_name, data[n][ours_name], theirs[their_name]))
        if str(theirs["registration_block_number"]) != data[n]["subnet_uid"].split("-")[1]:
            differences.append((n, "registration block", data[n]["subnet_uid"], theirs["registration_block_number"]))
    compared = len(SETTING_NETUIDS) * (len(SETTINGS) + 1)
    print(f"settings at block {T}: {compared - len(differences)} of {compared} values equal Taostats; "
          f"differences: {differences or 'none'}")
    return not differences


def main():
    cfg = paths.snapshot()
    arch, tao = archive(), taostats()
    ok = prices(cfg, arch, tao)
    ok = settings(cfg, tao) and ok
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
