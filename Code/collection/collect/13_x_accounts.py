"""The subnet's own X account: followers, account age, posts in the window (Y10, F1).

Source: X API v2 (pay-per-use). Profiles cost $0.01 each. Post counts use the archive
count endpoint ($0.01 per request) with the queries
    from:<handle> -is:retweet               all posts, reposts excluded
    from:<handle> -is:retweet -is:reply     original posts
No post is read. Followers and account age are as of collection time; counts are
pinned to the window by date.

Writes  Temp/collection-cache/intermediate/x_accounts_wave<N>.csv   one row per subnet
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.io import archive, ledger, read_table, write_table  # noqa: E402
from snprice.timeutil import epoch, iso  # noqa: E402
from snprice.windows import bounds  # noqa: E402
from snprice.xapi import XClient, XError  # noqa: E402


def main():
    cfg = paths.snapshot()
    wave = cfg["wave"]
    links = read_table(paths.EVIDENCE / f"links_wave{wave}.csv")
    arch = archive()
    book = ledger()
    x = XClient(paths.secret("X_BEARER_TOKEN"), ledger=book, cache_dir=str(paths.raw_dir("x")))

    w_lo, w_hi = (arch.timestamp(b) for b in bounds(cfg, "window"))
    l_lo, l_hi = (arch.timestamp(b) for b in bounds(cfg, "lag"))

    handles = sorted({l["x_handle"] for l in links if l["x_handle"]}, key=str.lower)
    profiles = {u["username"].lower(): u for u in x.users_by(handles)}
    print(f"{len(handles)} handles looked up, {len(profiles)} exist; X spend so far ${book.used('x_usd'):.2f}", flush=True)

    counts_ok = True
    counts = {}
    for i, h in enumerate(handles, 1):
        if h.lower() not in profiles or not counts_ok:
            continue
        try:
            per = {}
            for label, query in (("all", f"from:{h} -is:retweet"), ("original", f"from:{h} -is:retweet -is:reply")):
                days = x.counts_all(query, iso(l_lo), iso(w_hi), granularity="day")
                per[label] = {
                    "30d": sum(d["tweet_count"] for d in days if w_lo <= epoch(d["start"]) < w_hi),
                    "lag30": sum(d["tweet_count"] for d in days if l_lo <= epoch(d["start"]) < l_hi),
                }
            counts[h.lower()] = per
        except XError as exc:
            if not counts:
                counts_ok = False
                print(f"archive counts are not available on this account: {exc}", flush=True)
            else:
                raise
        if i % 20 == 0:
            print(f"  {i}/{len(handles)} handles counted; X spend ${book.used('x_usd'):.2f}", flush=True)

    rows = []
    for l in links:
        h = (l["x_handle"] or "").lower()
        p, c = profiles.get(h), counts.get(h)
        rows.append({
            "netuid": int(l["netuid"]),
            "x_handle": l["x_handle"],
            "x_status": ("found" if p else "dead") if h else "not_listed",
            "x_user_id": p["id"] if p else None,
            "x_followers": p["public_metrics"]["followers_count"] if p else None,
            "x_account_age_days": ((w_hi - epoch(p["created_at"])) / 86400.0) if p else None,
            "x_posts_lifetime": p["public_metrics"]["tweet_count"] if p else None,
            "x_posts_30d": c["all"]["30d"] if c else None,
            "x_posts_original_30d": c["original"]["30d"] if c else None,
            "x_posts_lag30": c["all"]["lag30"] if c else None,
            "x_posts_original_lag30": c["original"]["lag30"] if c else None,
        })
    write_table(paths.INTERMEDIATE / f"x_accounts_wave{wave}.csv", rows)
    print(f"wrote X account data: {sum(1 for r in rows if r['x_status'] == 'found')} accounts found, "
          f"{sum(1 for r in rows if r['x_posts_30d'] is not None)} with post counts; "
          f"X spend ${book.used('x_usd'):.2f} of ${cfg['x_usd_ceiling']:.2f}")


if __name__ == "__main__":
    main()
