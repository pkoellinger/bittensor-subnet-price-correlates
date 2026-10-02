"""Posts by independent Bittensor commentators that mention a subnet (Y19, Y20).

Step 1  python collect/14_kol.py candidates
        Screens the accounts in config/kol_candidates.csv by the rule in config/kol_rule.md,
        using profile and count requests only. No post is read. Writes the screening table
        and prints what reading the posts would cost for 30, 61 and 90 days.

Step 2  The project owner approves accounts in config/kol_accounts.csv.

Step 3  python collect/14_kol.py posts          (written after the approval; see PLAN.md)

Writes (step 1)  data/evidence/kol_candidates_wave<N>.csv
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.io import archive, ledger, read_table, write_table  # noqa: E402
from snprice.kol import screen  # noqa: E402
from snprice.timeutil import epoch, iso  # noqa: E402
from snprice.xapi import COST_POST, XClient  # noqa: E402

DAY = 86400
TERMS = "(bittensor OR tao OR dtao OR subnet OR subnets OR opentensor)"
WINDOWS = (30, 61, 90)


def candidates():
    cfg = paths.snapshot()
    wave = cfg["wave"]
    listed = read_table(paths.CONFIG / "kol_candidates.csv")
    subnet_handles = {(l["x_handle"] or "").lower() for l in read_table(paths.EVIDENCE / f"links_wave{wave}.csv")} - {""}
    book = ledger()
    x = XClient(paths.secret("X_BEARER_TOKEN"), ledger=book, cache_dir=str(paths.raw_dir("x")))
    t_end = int(archive().timestamp(cfg["t_block"]))
    start = t_end - cfg["long_window_days"] * DAY

    profiles = {u["username"].lower(): u for u in x.users_by([c["username"] for c in listed])}
    rows = []
    for c in listed:
        name = c["username"]
        p = profiles.get(name.lower())
        daily = {"original": {}, "bittensor": {}}
        if p:
            base = f"from:{p['username']} -is:retweet -is:reply"
            for label, query in (("original", base), ("bittensor", f"{base} {TERMS}")):
                for d in x.counts_all(query, iso(start), iso(t_end), granularity="day"):
                    daily[label][epoch(d["start"])] = d["tweet_count"]

        def total(label, days):
            return sum(v for t, v in daily[label].items() if t >= t_end - days * DAY) if p else None

        result = screen(name, p, total("original", 90), total("bittensor", 90), subnet_handles)
        rows.append({
            "username": p["username"] if p else name,
            "source": c["source"],
            "x_user_id": p["id"] if p else None,
            "followers": p["public_metrics"]["followers_count"] if p else None,
            "account_created": p["created_at"][:10] if p else None,
            **{f"posts_original_{d}d": total("original", d) for d in WINDOWS},
            **{f"posts_bittensor_{d}d": total("bittensor", d) for d in WINDOWS},
            "bittensor_share_90d": result["bittensor_share"],
            **{f"rule_{k}": result[k] for k in ("exists", "independent", "focus", "activity", "reach")},
            "passes_rule": result["passes"],
        })
        print(f"  {name}: {'found' if p else 'not found'}; X spend ${book.used('x_usd'):.2f}", flush=True)

    write_table(paths.EVIDENCE / f"kol_candidates_wave{wave}.csv", rows)
    passing = [r for r in rows if r["passes_rule"]]
    print(f"\n{len(passing)} of {len(rows)} candidates pass the rule: {[r['username'] for r in passing]}")
    for d in WINDOWS:
        posts = sum(r[f"posts_original_{d}d"] for r in passing)
        tagged = sum(r[f"posts_bittensor_{d}d"] for r in passing)
        print(f"  {d} days: {posts} original posts (${posts * COST_POST:.2f} to read all); "
              f"{tagged} with a Bittensor term (${tagged * COST_POST:.2f})")
    print(f"X spend so far ${book.used('x_usd'):.2f} of ${cfg['x_usd_ceiling']:.2f}")


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    if step == "candidates":
        candidates()
    else:
        raise SystemExit(__doc__)
