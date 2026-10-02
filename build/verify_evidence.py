"""Check, compare and settle the double coding of website facts (config/coding_protocol.md).

Reads   data/manual/web_coding_coder_A.json, data/manual/web_coding_coder_B.json
        data/manual/web_coding_third_reading.csv      (optional: netuid, item, value, reason)
        data/manual/catalog_categories_2026-08-20.csv
        data/raw/wave<N>/dossiers/<netuid>.sources.json   the saved texts the quotes must appear in
Writes  data/evidence/web_coding_wave<N>.csv          every item: both answers, evidence check, final value
        data/intermediate/web_coding_wave<N>.csv      one row per subnet with the final values

Every "yes" must quote the page it cites. An answer whose quote is not found counts as a
disagreement. Agreement of two verified answers stands; everything else needs the third
reading. For the category, the first coder is the August catalog where the subnet still has
the name it had in the catalog, and the dossier coder that is then left over serves as the
third reading when it sides with one of the two.

Where the site could not be read (a bot check, a warning of the security software on the
collecting computer, or a server error on the day), a "no" is recorded as missing: the pages
that would show a white paper, an API or a product were never seen. A "yes" backed by the
README stands.

Mailbox names are not republished: e-mail addresses in the coders' files are reduced to
"@domain" before anything is written, and quotes are compared with the pages on that basis.

Exit status 1 while items are still open.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.coding import ITEMS, check_answer, cohen_kappa, settle, without_mailboxes  # noqa: E402
from snprice.events import norm_name  # noqa: E402
from snprice.files import atomic_write  # noqa: E402
from snprice.webtext import UNREAD  # noqa: E402
from snprice.io import read_json, read_table, write_table  # noqa: E402

CATEGORY8 = {
    "Compute, Storage & Network Infrastructure": "Compute & inference",
    "AI Inference & Model Serving": "Compute & inference",
    "AI Training & Model Improvement": "Training & optimisation",
    "AI Optimization & Compression": "Training & optimisation",
    "AI Agents & Automation": "Agents, data & search",
    "Data & Database Construction": "Agents, data & search",
    "Search & Knowledge Retrieval": "Agents, data & search",
    "Forecasting & Prediction": "Finance & forecasting",
    "Financial Markets & Investing": "Finance & forecasting",
    "DeFi & Crypto Infrastructure": "DeFi & crypto infrastructure",
    "Cybersecurity, Authenticity & Verification": "Security & verification",
    "Scientific & Technical Problem Solving": "Science & robotics",
    "Robotics & Physical AI": "Science & robotics",
    "Media & Voice AI": "Media, marketing & other",
    "Marketing, Sales & Commerce": "Media, marketing & other",
    "Miscellaneous": "Media, marketing & other",
}


def same_name(a, b):
    a, b = norm_name(a), norm_name(b)
    return bool(a) and bool(b) and (a == b or a.startswith(b) or a.endswith(b) or b.startswith(a) or b.endswith(a))


def drop_mailbox_names(path):
    """Rewrite a coder's file with e-mail addresses reduced to "@domain" (nothing else changes)."""
    text = path.read_text(encoding="utf-8")
    clean = without_mailboxes(text)
    if clean != text:
        atomic_write(path, clean)
        print(f"removed mailbox names from {path.name}")


