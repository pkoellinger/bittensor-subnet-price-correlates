"""Concentration and share measures. Pure functions, no I/O.

A result of None always means "not defined" (for example nobody was paid).
None is written to the dataset as NA and must never be read as zero.
"""
from collections import defaultdict


def hhi_from_amounts(amounts):
    """Herfindahl index (0 to 1) of non-negative amounts; None if they sum to zero."""
    amounts = [float(a) for a in amounts]
    total = sum(amounts)
    if total <= 0:
        return None
    return sum((a / total) ** 2 for a in amounts)


def mech_weighted(mech_values, split):
    """Combine per-mechanism incentive values with the subnet's emission split.

    Subnets with two mechanisms pay incentive per mechanism; the split says which
    fraction of miner emission each mechanism receives (it can be [0, 1]).
    """
    if len(mech_values) != len(split):
        raise ValueError(f"{len(mech_values)} mechanism values for a split of length {len(split)}")
    if abs(sum(split) - 1.0) > 1e-6:
        raise ValueError(f"mechanism split sums to {sum(split)}, not 1")
    return sum(float(v) * float(s) for v, s in zip(mech_values, split))


def uid_weights(vectors, split):
    """Share of one sample's miner emission per UID, over ALL UIDs (owner rows included).

    vectors: one incentive vector per mechanism (None if the mechanism has none).
    split:   emission split between mechanisms on any scale, or None for a
             single-mechanism subnet.
    A mechanism that paid nobody, or has a split of zero, is ignored and the
    remaining mechanisms are renormalised. Returns {uid: weight} for weights
    above zero; the weights sum to 1 if anything was paid, else {} is returned.
    """
    split = [float(s) for s in (split or [1.0])]
    split += [0.0] * (len(vectors) - len(split))
    sums = [float(sum(v)) if v else 0.0 for v in vectors]
    live = [m for m in range(len(vectors)) if sums[m] > 0 and split[m] > 0]
    if not live:
        return {}
    norm = sum(split[m] for m in live)
    out = {}
    for m in live:
        share = split[m] / norm
        for uid, value in enumerate(vectors[m]):
            if value:
                out[uid] = out.get(uid, 0.0) + share * value / sums[m]
    return out


def pooled_shares(rows):
    """Share of each wallet in the incentive paid to non-owner UIDs over a window.

    rows: dicts with keys
        sample  identifier of the observation (a block)
        wallet  identity to aggregate by (coldkey, hotkey or lineage root)
        value   the UID's incentive in that sample (any scale, mechanism-weighted)
        owner   True if the UID belongs to the subnet owner (its incentive is burned)

    Within a sample every value is divided by the sample total over ALL UIDs,
    owner rows included, so a sample weighs by the fraction that was actually
    paid out (1 - burn). Shares are then pooled:

        share_i = sum_samples w_i  /  sum_samples sum_{j not owner} w_j

    Samples without any incentive are ignored.
    """
    by_sample = defaultdict(list)
    for r in rows:
        by_sample[r["sample"]].append(r)

    paid = defaultdict(float)
    paid_total = 0.0
    owner_total = 0.0
    samples = 0
    paid_samples = 0
    for sample_rows in by_sample.values():
        total = sum(float(r["value"]) for r in sample_rows)
        if total <= 0:
            continue
        samples += 1
        sample_paid = 0.0
        for r in sample_rows:
            w = float(r["value"]) / total
            if r.get("owner"):
                owner_total += w
            elif w > 0:
                paid[r["wallet"]] += w
                sample_paid += w
        if sample_paid > 0:
            paid_samples += 1
            paid_total += sample_paid

    shares = {k: v / paid_total for k, v in paid.items()} if paid_total > 0 else {}
    return {
        "shares": shares,
        "samples": samples,
        "paid_samples": paid_samples,
        "owner_share": (owner_total / samples) if samples else None,
    }


def holder_bounds(known_amounts, total):
    """Bounds on holder concentration when only the largest wallets are known.

    known_amounts: alpha per wallet for the wallets that were traced.
    total: all staked alpha that the shares refer to.

    The untraced remainder R could sit in any wallets, including the traced ones.
    The index is largest if all of R belongs to the largest traced wallet:

        HHI   in [ sum (a/S)^2 ,  sum (a/S)^2 + (2*a1*R + R^2) / S^2 ]
        top10 in [ sum_{1..10} a/S ,  that + R/S ]
    """
    known = sorted((float(a) for a in known_amounts if float(a) > 0), reverse=True)
    total = float(total)
    if total <= 0:
        return {"hhi_lower": None, "hhi_upper": None, "top10_lower": None,
                "top10_upper": None, "untraced_share": None}
    # balances and the total can be read a few blocks apart
    total = max(total, sum(known))
    rest = total - sum(known)
    lower = sum((a / total) ** 2 for a in known)
    largest = known[0] if known else 0.0
    upper = lower + (2 * largest * rest + rest ** 2) / total ** 2
    top10 = sum(known[:10]) / total
    return {
        "hhi_lower": lower,
        "hhi_upper": upper,
        "top10_lower": top10,
        "top10_upper": min(1.0, top10 + rest / total),
        "untraced_share": rest / total,
    }


def spaced_count(times, gap):
    """Number of events when events closer than `gap` to the last counted one are the same event.

    Used for podcast appearances: a live stream and its edited re-upload a few days
    later are one appearance. `times` and `gap` are in the same unit (seconds).
    """
    count, last = 0, None
    for t in sorted(times):
        if last is None or t - last >= gap:
            count += 1
            last = t
    return count
