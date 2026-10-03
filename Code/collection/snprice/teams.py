"""Which subnets are run by the same team (E3).

Two subnets belong to one team when they share the GitHub owner, the website domain, a
contact e-mail domain or the X account. Links chain: if A and B share one of these and B
and C another, all three are one team. The team is named after its lowest netuid.

The team id lets an analysis keep subnets of one team together, for example in the same
cross-validation fold, because their prices are not independent observations.
"""
from .webtext import SHARED_HOSTS, site_of

NOT_A_TEAM = {"deprecated", "unknown", "none", "null", "parked"}       # placeholder values on chain


def _keys(row):
    gh = (row.get("gh_owner") or "").strip().lower()
    if gh and gh not in NOT_A_TEAM:
        yield "github:" + gh
    url = (row.get("website_url") or "").strip()
    if url:
        site = site_of(url if "//" in url else "https://" + url)
        if site and not any(site == h or site.endswith("." + h) for h in SHARED_HOSTS):
            yield "site:" + site
    contact = (row.get("contact_domain") or "").strip().lower()
    if contact:
        yield "contact:" + contact
    handle = (row.get("x_handle") or "").strip().lstrip("@").lower()
    if handle:
        yield "x:" + handle


def team_ids(rows):
    """{netuid: {"team_id": "T001", "team_n_subnets": 3}} from the links table."""
    parent = {int(r["netuid"]): int(r["netuid"]) for r in rows}

    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    first = {}
    for r in rows:
        n = int(r["netuid"])
        for key in _keys(r):
            if key in first:
                a, b = find(first[key]), find(n)
                parent[max(a, b)] = min(a, b)
            else:
                first[key] = n
    size = {}
    for n in parent:
        size[find(n)] = size.get(find(n), 0) + 1
    return {n: {"team_id": f"T{find(n):03d}", "team_n_subnets": size[find(n)]} for n in parent}
