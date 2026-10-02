"""Independent Bittensor commentators on X: screening of accounts (config/kol_rule.md), subnets
named in their posts, and the polarity of those mentions (config/polarity_criteria.md)."""
import re

from .textmatch import valid_for_project
from .timeutil import epoch, iso

_LINK = re.compile(r"https?://\S+")

MIN_FOCUS = 0.5
MIN_POSTS = 30
MIN_FOLLOWERS = 2000


def screen(username, profile, original, bittensor, subnet_handles):
    """Apply the screening rule to one candidate.

    profile         the account's profile from the X API, or None if the handle does not exist
    original        its original posts in the 90 days before T (reposts and replies excluded)
    bittensor       how many of those contain a Bittensor term
    subnet_handles  lower-case handles of the subnets' own accounts

    The rule in force asks for volume: at least 30 posts with a Bittensor term (`passes`).
    The rule as first written asked for focus, at least half of the posts, and 30 posts of
    any kind; its result is kept as `passes_first_rule` so that both lists can be compared.
    Whether the account is a commentator at all (a person, not an institution or a show) is
    decided by hand in config/kol_accounts.csv.
    """
    exists = int(profile is not None)
    share = (bittensor / original) if exists and original else None
    out = {
        "exists": exists,
        "independent": int(username.lstrip("@").lower() not in subnet_handles),
        "focus": int(share is not None and share >= MIN_FOCUS),
        "activity": int(bool(exists and original is not None and original >= MIN_POSTS)),
        "reach": int(bool(exists and profile["public_metrics"]["followers_count"] >= MIN_FOLLOWERS)),
        "volume": int(bool(exists and bittensor is not None and bittensor >= MIN_POSTS)),
        "bittensor_share": share,
    }
    out["passes_first_rule"] = int(all(out[k] for k in ("exists", "independent", "focus", "activity", "reach")))
    out["passes"] = int(all(out[k] for k in ("exists", "independent", "volume", "reach")))
    return out


POLARITIES = ("positive", "negative", "neutral")
LABELS = POLARITIES + ("not_about",)       # what a coder may answer for a post and a subnet
DAY = 86400


def post_text(post):
    """Full text of a post; long posts carry it in `note_tweet`."""
    return (post.get("note_tweet") or {}).get("text") or post.get("text") or ""


def post_mentions(post, username, matcher, project_start):
    """Subnets named in one post, as rows without the post's text.

    matcher        snprice.textmatch.Matcher over the subnets of the wave
    project_start  {netuid: UTC time at which the current project took over the netuid, or None}

    A subnet named by number alone before its project started does not count: the number
    then meant the previous occupant.
    """
    created = iso(epoch(post["created_at"]))
    rows = []
    text = _LINK.sub(" ", post_text(post))      # shortened links are random strings ("t.co/Sn3Zj...")
    for netuid, hit in sorted(matcher.find(text).items()):
        if not valid_for_project(hit, created, project_start.get(netuid)):
            continue
        rows.append({"post_id": post["id"], "username": username, "created": created, "netuid": netuid,
                     "strength": hit["strength"], "rules": "|".join(hit["rules"])})
    return rows


def merge_posts(earlier, new, start, end):
    """Posts of one account inside [start, end] (seconds since 1970), each once, oldest first.

    earlier  posts read for the wave before (its window overlaps the present one)
    new      posts read now for the days after that wave's snapshot
    """
    by_id = {}
    for post in list(earlier) + list(new):
        if start <= epoch(post["created_at"]) <= end:
            by_id[post["id"]] = post
    return sorted(by_id.values(), key=lambda p: (epoch(p["created_at"]), p["id"]))


def carry_labels(earlier_labels, earlier_uids, current_uids):
    """Labels of an earlier wave that still apply: {(post_id, netuid): label}.

    earlier_labels  [{"post_id", "netuid", "label"}] of the earlier wave
    earlier_uids, current_uids  {netuid: subnet_uid} in the two waves

    A label says how a post speaks about the subnet that held the netuid then. It is carried
    over only if the same subnet (same registration) holds the netuid now.
    """
    return {(str(r["post_id"]), int(r["netuid"])): r["label"] for r in earlier_labels
            if earlier_uids.get(int(r["netuid"])) is not None
            and earlier_uids.get(int(r["netuid"])) == current_uids.get(int(r["netuid"]))}


def mention_decision(strength, label_a, label_b):
    """(counts, polarity) of one post for one subnet after two independent codings.

    strength  how the subnet was matched in the text (snprice.textmatch): "strong" (number,
              handle or distinctive name) or "weak" (an ordinary word used as a name)
    labels    each coder's answer: positive, negative, neutral, or not_about (the matched
              word does not refer to the subnet)

    A strong match is dropped only if both coders say the post is not about the subnet; a weak
    match is dropped if either says so. A direction counts only if both coders chose it.
    """
    if strength not in ("strong", "weak"):
        raise ValueError(f"unknown match strength {strength!r}")
    for label in (label_a, label_b):
        if label not in LABELS:
            raise ValueError(f"unknown label {label!r}")
    doubts = [label_a, label_b].count("not_about")
    if doubts == 2 or (doubts and strength == "weak"):
        return False, None
    if doubts:
        return True, "neutral"
    return True, agreed_polarity(label_a, label_b)


def agreed_polarity(a, b):
    """Polarity of a mention after two independent codings: a direction counts only if both
    coders chose it; everything else is neutral."""
    for label in (a, b):
        if label not in POLARITIES:
            raise ValueError(f"unknown polarity {label!r}")
    return a if a == b and a != "neutral" else "neutral"


def mention_counts(mentions, t_end, window_days=90, month_days=30):
    """Per-subnet counts of posts by the approved accounts.

    mentions: dicts with post_id, username, created (seconds since 1970), netuid, polarity.
    A post that names two subnets counts for each of them; a (post, subnet) pair counts once.
    Returns {netuid: {"kol_posts_90d": ..., ...}} for subnets with at least one post in the window.
    """
    seen, out = set(), {}
    for m in mentions:
        key = (m["post_id"], m["netuid"])
        age = t_end - m["created"]
        if key in seen or age < 0 or age >= window_days * DAY:
            continue
        seen.add(key)
        row = out.setdefault(m["netuid"], {
            f"kol_posts_{window_days}d": 0, f"kol_accounts_{window_days}d": set(),
            f"kol_pos_posts_{window_days}d": 0, f"kol_neg_posts_{window_days}d": 0,
            f"kol_posts_{month_days}d": 0, f"kol_posts_lag{month_days}": 0,
            f"kol_pos_posts_{month_days}d": 0, f"kol_pos_posts_lag{month_days}": 0,
            f"kol_neg_posts_{month_days}d": 0, f"kol_neg_posts_lag{month_days}": 0})
        tag = {"positive": "pos_", "negative": "neg_"}.get(m["polarity"])
        row[f"kol_posts_{window_days}d"] += 1
        row[f"kol_accounts_{window_days}d"].add(m["username"].lower())
        if tag:
            row[f"kol_{tag}posts_{window_days}d"] += 1
        month = f"{month_days}d" if age < month_days * DAY else f"lag{month_days}" if age < 2 * month_days * DAY else None
        if month:
            row[f"kol_posts_{month}"] += 1
            if tag:
                row[f"kol_{tag}posts_{month}"] += 1
    for row in out.values():
        row[f"kol_accounts_{window_days}d"] = len(row[f"kol_accounts_{window_days}d"])
    return out
