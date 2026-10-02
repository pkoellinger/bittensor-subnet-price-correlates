"""TAO price in US dollars at T and at T - 30 days (for price_usd).

Source: Taostats /api/price/history/v1 (15-minute quotes). The quote closest to the block
time is used; it must lie within 15 minutes of it.

Writes  data/intermediate/tao_usd_wave<N>.csv   one row per block (t, lag)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.io import archive, taostats, write_table  # noqa: E402
from snprice.timeutil import epoch, iso  # noqa: E402
from snprice.windows import bounds  # noqa: E402

MAX_GAP = 900


def main():
    cfg = paths.snapshot()
    wave, T = cfg["wave"], cfg["t_block"]
    arch, tao = archive(), taostats()
    rows = []
    for label, block in (("t", T), ("lag", bounds(cfg, "lag")[1])):
        when = int(arch.timestamp(block))
        quotes = tao.get("/api/price/history/v1", asset="tao", timestamp_start=when - 3600,
                         timestamp_end=when + 3600, limit=50)["data"]
        if not quotes:
            raise SystemExit(f"no TAO price quote around block {block}")
        best = min(quotes, key=lambda q: abs(epoch(q["last_updated"]) - when))
        gap = abs(epoch(best["last_updated"]) - when)
        if gap > MAX_GAP:
            raise SystemExit(f"closest TAO price quote is {gap} seconds from block {block}")
        rows.append({"label": label, "block": block, "block_utc": iso(when), "tao_usd": float(best["price"]),
                     "quote_utc": best["last_updated"]})
        print(f"{label}: block {block} at {iso(when)}: TAO = ${float(best['price']):.2f} (quote of {best['last_updated']})")
    write_table(paths.INTERMEDIATE / f"tao_usd_wave{wave}.csv", rows)


if __name__ == "__main__":
    main()
