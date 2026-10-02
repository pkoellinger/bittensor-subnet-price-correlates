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
