"""Compare the documentation checklist with a reader's judgment of the same repositories.

The checklist (doc_* columns, fixed rules in snprice/github.py) was checked against two
samples of 15 repositories each, read by an independent coder who did not see the rules'
output: data/manual/doc_checklist_hand_check.json (sample 1) and
data/manual/doc_checklist_hand_check_2.json (sample 2). The rules were corrected once, after
sample 1; sample 2 was drawn afterwards and is the out-of-sample check.

Prints the share of agreeing answers per sample and per item, and every disagreement.
Usage: python build/check_doc_checklist.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.github import DOC_ITEMS  # noqa: E402
from snprice.io import read_table  # noqa: E402


def main():
    cfg = paths.snapshot()
    data = {int(r["netuid"]): r for r in read_table(paths.FINAL / f"subnets_wave{cfg['wave']}_{cfg['snapshot_date']}.csv")}
    for path in sorted(paths.MANUAL.glob("doc_checklist_hand_check*.json")):
        hand = json.loads(path.read_text(encoding="utf-8"))
        agree = {item: 0 for item in DOC_ITEMS}
        misses = []
        for row in hand:
            n = int(row["netuid"])
            for item in DOC_ITEMS:
                rule = data[n][item]
                if rule is None:
                    raise SystemExit(f"subnet {n} has no checklist value for {item}")
                if int(rule) == int(row[item]):
                    agree[item] += 1
                else:
                    misses.append(f"    subnet {n:3d} {item}: rule {rule}, reader {row[item]}")
        total = len(hand) * len(DOC_ITEMS)
        print(f"{path.name}: {len(hand)} repositories, {sum(agree.values())} of {total} answers agree "
              f"({sum(agree.values()) / total:.1%})")
        for item in DOC_ITEMS:
            print(f"  {item:22s} {agree[item]:2d} of {len(hand)}")
        print("\n".join(misses))


if __name__ == "__main__":
    main()
