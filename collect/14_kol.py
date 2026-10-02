"""Posts by independent Bittensor commentators that mention a subnet (Y19, Y20).

Step 1  python collect/14_kol.py candidates
        Screens the accounts in config/kol_candidates.csv by the rule in config/kol_rule.md,
        using profile and count requests only. No post is read. Writes the screening table
        and prints what reading the posts would cost for 30, 61 and 90 days.

Step 2  The project owner approves accounts in config/kol_accounts.csv
        (approved = yes and the date in approved_on).

Step 3  python collect/14_kol.py posts
        Reads the original posts (no reposts, no replies) of the approved accounts in the
        90 days before T and finds the subnets they name (snprice/textmatch.py, the rules
        used for podcast titles). The X client refuses any account that is not approved, and
        the step refuses to start if the posts counted at screening would cost more than
        the budget has left. The number of posts read is checked against that count.

Step 4  Two coders label every post-subnet pair (config/polarity_criteria.md), then
        python build/kol_polarity.py

Writes (step 1)  data/evidence/kol_candidates_wave<N>.csv
       (step 3)  data/evidence/kol_mentions_wave<N>.csv   post id, account, time, subnet, how matched
                 data/evidence/kol_accounts_wave<N>.csv   posts read and posts naming a subnet, per account
                 data/raw/wave<N>/kol/coding_input.json   the same with the text, for the coders (not committed:
                                                          post text is not republished)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.io import archive, ledger, read_json, read_table, write_json, write_table  # noqa: E402
from snprice.kol import merge_posts, post_mentions, post_text, screen  # noqa: E402
from snprice.textmatch import Matcher, subnet_entries  # noqa: E402
from snprice.timeutil import epoch, iso  # noqa: E402
from snprice.xapi import COST_POST, XClient, XError, load_approved  # noqa: E402

DAY = 86400
COUNT_TOLERANCE = 0.03          # posts read may differ from posts counted by 3% (deleted posts, day edges)
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
            **{f"rule_{k}": result[k] for k in ("exists", "independent", "reach", "volume")},
            "passes_rule": result["passes"],
            # the rule as first written (focus instead of volume), kept for comparison
            "rule_focus": result["focus"],
            "rule_activity": result["activity"],
            "passes_first_rule": result["passes_first_rule"],
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


def posts():
    cfg = paths.snapshot()
    wave = cfg["wave"]
    approved = load_approved(str(paths.CONFIG / "kol_accounts.csv"))
    if not approved:
        raise SystemExit("no account in config/kol_accounts.csv is approved (approved = yes with a date in "
                         "approved_on); no post is read")
    screened = {r["username"].lower(): r for r in read_table(paths.EVIDENCE / f"kol_candidates_wave{wave}.csv")}
    unknown = sorted(a for a in approved if a not in screened or not screened[a]["x_user_id"])
    if unknown:
        raise SystemExit(f"approved but not screened by `14_kol.py candidates`: {unknown}")

    days = cfg["long_window_days"]
    arch = archive()
    t_end = int(arch.timestamp(cfg["t_block"]))
    start = t_end - days * DAY
    counted = {a: int(screened[a][f"posts_original_{days}d"]) for a in approved}

    # A follow-up wave reads only the days since the wave before it and reuses the posts read then.
    before = paths.snapshot_before(cfg)
    earlier_end = int(arch.timestamp(before["t_block"])) if before else None
    earlier, to_read = {}, {}
    for a in approved:
        old = read_json(paths.raw_dir("kol", wave=before["wave"]) / "posts" / f"{a}.json") if before else None
        if old is not None and earlier_end > start:
            earlier[a], to_read[a] = old, int(screened[a][f"posts_original_{cfg['window_days']}d"])
        else:
            earlier[a], to_read[a] = None, counted[a]
    book = ledger()
    room = cfg["x_usd_ceiling"] - book.used("x_usd")
    cost = sum(to_read.values()) * COST_POST
    print(f"{len(approved)} approved accounts with {sum(counted.values())} original posts counted in the {days} days "
          f"before T; {sum(to_read.values())} of them still to read: about ${cost:.2f}; ${room:.2f} of the wave's X "
          f"budget is left", flush=True)
    if cost > room:
        raise SystemExit("that is more than the budget has left; nothing was read")
    saved = paths.raw_dir("kol") / "posts"
    saved.mkdir(exist_ok=True)

    roster = read_table(paths.CHAIN / f"roster_wave{wave}.csv")
    entries = subnet_entries(roster, read_table(paths.EVIDENCE / f"links_wave{wave}.csv"),
                             read_table(paths.CONFIG / "name_aliases.csv"))
    matcher = Matcher(entries)
    label = {e["netuid"]: " / ".join([e["name"] or "(no name)"] + e["aliases"]) for e in entries}
    project_start = {int(h["netuid"]): h["project_start_utc"]
                     for h in read_table(paths.INTERMEDIATE / f"history_wave{wave}.csv")}

    x = XClient(paths.secret("X_BEARER_TOKEN"), ledger=book, cache_dir=str(paths.raw_dir("x")), approved=approved)
    mentions, coding, accounts, stopped = [], [], [], None
    for a in sorted(approved):
        name = screened[a]["username"]
        read_from = start if earlier[a] is None else earlier_end + 1
        try:
            new = x.original_posts(name, iso(read_from), iso(t_end + 1))
        except XError as exc:           # for example HTTP 402: the prepaid credits of the X account are used up
            stopped = (name, str(exc))
            break
        got = merge_posts(earlier[a] or [], new, start, t_end)
        if abs(len(got) - counted[a]) > max(3, COUNT_TOLERANCE * counted[a]):
            raise SystemExit(f"@{name}: {len(got)} posts read, {counted[a]} counted at screening; the window is not "
                             f"complete, nothing was written")
        write_json(saved / f"{a}.json", got)        # with text: stays in data/raw, the next wave reuses it
        naming = 0
        for post in got:
            rows = post_mentions(post, name, matcher, project_start)
            if not rows:
                continue
            naming += 1
            mentions.extend(rows)
            coding.append({"post_id": post["id"], "username": name, "created": rows[0]["created"],
                           "text": post_text(post),
                           "subnets": [{"netuid": r["netuid"], "name": label[r["netuid"]], "match": r["strength"]}
                                       for r in rows]})
        accounts.append({"username": name, "posts_counted": counted[a], "posts_read": len(got),
                         "posts_naming_a_subnet": naming})
        print(f"  @{name}: {len(got)} posts read, {naming} name a subnet; X spend ${book.used('x_usd'):.2f}", flush=True)

    # the coders' input is written for the accounts read so far: labels are per post and stay valid
    write_json(paths.raw_dir("kol") / "coding_input.json", coding)
    if stopped:
        done = {r["username"].lower() for r in accounts}
        left = sorted(a for a in approved if a not in done)
        print(f"STOPPED at @{stopped[0]}: {stopped[1]}")
        print(f"read completely: {len(accounts)} of {len(approved)} accounts; still to read: {left}, about "
              f"{sum(counted[a] for a in left)} posts (${sum(counted[a] for a in left) * COST_POST:.2f} less what is "
              f"already cached). Nothing is lost: run the step again and it continues from the cache.")
        print("The tables of mentions are written only when every approved account has been read.")
        sys.exit(2)

    write_table(paths.EVIDENCE / f"kol_mentions_wave{wave}.csv", mentions,
                columns=["post_id", "username", "created", "netuid", "strength", "rules"])
    write_table(paths.EVIDENCE / f"kol_accounts_wave{wave}.csv", accounts)
    weak = sum(1 for m in mentions if m["strength"] == "weak")
    print(f"{len(mentions)} post-subnet pairs in {len(coding)} posts ({weak} weak matches for the coders to confirm); "
          f"{len({m['netuid'] for m in mentions})} subnets named; X spend ${book.used('x_usd'):.2f} "
          f"of ${cfg['x_usd_ceiling']:.2f}")
    print("next: two coders label data/raw/.../kol/coding_input.json (config/polarity_criteria.md), "
          "then python build/kol_polarity.py")


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    if step == "candidates":
        candidates()
    elif step == "posts":
        posts()
    else:
        raise SystemExit(__doc__)
