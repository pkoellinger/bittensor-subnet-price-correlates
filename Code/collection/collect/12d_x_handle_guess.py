"""X accounts of subnets for which no source lists a handle: guessed, then verified.

For each named subnet still without a handle after collect/10_links.py, handles are built
from its name, GitHub owner and website (snprice.handles.candidate_handles) and looked up
through the X API. A guess is accepted only if the profile points back to the subnet: it
links the subnet's site, or its text names the subnet together with its number
(snprice.handles.profile_matches). Everything else is discarded.

Profile lookups cost $0.01 per existing account and are booked in the spending ledger.

Writes  data/evidence/x_handle_guess_wave<N>.csv   one row per subnet examined
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.handles import candidate_handles, profile_matches  # noqa: E402
from snprice.io import ledger, read_table, write_table  # noqa: E402
from snprice.xapi import XClient  # noqa: E402

FIELDS = "created_at,public_metrics,verified,description,url,entities"


def main():
    cfg = paths.snapshot()
    wave = cfg["wave"]
    roster = {int(r["netuid"]): r for r in read_table(paths.CHAIN / f"roster_wave{wave}.csv")}
    links = read_table(paths.EVIDENCE / f"links_wave{wave}.csv")
    book = ledger()
    x = XClient(paths.secret("X_BEARER_TOKEN"), ledger=book, cache_dir=str(paths.raw_dir("x")))

    todo = {}
    for link in links:
        n = int(link["netuid"])
        if (link["x_handle"] and link["x_source"] != "x_profile_match") or roster[n]["flag_placeholder_identity"] == "1":
            continue
        guesses = candidate_handles(link["subnet_name"], link["gh_owner"], link["website_url"])
        if guesses:
            todo[n] = (link, guesses)
    every = sorted({g for _, guesses in todo.values() for g in guesses})
    print(f"{len(todo)} subnets without a handle; {len(every)} guesses to look up", flush=True)
    found = {u["username"].lower(): u for u in x.users_by(every, fields=FIELDS)}
    print(f"{len(found)} of the guessed handles exist; X spend ${book.used('x_usd'):.2f}", flush=True)

    rows = []
    for n, (link, guesses) in sorted(todo.items()):
        accepted, basis = None, None
        for g in guesses:
            p = found.get(g.lower())
            why = profile_matches(p, n, link["subnet_name"], link["website_url"]) if p else None
            if why:
                accepted, basis = p["username"], why
                break
        rows.append({"netuid": n, "x_handle": accepted, "basis": basis, "guesses_tried": len(guesses),
                     "guesses_existing": sum(1 for g in guesses if g.lower() in found)})
        print(f"  SN{n} {link['subnet_name']}: {accepted or 'no verified account'}" + (f" ({basis})" if basis else ""),
              flush=True)
    write_table(paths.EVIDENCE / f"x_handle_guess_wave{wave}.csv", rows)
    print(f"verified handles for {sum(1 for r in rows if r['x_handle'])} of {len(rows)} subnets; "
          f"X spend ${book.used('x_usd'):.2f} of ${cfg['x_usd_ceiling']:.2f}")


if __name__ == "__main__":
    main()
