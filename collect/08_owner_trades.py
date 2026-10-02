"""Owner buying and selling of its own subnet's alpha (Y14).

Source: Taostats /api/delegation/v1 for the owner coldkey (as of T) on its own subnet,
over the 90 days before T. Transfers are dropped and moves between validators are netted
out (snprice.events.net_owner_trades). The owner cut received in a window is 18% of the
subnet's alpha emission, read from the chain, over the blocks at which the subnet emitted
(from its first emission block on). The ratio of alpha sold to owner cut is missing when
no owner cut was received.

These are flows through the pool: a purchase moves the price in the same window by
construction. The codebook marks them `mechanical (flow)`; the lagged columns exist so
that earlier flows can be related to later price changes.

Writes  data/intermediate/owner_trades_wave<N>.csv   one row per subnet
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import chain, paths  # noqa: E402
from snprice.events import net_owner_trades  # noqa: E402
from snprice.io import archive, read_table, taostats, write_table  # noqa: E402
from snprice.windows import bounds, emitting_blocks  # noqa: E402

P = "SubtensorModule"
RAO = 10 ** 9


def main():
    cfg = paths.snapshot()
    wave, T = cfg["wave"], cfg["t_block"]
    roster = read_table(paths.CHAIN / f"roster_wave{wave}.csv")
    history = {int(r["netuid"]): r for r in read_table(paths.INTERMEDIATE / f"history_wave{wave}.csv")}
    tao, arch = taostats(), archive()

    w_lo, w_hi = bounds(cfg, "window")
    l_lo, l_hi = bounds(cfg, "lag")
    long_lo, _ = bounds(cfg, "window", days=cfg["long_window_days"])
    netuids = [int(r["netuid"]) for r in roster]

    # owner cut per block = SubnetOwnerCut (u16 fraction) x alpha-out emission of the subnet
    cut_raw = arch.read([chain.key(P, "SubnetOwnerCut")], T)[chain.key(P, "SubnetOwnerCut")]
    cut = chain.decode_uint(cut_raw, default=11796) / 65535.0
    emission = {b: arch.read_map(P, "SubnetAlphaOutEmission", netuids, b) for b in (T, w_lo, l_lo)}
    print(f"owner cut {cut:.4f}", flush=True)

    rows = []
    for i, r in enumerate(roster, 1):
        n, owner, reg_block = int(r["netuid"]), r["owner_coldkey"], int(r["registered_block"])
        first_emission = int(r["first_emission_block"]) if r["first_emission_block"] else None
        start = max(long_lo, reg_block)
        events = tao.get_all("/api/delegation/v1", per_page=200, nominator=owner, netuid=n,
                             block_start=start + 1, block_end=T) if owner else []

        def trades(lo, hi):
            lo = max(lo, reg_block)
            if lo >= hi:
                return None
            return net_owner_trades([e for e in events if lo < int(e["block_number"]) <= hi])

        def cut_alpha(lo, hi, b_lo, b_hi):
            if max(lo, reg_block) >= hi:
                return None                                    # not registered in this window
            blocks = emitting_blocks(lo, hi, first_emission)    # nothing is emitted before the first emission block
            if not blocks:
                return 0.0
            rates = [chain.decode_uint(emission[b][n]) for b in (b_lo, b_hi) if b >= reg_block]   # not a previous occupant's
            rates = [x / RAO for x in rates if x is not None]
            return cut * (sum(rates) / len(rates)) * blocks if rates else None

        w, lag, long = trades(w_lo, w_hi), trades(l_lo, l_hi), trades(long_lo, w_hi)
        cut_w, cut_l = cut_alpha(w_lo, w_hi, w_lo, T), cut_alpha(l_lo, l_hi, l_lo, w_lo)
        rows.append({
            "netuid": n,
            "owner_buy_tao_30d": w["buy_tao"] if w else None,
            "owner_sell_tao_30d": w["sell_tao"] if w else None,
            "owner_net_buy_tao_30d": w["net_buy_tao"] if w else None,
            "owner_sell_alpha_30d": w["sell_alpha"] if w else None,
            "owner_transfer_out_alpha_30d": w["transfer_out_alpha"] if w else None,
            "owner_cut_alpha_30d": cut_w,
            "owner_cut_sold_ratio_30d": (w["sell_alpha"] / cut_w) if (w and cut_w) else None,
            "owner_net_buy_tao_lag30": lag["net_buy_tao"] if lag else None,
            "owner_cut_sold_ratio_lag30": (lag["sell_alpha"] / cut_l) if (lag and cut_l) else None,
            "owner_net_buy_tao_90d": long["net_buy_tao"] if long else None,
            "owner_bought_any_90d": int(long["n_buys"] > 0) if long else None,
            "owner_trade_events_90d": len(events),
            "owner_changed_in_window": history[n]["owner_changed_in_window"],
        })
        if i % 16 == 0:
            print(f"  {i}/{len(roster)} subnets, Taostats {tao.stats}", flush=True)

    write_table(paths.INTERMEDIATE / f"owner_trades_wave{wave}.csv", rows)
    buyers = [r["netuid"] for r in rows if r["owner_bought_any_90d"]]
    print(f"wrote owner trades; owners that bought in 90 days: {len(buyers)} {buyers}")


if __name__ == "__main__":
    main()
