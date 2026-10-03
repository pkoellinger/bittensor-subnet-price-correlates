"""One subnet, one window: summary of the chain samples (price, burn, flags, paid miners)."""
from .metrics import hhi_from_amounts, pooled_shares

IP_MIN_COVERAGE = 0.5      # the IP count is reported only if at least half of the paid hotkeys publish an IP

VALUE_KEYS = ("price_tao_avg", "burn_mean", "burn_time_share_ge50", "emission_flag_on_share",
              "tao_emission_on_share", "reg_cost_tao_mean", "miners_paid_hotkeys", "miners_paid_coldkeys",
              "miner_paid_days", "miner_hhi_coldkey", "miner_top1_share", "miners_ip_coverage",
              "miners_distinct_ips", "owner_incentive_share", "flag_no_miner_paid", "flag_full_burn")


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _num(value):
    return None if value is None or value == "" else float(value)


def emissions_paid_after(first_emission, tempo):
    """Block after which a subnet has certainly paid emissions at least once.

    A subnet pays miners at the end of each tempo. Between its registration and the end of
    the first tempo after its emissions start, nobody is paid and the chain's MinerBurned
    holds its default of 0. None if the emissions have not started.
    """
    return None if first_emission is None else int(first_emission) + int(tempo)


def measured_blocks(rows, paid_after):
    """Blocks at which the chain's MinerBurned is a measurement.

    MinerBurned is the incentive withheld from the owner's UIDs divided by all incentive.
    It is a measurement only where the subnet pays emissions (block after `paid_after`) and
    some UID holds incentive (the block has incentive rows). Elsewhere the chain stores 0.
    """
    if paid_after is None:
        return set()
    return {int(r["block"]) for r in rows if int(r["block"]) > paid_after}


def window_summary(samples, rows, day_of, paid_after):
    """Summarise a window.

    samples     grid rows of the subnet in the window (block, price_tao, miner_burned,
                emission_enabled, tao_in_emission, reg_cost_tao), only blocks at which the
                current occupant of the netuid was registered
    rows        incentive rows at those blocks (block, coldkey, hotkey, weight, owner, ip)
    day_of      block -> UTC date
    paid_after  emissions_paid_after() of the subnet

    A window without samples (subnet not yet registered) gives missing values, never zeros.
    Burn and miner payments are taken only from blocks at which the subnet paid emissions:
    incentive held before that pays nobody. Price, emission shares and registration cost use
    every sample.
    "shares" holds each paying wallet's share of the incentive paid to non-owner UIDs.
    """
    out = {"samples_observed": len(samples),
           "window_days_observed": len({day_of[int(s["block"])] for s in samples}),
           "shares": {}}
    if not samples:
        out.update({k: None for k in VALUE_KEYS})
        return out

    measured = measured_blocks(rows, paid_after)
    rows = [r for r in rows if int(r["block"]) in measured]
    burns = [_num(s["miner_burned"]) for s in samples if int(s["block"]) in measured]
    out["price_tao_avg"] = _mean([_num(s["price_tao"]) for s in samples])
    out["burn_mean"] = _mean(burns)
    out["burn_time_share_ge50"] = _mean([float(b >= 0.5) for b in burns if b is not None])
    out["emission_flag_on_share"] = _mean([_num(s["emission_enabled"]) for s in samples])
    emitted = [_num(s.get("tao_in_emission")) for s in samples]
    out["tao_emission_on_share"] = _mean([float(e > 0) for e in emitted if e is not None])
    out["reg_cost_tao_mean"] = _mean([_num(s["reg_cost_tao"]) for s in samples])

    pooled = pooled_shares({"sample": r["block"], "wallet": r["coldkey"] or r["hotkey"],
                            "value": float(r["weight"]), "owner": str(r["owner"]) == "1"} for r in rows)
    shares = pooled["shares"]
    paid = [r for r in rows if str(r["owner"]) != "1"]
    hotkeys = {r["hotkey"] for r in paid}
    with_ip = {r["hotkey"] for r in paid if r["ip"]}
    coverage = len(with_ip) / len(hotkeys) if hotkeys else None
    known = [b for b in burns if b is not None]
    out.update({
        "shares": shares,
        "miners_paid_hotkeys": len(hotkeys),
        "miners_paid_coldkeys": len(shares),
        "miner_paid_days": len({day_of[int(r["block"])] for r in paid}),
        "miner_hhi_coldkey": hhi_from_amounts(shares.values()),
        "miner_top1_share": max(shares.values()) if shares else None,
        "miners_ip_coverage": coverage,
        "miners_distinct_ips": (len({r["ip"] for r in paid if r["ip"]})
                                if coverage is not None and coverage >= IP_MIN_COVERAGE else None),
        "owner_incentive_share": pooled["owner_share"],
        "flag_no_miner_paid": int(not shares),
        "flag_full_burn": int(bool(known) and min(known) >= 0.999),
    })
    return out
