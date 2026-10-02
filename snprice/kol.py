"""Screening of X accounts for the list of independent Bittensor commentators (config/kol_rule.md)."""

MIN_FOCUS = 0.5
MIN_POSTS = 30
MIN_FOLLOWERS = 2000


def screen(username, profile, original, bittensor, subnet_handles):
    """Apply the screening rule to one candidate.

    profile         the account's profile from the X API, or None if the handle does not exist
    original        its original posts in the 90 days before T (reposts and replies excluded)
    bittensor       how many of those contain a Bittensor term
    subnet_handles  lower-case handles of the subnets' own accounts
    """
    exists = int(profile is not None)
    share = (bittensor / original) if exists and original else None
    out = {
        "exists": exists,
        "independent": int(username.lstrip("@").lower() not in subnet_handles),
        "focus": int(share is not None and share >= MIN_FOCUS),
        "activity": int(bool(exists and original is not None and original >= MIN_POSTS)),
        "reach": int(bool(exists and profile["public_metrics"]["followers_count"] >= MIN_FOLLOWERS)),
        "bittensor_share": share,
    }
    out["passes"] = int(all(out[k] for k in ("exists", "independent", "focus", "activity", "reach")))
    return out


POLARITIES = ("positive", "negative", "neutral")
DAY = 86400


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
