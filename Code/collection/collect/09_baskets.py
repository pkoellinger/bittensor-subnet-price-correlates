"""Validator baskets (Y16): active trades into and out of each subnet, and holdings.

Since runtime 468 (21 Sep 2026) a root validator can trade its basket with
`swap_basket`. Each BasketSwapped event sells one subnet's alpha out of the basket
and buys another's. These discretionary trades are the measure of "funds invested".
Holdings are reported as a description only: they are mostly passive accrual of
root dividends plus the market-cap index rules that applied until 18 Sep 2026.

Sources
  Taostats /api/event/v1?full_name=SubtensorModule.BasketSwapped   (the trades)
  Taostats /api/dtao/validator/basket/history/v1                   (holdings on the snapshot day)

Writes  Temp/collection-cache/intermediate/baskets_wave<N>.csv   one row per subnet
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.events import basket_flows  # noqa: E402
from snprice.io import read_table, taostats, write_table  # noqa: E402
from snprice.windows import bounds  # noqa: E402

RAO = 10 ** 9


def main():
    cfg = paths.snapshot()
    wave = cfg["wave"]
    netuids = [int(r["netuid"]) for r in read_table(paths.CHAIN / f"roster_wave{wave}.csv")]
    state = {int(r["netuid"]): r for r in read_table(paths.CHAIN / f"state_wave{wave}.csv") if r["label"] == "t"}
    tao = taostats()

    flows = {}
    for name in ("window", "lag"):
        lo, hi = bounds(cfg, name)
        events = tao.get_all("/api/event/v1", per_page=200, full_name="SubtensorModule.BasketSwapped",
                             block_start=lo + 1, block_end=hi)
        flows[name] = basket_flows(events)
        total = sum(v["net_tao"] for v in flows[name].values())
        if abs(total) > 1e-6:
            raise SystemExit(f"{name}: basket flows sum to {total}, expected zero")
        first = min((int(e["block_number"]) for e in events), default=None)
        print(f"{name}: {len(events)} BasketSwapped events (first at block {first})", flush=True)

    baskets = tao.get_all("/api/dtao/validator/basket/history/v1", per_page=200,
                          day_start=cfg["snapshot_date"], day_end=cfg["snapshot_date"])
    held = defaultdict(float)
    for b in baskets:
        for h in b.get("holdings") or []:
            held[int(h["netuid"])] += int(h["alpha"]) / RAO
    print(f"{len(baskets)} validator baskets on {cfg['snapshot_date']}", flush=True)

    rows = []
    for n in netuids:
        w, lag = flows["window"].get(n), flows["lag"].get(n)
        issued = float(state[n]["alpha_issued"])
        rows.append({
            "netuid": n,
            "baskets_net_buyers_n_30d": w["net_buyers"] if w else 0,
            "baskets_net_sellers_n_30d": w["net_sellers"] if w else 0,
            "basket_net_buy_tao_30d": w["net_tao"] if w else 0.0,
            "basket_swaps_n_30d": w["n_swaps"] if w else 0,
            # trading did not exist in the lagged window: NA, not zero
            "basket_net_buy_tao_lag30": (lag["net_tao"] if lag else 0.0) if flows["lag"] else None,
            "basket_alpha_held": round(held.get(n, 0.0), 6),
            "basket_alpha_share_issued": held.get(n, 0.0) / issued if issued > 0 else None,
        })
    write_table(paths.INTERMEDIATE / f"baskets_wave{wave}.csv", rows)
    top = sorted(rows, key=lambda r: -r["basket_net_buy_tao_30d"])[:5]
    print("wrote baskets; largest net buys (netuid, TAO, net buyers):",
          [(r["netuid"], round(r["basket_net_buy_tao_30d"], 1), r["baskets_net_buyers_n_30d"]) for r in top])


if __name__ == "__main__":
    main()
