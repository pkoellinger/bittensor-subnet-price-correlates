"""X accounts that a subnet links from its own home page.

On-chain identity has no field for an X handle, and Taostats and GitHub profiles cover
only part of the subnets. For subnets still without a handle after collect/10_links.py,
the home page is read (first as the server sends it, then rendered) and its links to X
profiles are listed (snprice.webtext.x_profiles).

A site that links exactly one profile supplies the handle (source "website" in
collect/10_links.py). A site that links several is listed for a decision by hand in
data/manual/links_manual.csv.

Writes  data/evidence/site_x_links_wave<N>.csv   one row per subnet examined
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.browser import http_answer, remove_profiles, render  # noqa: E402
from snprice.io import read_table, write_table  # noqa: E402
from snprice.webtext import page_links, safe_url, x_profiles  # noqa: E402


def main():
    cfg = paths.snapshot()
    wave = cfg["wave"]
    links = read_table(paths.EVIDENCE / f"links_wave{wave}.csv")
    web = {int(w["netuid"]): w for w in read_table(paths.INTERMEDIATE / f"web_wave{wave}.csv")}
    rows = []
    for link in links:
        n = int(link["netuid"])
        if link["x_handle"] and link["x_source"] != "website":
            continue
        home = safe_url(link["website_url"])
        if not home or not web[n]["website_live"] == "1":
            continue
        _, final, _, html = http_answer(home)
        base = safe_url(final) or home
        handles, how = x_profiles(page_links(html, base)), "static"
        if not handles:
            handles, how = x_profiles(page_links(render(base) or "", base)), "browser"
        rows.append({"netuid": n, "website_url": base, "x_handles": "|".join(handles), "handles_n": len(handles),
                     "how": how if handles else None})
        print(f"  SN{n}: {handles or 'no X profile linked'}", flush=True)
    remove_profiles()
    write_table(paths.EVIDENCE / f"site_x_links_wave{wave}.csv", rows)
    print(f"examined {len(rows)} sites: one profile {sum(1 for r in rows if r['handles_n'] == 1)}, "
          f"several {sum(1 for r in rows if r['handles_n'] > 1)}, none {sum(1 for r in rows if not r['handles_n'])}")


if __name__ == "__main__":
    main()
