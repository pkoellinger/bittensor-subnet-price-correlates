"""Settle the two coded white paper features: named authors, formula for the mechanism (Y9).

Reads   data/manual/whitepaper_coding_coder_A.json, data/manual/whitepaper_coding_coder_B.json
        data/manual/whitepaper_coding_third_reading.csv   (optional: netuid, item, value, reason)
        data/raw/wave<N>/whitepapers/excerpts.txt         the excerpts the coders read
Writes  data/evidence/whitepaper_coding_wave<N>.csv       both answers, quote check, final value
        data/intermediate/whitepaper_features_wave<N>.csv one row per subnet with a readable white paper

Rules as for the website facts (config/coding_protocol.md): a "yes" must quote the excerpt,
agreement of two verified answers stands, anything else needs the third reading.

Exit status 1 while items are still open.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.coding import cohen_kappa, quote_found, settle  # noqa: E402
from snprice.io import read_json, read_table, write_table  # noqa: E402

ITEMS = ("wp_named_authors", "wp_formal_mechanism")


def excerpt_blocks(text):
    blocks = {}
    for part in re.split(r"(?m)^=== SUBNET ", text)[1:]:
        blocks[int(part.split(":", 1)[0])] = part
    return blocks


def main():
    cfg = paths.snapshot()
    wave = cfg["wave"]
    blocks = excerpt_blocks((paths.raw_dir("whitepapers") / "excerpts.txt").read_text(encoding="utf-8"))
    coder = {c: {int(x["netuid"]): x for x in read_json(paths.MANUAL / f"whitepaper_coding_coder_{c}.json")} for c in "AB"}
    third_path = paths.MANUAL / "whitepaper_coding_third_reading.csv"
    third = {(int(t["netuid"]), t["item"]): t["value"] for t in (read_table(third_path) if third_path.exists() else [])}

    long_rows, wide_rows, open_items = [], [], []
    pairs = {item: ([], []) for item in ITEMS}
    for n in sorted(blocks):
        if n not in coder["A"] or n not in coder["B"]:
            raise SystemExit(f"subnet {n} is missing from a coder's file")
        final = {"netuid": n}
        for item in ITEMS:
            answers, checks = [], []
            for c in "AB":
                a = coder[c][n][item]
                value = int(a["value"])
                ok = value == 0 or quote_found(a.get("quote"), blocks[n])
                answers.append((value, a.get("quote")))
                checks.append("verified" if ok else "quote not in the excerpt")
            decided = third.get((n, item))
            decided = int(decided) if decided not in (None, "NA") else decided
            value, how = settle(answers[0][0], checks[0], answers[1][0], checks[1], decided)
            pairs[item][0].append(answers[0][0])
            pairs[item][1].append(answers[1][0])
            final[item] = value
            if how == "open":
                open_items.append((n, item))
            long_rows.append({"netuid": n, "item": item, "value_a": answers[0][0], "check_a": checks[0],
                              "quote_a": answers[0][1], "value_b": answers[1][0], "check_b": checks[1],
                              "quote_b": answers[1][1], "final": value, "how": how})
        wide_rows.append(final)

    write_table(paths.EVIDENCE / f"whitepaper_coding_wave{wave}.csv", long_rows)
    write_table(paths.INTERMEDIATE / f"whitepaper_features_wave{wave}.csv", wide_rows)
    for item in ITEMS:
        a, b = pairs[item]
        agree = sum(1 for x, y in zip(a, b) if x == y) / len(a)
        kappa = cohen_kappa(a, b)
        print(f"{item:22} documents {len(a)}  agree {agree:.2f}  kappa {kappa if kappa is None else round(kappa, 2)}  "
              f"yes A {sum(a)}  yes B {sum(b)}  final yes {sum(1 for r in wide_rows if r[item] == 1)}")
    print(f"{len(open_items)} items open: {open_items}")
    if open_items:
        sys.exit(1)


if __name__ == "__main__":
    main()
