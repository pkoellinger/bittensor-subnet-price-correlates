"""Logic on event lists: owner trades, basket swaps, identity changes, windows.

Pure functions. Inputs are rows as returned by the Taostats API.
"""
import re
from collections import defaultdict
from urllib.parse import urlparse

RAO = 10 ** 9


# ------------------------------------------------------------------ normalisers

def norm_name(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def github_owner(url):
    """Owner (user or organisation) of a GitHub URL, lower case; '' if none.

    Handles https://github.com/<owner>/<repo>... and https://github.com/orgs/<org>/...
    """
    m = re.search(r"github\.com/(?:orgs/)?([A-Za-z0-9_.-]+)", url or "", flags=re.I)
    return m.group(1).lower() if m else ""


def site_host(url):
    url = (url or "").strip()
    if not url:
        return ""
    if "//" not in url:
        url = "https://" + url
    host = (urlparse(url).netloc or "").lower()
    return host[4:] if host.startswith("www.") else host


# ------------------------------------------------------------------ owner trades

def net_owner_trades(events):
    """Buys and sells of a wallet on one subnet from Taostats delegation events.

    DELEGATE = TAO in, alpha out of the pool (a buy); UNDELEGATE = a sell.
    Not trades, and therefore removed:
      * rows flagged is_transfer (stake sent to or received from another wallet);
      * moving stake between validators, which appears as an UNDELEGATE and a
        DELEGATE with identical alpha inside one extrinsic.
    Amounts are returned in TAO and alpha (not rao).
    """
    out = {"buy_tao": 0.0, "sell_tao": 0.0, "buy_alpha": 0.0, "sell_alpha": 0.0,
           "n_buys": 0, "n_sells": 0, "transfer_out_alpha": 0.0, "transfer_in_alpha": 0.0,
           "moves_netted": 0}
    groups = defaultdict(list)
    for e in events:
        action = (e.get("action") or "").upper()
        if e.get("is_transfer"):
            side = "transfer_out_alpha" if action == "UNDELEGATE" else "transfer_in_alpha"
            out[side] += int(e["alpha"]) / RAO
            continue
        groups[e.get("extrinsic_id")].append((action, int(e["alpha"]), int(e["amount"])))

    for legs in groups.values():
        sells = [leg for leg in legs if leg[0] == "UNDELEGATE"]
        buys = [leg for leg in legs if leg[0] == "DELEGATE"]
        for s in list(sells):
            match = next((b for b in buys if b[1] == s[1]), None)
            if match is not None:
                sells.remove(s)
                buys.remove(match)
                out["moves_netted"] += 1
        for _, alpha, tao in buys:
            out["buy_tao"] += tao / RAO
            out["buy_alpha"] += alpha / RAO
            out["n_buys"] += 1
        for _, alpha, tao in sells:
            out["sell_tao"] += tao / RAO
            out["sell_alpha"] += alpha / RAO
            out["n_sells"] += 1
    out["net_buy_tao"] = out["buy_tao"] - out["sell_tao"]
    return out


# ------------------------------------------------------------------ basket swaps

def basket_flows(events):
    """Net TAO value that validator baskets moved into each subnet.

    A BasketSwapped event sells a basket's holding of `originNetuid` and buys
    `destinationNetuid`; `taoMid` is the TAO value of the swap. The destination
    gains it, the origin loses it, so flows sum to zero over all netuids
    (netuid 0 = root, which is TAO itself). Passive dividend accrual and root
    claims are not in these events.
    """
    net = defaultdict(float)
    buy = defaultdict(float)
    sell = defaultdict(float)
    swaps = defaultdict(int)
    by_basket = defaultdict(lambda: defaultdict(float))
    for e in events:
        a = e["args"]
        tao = int(a["taoMid"]) / RAO
        origin, dest, basket = int(a["originNetuid"]), int(a["destinationNetuid"]), a["hotkey"]
        net[dest] += tao
        net[origin] -= tao
        buy[dest] += tao
        sell[origin] += tao
        swaps[dest] += 1
        swaps[origin] += 1
        by_basket[dest][basket] += tao
        by_basket[origin][basket] -= tao
    return {
        n: {
            "net_tao": net[n], "buy_tao": buy[n], "sell_tao": sell[n], "n_swaps": swaps[n],
            "net_buyers": sum(1 for v in by_basket[n].values() if v > 1e-12),
            "net_sellers": sum(1 for v in by_basket[n].values() if v < -1e-12),
        }
        for n in net
    }


# ------------------------------------------------------------------ identity changes

_FIELDS = (
    ("name", "subnet_name", norm_name),
    ("github_owner", "github_repo", github_owner),
    ("site_host", "subnet_url", site_host),
)


def last_real_identity_change(rows, registered_block):
    """Most recent identity change that signals a different project, or None.

    rows: identity-set events of one netuid (block_number, subnet_name,
    github_repo, subnet_url). Only events at or after the current registration
    count; earlier ones belong to a previous occupant of the netuid.

    A change is real when the normalised name, the GitHub owner, or the website
    host differs from the previous event. Not counted: the first identity after
    registration, a blank field being filled or emptied, and edits that leave
    all three unchanged (logo, description, contact, repo within the same owner).
    """
    seq = sorted((r for r in rows if int(r["block_number"]) >= registered_block),
                 key=lambda r: int(r["block_number"]))
    latest = None
    for prev, cur in zip(seq, seq[1:]):
        for what, field, norm in _FIELDS:
            before, after = norm(prev.get(field)), norm(cur.get(field))
            if before and after and before != after:
                latest = {"block": int(cur["block_number"]), "what": what, "before": before, "after": after}
                break
    return latest


# ------------------------------------------------------------------ windows

def observed_window(blocks, registered_block):
    """Sample blocks at which the current subnet existed (registered at or before the block)."""
    return [b for b in blocks if b >= registered_block]