def main():
    cfg = paths.snapshot()
    wave = cfg["wave"]
    roster = {int(r["netuid"]): r for r in read_table(paths.CHAIN / f"roster_wave{wave}.csv")}
    for c in "AB":
        drop_mailbox_names(paths.MANUAL / f"web_coding_coder_{c}.json")
    coder = {c: {int(x["netuid"]): x for x in read_json(paths.MANUAL / f"web_coding_coder_{c}.json")} for c in "AB"}
    catalog = {int(r["netuid"]): r for r in read_table(paths.MANUAL / "catalog_categories_2026-08-20.csv")}
    third_path = paths.MANUAL / "web_coding_third_reading.csv"
    third = {(int(t["netuid"]), t["item"]): t["value"] for t in (read_table(third_path) if third_path.exists() else [])}
    dossiers = paths.raw_dir("dossiers")
    web = {int(w["netuid"]): w for w in read_table(paths.INTERMEDIATE / f"web_wave{wave}.csv")}

    long_rows, wide_rows, open_items = [], [], []
    pairs = {item: ([], []) for item in ITEMS}
    for n in sorted(roster):
        if n not in coder["A"] or n not in coder["B"]:
            raise SystemExit(f"subnet {n} is missing from a coder's file")
        sources = read_json(dossiers / f"{n}.sources.json") or {}
        site_unread = web[n]["website_status"] in UNREAD
        final = {}
        for item in ITEMS:
            a, b = coder["A"][n][item], coder["B"][n][item]
            va, vb = a.get("value"), b.get("value")
            ca, cb = check_answer(a, sources), check_answer(b, sources)
            if item == "category":
                for v in (va, vb):
                    if v not in CATEGORY8:
                        raise SystemExit(f"subnet {n}: unknown category {v!r}")
                if va == "Miscellaneous" and not a.get("quote"):
                    ca = "verified"                            # nothing identifiable: there is nothing to quote
                if vb == "Miscellaneous" and not b.get("quote"):
                    cb = "verified"
                left_over = None
                if same_name(catalog[n]["catalog_name"], roster[n]["subnet_name"]):
                    left_over = va if ca == "verified" else None
                    va, ca = catalog[n]["catalog_category"], "verified"        # the catalog is the first coder
                decided = third.get((n, item))
                if decided is None and va != vb and left_over in (va, vb):
                    decided = left_over
            else:
                va, vb = int(va), int(vb)
                decided = third.get((n, item))
                decided = int(decided) if decided not in (None, "NA") else decided
            value, how = settle(va, ca, vb, cb, decided)
            if item != "category" and value == 0 and site_unread:
                value, how = None, "site could not be read"   # a "no" means nothing if the site was never shown
            pairs[item][0].append(va)
            pairs[item][1].append(vb)
            final[item] = value
            if how == "open":
                open_items.append((n, item))
            long_rows.append({"netuid": n, "item": item, "value_a": va, "check_a": ca, "url_a": a.get("url"),
                              "quote_a": a.get("quote"), "value_b": vb, "check_b": cb, "url_b": b.get("url"),
                              "quote_b": b.get("quote"), "final": value, "how": how})
        url = None
        if final["whitepaper_available"] == 1:
            url = next((coder[c][n].get("whitepaper_url") for c in "AB"
                        if coder[c][n]["whitepaper_available"].get("value") in (1, "1") and coder[c][n].get("whitepaper_url")),
                       None)
        wide_rows.append({"netuid": n, **{i: final[i] for i in ITEMS}, "whitepaper_url": url,
                          "category8": CATEGORY8.get(final["category"])})

    write_table(paths.EVIDENCE / f"web_coding_wave{wave}.csv", long_rows)
    write_table(paths.INTERMEDIATE / f"web_coding_wave{wave}.csv", wide_rows)

    print("item                   agree   kappa   yes(A) yes(B)  unverified(A) unverified(B)  open")
    for item in ITEMS:
        a, b = pairs[item]
        rows = [r for r in long_rows if r["item"] == item]
        agree = sum(1 for x, y in zip(a, b) if x == y) / len(a)
        kappa = cohen_kappa(a, b)
        yes = (lambda v: sum(1 for x in v if x == 1)) if item != "category" else (lambda v: len(set(v)))
        print(f"{item:22} {agree:5.2f}   {kappa if kappa is None else round(kappa, 2)!s:5}   {yes(a):5} {yes(b):5}  "
              f"{sum(1 for r in rows if r['check_a'] != 'verified'):12} {sum(1 for r in rows if r['check_b'] != 'verified'):12}  "
              f"{sum(1 for r in rows if r['how'] == 'open'):4}")
    print(f"{len(open_items)} items open; third readings applied: {sum(1 for r in long_rows if r['how'].startswith('third'))}")
    if open_items:
        print("open:", open_items[:400])
        sys.exit(1)


if __name__ == "__main__":
    main()
