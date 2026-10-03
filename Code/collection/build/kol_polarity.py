"""Posts by approved commentators that name a subnet: settle the two codings and count (Y19, Y20).

Reads   data/evidence/kol_mentions_wave<N>.csv      post-subnet pairs found by collect/14_kol.py posts
        data/manual/kol_polarity_wave<N>_coder_A.json, ..._coder_B.json
                                                    [{"post_id": ..., "netuid": ..., "label": ...}]
        data/manual/kol_attribution_wave<N>_reader_A.json, ..._reader_B.json
                                                    for pairs matched by the number alone:
                                                    [{"post_id": ..., "netuid": ..., "refers_to_current": ..., "reason": ...}]
Writes  data/evidence/kol_coding_wave<N>.csv        every pair: both labels, both readings, whether it counts, polarity
        Temp/collection-cache/intermediate/kol_wave<N>.csv           one row per subnet; 0 where no counted post names it

Labels and their use: config/polarity_criteria.md, snprice.kol.mention_decision. A netuid
is reused, so a number in a post can mean an earlier project: pairs matched by the number
alone are read by two readers and dropped if both say so (config/kol_attribution.md,
snprice.kol.stands_for_current). The files hold post IDs, labels and readings, never post
text. A follow-up wave reuses the labels and readings of earlier waves for posts in the
overlapping days, as long as the netuid still belongs to the same subnet
(snprice.io.polarity_labels, attribution_readings).

Exit status 1 while a pair lacks a label from either coder or a reading from either reader.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.coding import cohen_kappa  # noqa: E402
from snprice.io import archive, attribution_readings, polarity_labels, read_table, write_table  # noqa: E402
from snprice.kol import by_number_alone, mention_counts, mention_decision, stands_for_current  # noqa: E402
from snprice.timeutil import epoch  # noqa: E402


def main():
    cfg = paths.snapshot()
    wave = cfg["wave"]
    days, month = cfg["long_window_days"], cfg["window_days"]
    mentions = read_table(paths.EVIDENCE / f"kol_mentions_wave{wave}.csv")
    labels = {coder: polarity_labels(cfg, coder) for coder in "AB"}     # this wave's labels and those carried over
    readings = {reader: attribution_readings(cfg, reader) for reader in "AB"}

    coded, counted, open_pairs, unread = [], [], [], []
    for m in mentions:
        key = (str(m["post_id"]), int(m["netuid"]))
        a, b = labels["A"].get(key), labels["B"].get(key)
        if a is None or b is None:
            open_pairs.append(key)
            continue
        current_a = current_b = None            # only a number can mean an earlier project
        if by_number_alone(m["rules"]):
            current_a, current_b = readings["A"].get(key), readings["B"].get(key)
            if current_a is None or current_b is None:
                unread.append(key)
                continue
        counts, polarity = mention_decision(m["strength"], a, b)
        if current_a is not None and not stands_for_current(current_a, current_b):
            counts, polarity = False, None
        coded.append({**m, "label_a": a, "label_b": b, "current_a": current_a, "current_b": current_b,
                      "counts": int(counts), "polarity": polarity})
        if counts:
            counted.append({"post_id": key[0], "username": m["username"], "created": epoch(m["created"]),
                            "netuid": key[1], "polarity": polarity})
    if open_pairs:
        print(f"{len(open_pairs)} post-subnet pairs lack a label from a coder, for example {open_pairs[:10]}")
    if unread:
        print(f"{len(unread)} pairs matched by the number alone lack a reading (build/coding_material.py attribution "
              f"prepare, config/kol_attribution.md), for example {unread[:10]}")
    if open_pairs or unread:
        sys.exit(1)

    t_end = int(archive().timestamp(cfg["t_block"]))
    per_subnet = mention_counts(counted, t_end, window_days=days, month_days=month)
    columns = [f"kol_posts_{days}d", f"kol_accounts_{days}d", f"kol_pos_posts_{days}d", f"kol_neg_posts_{days}d",
               f"kol_posts_{month}d", f"kol_pos_posts_{month}d", f"kol_neg_posts_{month}d",
               f"kol_posts_lag{month}", f"kol_pos_posts_lag{month}", f"kol_neg_posts_lag{month}"]
    roster = read_table(paths.CHAIN / f"roster_wave{wave}.csv")
    rows = [{"netuid": int(r["netuid"]), **{c: per_subnet.get(int(r["netuid"]), {}).get(c, 0) for c in columns}}
            for r in roster]

    write_table(paths.EVIDENCE / f"kol_coding_wave{wave}.csv", coded,
                columns=list(mentions[0].keys()) + ["label_a", "label_b", "current_a", "current_b", "counts", "polarity"]
                if mentions else None)
    write_table(paths.INTERMEDIATE / f"kol_wave{wave}.csv", rows, columns=["netuid"] + columns)

    a, b = [c["label_a"] for c in coded], [c["label_b"] for c in coded]
    agree = sum(1 for x, y in zip(a, b) if x == y) / len(coded) if coded else None
    kappa = cohen_kappa(a, b) if coded else None
    print(f"{len(coded)} post-subnet pairs coded; the coders agree on {agree:.0%} (Cohen's kappa "
          f"{kappa if kappa is None else round(kappa, 2)})" if coded else "no pair to code")
    numbered = [c for c in coded if c["current_a"] is not None]
    other = [c for c in numbered if not stands_for_current(c["current_a"], c["current_b"])]
    print(f"matched by the number alone: {len(numbered)} pairs; both readers say the number means another project "
          f"or no subnet: {len(other)}; the readers differ on {sum(1 for c in numbered if c['current_a'] != c['current_b'])}")
    print(f"counted: {len(counted)} pairs, {sum(1 for c in counted if c['polarity'] == 'positive')} positive, "
          f"{sum(1 for c in counted if c['polarity'] == 'negative')} negative; dropped: {len(coded) - len(counted)} "
          f"({len(other)} for the number, the rest because the coders say the post is not about the subnet)")
    print(f"subnets named at least once in {days} days: {sum(1 for r in rows if r[columns[0]])} of {len(rows)}")


if __name__ == "__main__":
    main()
