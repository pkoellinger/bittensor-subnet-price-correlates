"""Joining two consecutive waves: what happened to each subnet of the earlier wave, and whether
the later wave's lagged columns repeat the earlier wave's values. Pure functions, no I/O.

A subnet is identified by `subnet_uid` (netuid and registration block). A netuid that was
registered anew between the waves is another subnet: the earlier one was evicted.
"""
import math


def _num(value):
    return None if value in (None, "") else float(value)


def last_seen(grid_rows):
    """Last chain sample of every registration: {subnet_uid: {"block", "price_tao"}}.

    grid_rows: samples with block, netuid, registered_block, price_tao (data/chain/grid_wave<N>.csv).
    """
    out = {}
    for r in grid_rows:
        price = _num(r["price_tao"])
        if price is None:
            continue
        uid = f"{int(r['netuid'])}-{int(r['registered_block'])}"
        block = int(r["block"])
        if uid not in out or block > out[uid]["block"]:
            out[uid] = {"block": block, "price_tao": price}
    return out


def forward_outcomes(earlier, later, last):
    """Outcomes of the earlier wave's subnets at the later wave.

    earlier, later  rows of the two waves (subnet_uid, price_tao)
    last            last_seen() of the later wave's chain samples

    evicted_fwd30    1 if the subnet no longer holds its netuid at the later snapshot
    price_tao_fwd30  price at the later snapshot (missing if evicted)
    logret_fwd30     log price change between the snapshots (missing if evicted)
    price_tao_last, last_block, logret_to_last
                     the last price observed for this subnet up to the later snapshot and the log
                     change to it; for a subnet that survived this is the later snapshot itself.
                     Leaving evicted subnets out of an analysis keeps only the survivors.
    """
    later_by_uid = {r["subnet_uid"]: r for r in later}
    out = {}
    for r in earlier:
        uid, p0 = r["subnet_uid"], _num(r["price_tao"])
        nxt = later_by_uid.get(uid)
        p1 = _num(nxt["price_tao"]) if nxt else None
        seen = last.get(uid)
        out[uid] = {
            "evicted_fwd30": int(nxt is None),
            "price_tao_fwd30": p1,
            "logret_fwd30": math.log(p1 / p0) if p0 and p1 else None,
            "price_tao_last": seen["price_tao"] if seen else None,
            "last_block": seen["block"] if seen else None,
            "logret_to_last": math.log(seen["price_tao"] / p0) if seen and p0 and seen["price_tao"] else None,
        }
    return out


def tiling_problems(earlier, later, pairs, tolerance=1e-9):
    """Where the later wave's lagged column differs from the earlier wave's column.

    pairs: [(column of the earlier wave, column of the later wave)]. Only subnets present in
    both waves are compared. Returns (subnet_uid, column, value, lagged column, value) tuples.
    """
    later_by_uid = {r["subnet_uid"]: r for r in later}
    problems = []
    for r in earlier:
        nxt = later_by_uid.get(r["subnet_uid"])
        if nxt is None:
            continue
        for now, lagged in pairs:
            a, b = r.get(now), nxt.get(lagged)
            x, y = _num(a), _num(b)
            if x is None and y is None:
                continue
            if x is None or y is None or abs(x - y) > tolerance * max(1.0, abs(x), abs(y)):
                problems.append((r["subnet_uid"], now, a, lagged, b))
    return problems
