"""Posts by approved commentators that name a subnet: settle the two codings and count (Y19, Y20).

Reads   data/evidence/kol_mentions_wave<N>.csv      post-subnet pairs found by collect/14_kol.py posts
        data/manual/kol_polarity_coder_A.json, data/manual/kol_polarity_coder_B.json
                                                    [{"post_id": ..., "netuid": ..., "label": ...}]
Writes  data/evidence/kol_coding_wave<N>.csv        every pair: both labels, whether it counts, polarity
        data/intermediate/kol_wave<N>.csv           one row per subnet; 0 where no counted post names it

Labels and their use: config/polarity_criteria.md, snprice.kol.mention_decision. The files
hold post IDs and labels, never post text.

Exit status 1 while a pair lacks a label from either coder.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.coding import cohen_kappa  # noqa: E402
from snprice.io import archive, read_json, read_table, write_table  # noqa: E402
from snprice.kol import mention_counts, mention_decision  # noqa: E402
from snprice.timeutil import epoch  # noqa: E402


def main():
    cfg = paths.snapshot()
    wave = cfg["wave"]
    days, month = cfg["long_window_days"], cfg["window_days"]
    mentions = read_table(paths.EVIDENCE / f"kol_mentions_wave{wave}.csv")
    labels = {}
    for coder in "AB":
        rows = read_json(paths.MANUAL / f"kol_polarity_coder_{coder}.json")
        if rows is None:
            raise SystemExit(f"data/manual/kol_polarity_coder_{coder}.json is missing")
        labels[coder] = {(str(r["post_id"]), int(r["netuid"])): r["label"] for r in rows}

    coded, counted, open_pairs = [], [], []
    for m in mentions:
        key = (str(m["post_id"]), int(m["netuid"]))
        a, b = labels["A"].get(key), labels["B"].get(key)
        if a is None or b is None:
            open_pairs.append(key)
            continue
        counts, polarity = mention_decision(m["strength"], a, b)
        coded.append({**m, "label_a": a, "label_b": b, "counts": int(counts), "polarity": polarity})
        if counts:
            counted.append({"post_id": key[0], "username": m["username"], "created": epoch(m["created"]),
                            "netuid": key[1], "polarity": polarity})
    if open_pairs:
        print(f"{len(open_pairs)} post-subnet pairs lack a label from a coder, for example {open_pairs[:10]}")
        sys.exit(1)

    t_end = int(archive().timestamp(cfg["t_block"]))
    per_subnet = mention_counts(counted, t_end, window_days=days, month_days=month)
    columns = [f"kol_posts_{days}d", f"kol_accounts_{days}d", f"kol_pos_posts_{days}d", f"kol_neg_posts_{days}d",
               f"kol_posts_{month}d", f"kol_pos_posts_{month}d", f"kol_neg_posts_{month}d",
               f"kol_posts_lag{month}", f"kol_pos_posts_lag{month}", f"kol_neg_posts_lag{month}"]
    roster = read_table(paths.CHAIN / f"roster_wave{wave}.csv")
    rows = [{"netuid": int(r["netuid"]), **{c: per_subnet.get(int(r["netuid"]), {}).get(c, 0) for c in columns}}
            for r in roster]

    write_table(paths.EVIDENCE / f"kol_coding_wave{wave}.csv", coded)
    write_table(paths.INTERMEDIATE / f"kol_wave{wave}.csv", rows, columns=["netuid"] + columns)

    a, b = [c["label_a"] for c in coded], [c["label_b"] for c in coded]
    agree = sum(1 for x, y in zip(a, b) if x == y) / len(coded) if coded else None
    kappa = cohen_kappa(a, b) if coded else None
    print(f"{len(coded)} post-subnet pairs coded; the coders agree on {agree:.0%} (Cohen's kappa "
          f"{kappa if kappa is None else round(kappa, 2)})" if coded else "no pair to code")
    print(f"counted: {len(counted)} pairs, {sum(1 for c in counted if c['polarity'] == 'positive')} positive, "
          f"{sum(1 for c in counted if c['polarity'] == 'negative')} negative; dropped as not about the subnet: "
          f"{len(coded) - len(counted)}")
    print(f"subnets named at least once in {days} days: {sum(1 for r in rows if r[columns[0]])} of {len(rows)}")


if __name__ == "__main__":
    main()
