"""Holder count and holder concentration per subnet (B1, B2).

Step 1 (Taostats): the largest stake positions of every subnet and the number of
positions. Taostats only serves the current state, so this is run right after T.
Step 2 (archive node): the alpha balance of each of those positions is re-read at
block T, summed by wallet, and related to all alpha staked on the subnet at T (the
custody wallet of validator baskets is left out of both). The untraced remainder
gives exact bounds (snprice.metrics.holder_bounds); more pages are pulled until the
remainder is at most 1% or ten pages are used.

Writes
  data/intermediate/holders_wave<N>.csv          one row per subnet
  data/intermediate/holder_wallets_wave<N>.csv   wallet-level balances at T (not committed)

Usage: 07_holders.py candidates   (step 1 only)   |   07_holders.py   (both steps)
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import chain, paths  # noqa: E402
from snprice.io import archive, read_table, taostats, write_table  # noqa: E402
from snprice.metrics import holder_bounds  # noqa: E402

P = "SubtensorModule"
RAO = 10 ** 9
PER_PAGE = 200
MAX_PAGES = 10
TARGET_UNTRACED = 0.01
BASKET_ESCROW = "5EYCAe5jLQhn6ofDSwHx3AZmsZPVFHnKpstqap4vqwDWtp7s"   # custody wallet of validator baskets


def position_page(tao, netuid, page):
    return tao.get("/api/dtao/stake_balance/latest/v1", netuid=netuid, order="balance_desc",
                   limit=PER_PAGE, page=page)


def staked_total(arch, netuids, block):
    """All alpha staked on hotkeys of a subnet (TotalAlphaStaked). Where the chain does not
    keep that total, AlphaOut - AlphaBurned - protocol-owned alpha, which is within 1% of it."""
    total = arch.read_map(P, "TotalAlphaStaked", netuids, block)
    out = arch.read_map(P, "SubnetAlphaOut", netuids, block)
    protocol = arch.read_map(P, "SubnetProtocolAlpha", netuids, block)
    burned = arch.read_map("AlphaAssets", "AlphaBurned", netuids, block,
                           part=lambda n: chain.twox64_concat(chain.u16(n)))
    return {
        n: (chain.decode_uint(total[n]) if total[n] is not None else
            chain.decode_uint(out[n], 0) - chain.decode_uint(burned[n], 0) - chain.decode_uint(protocol[n], 0)) / RAO
        for n in netuids
    }


def balances_at(arch, netuid, positions, block):
    """Alpha of each (hotkey, coldkey) position at `block` (snprice.chain.position_alpha)."""
    keys = {pos: chain.position_keys(pos[0], pos[1], netuid) for pos in positions}
    vals = arch.read(sorted({k for names in keys.values() for k in names.values()}), block)
    return {pos: chain.position_alpha({name: vals[k] for name, k in names.items()}) for pos, names in keys.items()}


def main():
    cfg = paths.snapshot()
    wave, T = cfg["wave"], cfg["t_block"]
    netuids = [int(r["netuid"]) for r in read_table(paths.CHAIN / f"roster_wave{wave}.csv")]
    tao = taostats()

    first = {}
    for n in netuids:
        first[n] = position_page(tao, n, 1)
        if n % 16 == 0:
            print(f"  candidates: netuid {n} done, Taostats {tao.stats}", flush=True)
    if len(sys.argv) > 1 and sys.argv[1] == "candidates":
        print("candidate positions cached; run again without arguments for the chain step")
        return

    arch = archive()
    staked = staked_total(arch, netuids, T)
    rows, wallet_rows = [], []
    for n in netuids:
        body, page = first[n], 1
        total_positions = (body.get("pagination") or {}).get("total_items")
        positions = {}
        while True:
            fresh = [(r["hotkey"]["ss58"], r["coldkey"]["ss58"]) for r in body["data"]]
            positions.update(balances_at(arch, n, [p for p in fresh if p not in positions], T))
            wallets = defaultdict(float)
            for (hk, ck), alpha in positions.items():
                if ck != BASKET_ESCROW:
                    wallets[ck] += alpha
            escrow = sum(a for (hk, ck), a in positions.items() if ck == BASKET_ESCROW)
            base = staked[n] - escrow
            bounds = holder_bounds(wallets.values(), base)
            more = (body.get("pagination") or {}).get("next_page")
            if not more or page >= MAX_PAGES or bounds["untraced_share"] is None \
                    or bounds["untraced_share"] <= TARGET_UNTRACED:
                break
            page += 1
            body = position_page(tao, n, page)
        rows.append({
            "netuid": n,
            "holders_positions_n": total_positions,
            "holders_positions_traced": len(positions),
            "holders_wallets_traced": len(wallets),
            "staked_alpha_at_t": round(base, 6),
            "holders_top10_share": bounds["top10_lower"],
            "holders_top10_share_upper": bounds["top10_upper"],
            "holders_hhi": bounds["hhi_lower"],
            "holders_hhi_upper": bounds["hhi_upper"],
            "holders_untraced_share": bounds["untraced_share"],
        })
        wallet_rows += [{"netuid": n, "coldkey": ck, "alpha_at_t": a} for ck, a in
                        sorted(wallets.items(), key=lambda kv: -kv[1])]
        if n % 16 == 0:
            print(f"  balances at T: netuid {n} done ({arch.calls} archive calls, Taostats {tao.stats})", flush=True)

    write_table(paths.INTERMEDIATE / f"holders_wave{wave}.csv", rows)
    write_table(paths.INTERMEDIATE / f"holder_wallets_wave{wave}.csv", wallet_rows)
    worst = sorted(rows, key=lambda r: -(r["holders_untraced_share"] or 0))[:5]
    print(f"wrote holders for {len(rows)} subnets; largest untraced shares:",
          [(r["netuid"], round(r["holders_untraced_share"] or 0, 4)) for r in worst])


if __name__ == "__main__":
    main()
