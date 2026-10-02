"""Logic on event lists: owner trades, basket swaps, identity changes, windows.

Pure functions. Inputs are rows as returned by the Taostats API.
"""
import re
from collections import defaultdict
from urllib.parse import urlparse

from .webtext import site_of

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


_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})")
GENERIC_MAIL_DOMAINS = {"gmail.com", "googlemail.com", "proton.me", "protonmail.com", "pm.me", "outlook.com",
                        "hotmail.com", "yahoo.com", "icloud.com", "tutanota.com", "bittensor.com"}


def contact_without_mailbox(text):
    """A contact field with e-mail addresses reduced to '@domain' (mailbox names are not republished)."""
    return _EMAIL.sub(lambda m: "@" + m.group(1).lower(), (text or "").strip())


def contact_domain(text):
    """Organisation e-mail domain of a contact field; '' for none or for generic mailbox providers."""
    m = _EMAIL.search(text or "")
    if not m:
        return ""
    domain = m.group(1).lower()
    return "" if domain in GENERIC_MAIL_DOMAINS else domain


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

def _same_name(a, b):
    """Equal, or one name extends the other at its start or end ("gm" and "saygm")."""
    return a == b or a.startswith(b) or a.endswith(b) or b.startswith(a) or b.endswith(a)


def _same_site(a, b):
    return site_of(a) == site_of(b)


_FIELDS = (
    ("name", "subnet_name", norm_name, _same_name),
    ("github_owner", "github_repo", github_owner, lambda a, b: a == b),
    ("site_host", "subnet_url", site_host, _same_site),
)


def _events(rows, registered_block):
    return sorted((r for r in rows if int(r["block_number"]) >= registered_block),
                  key=lambda r: int(r["block_number"]))


def last_real_identity_change(rows, registered_block):
    """Most recent change of the name, the GitHub owner or the website, or None.

    rows: identity-set events of one netuid (block_number, subnet_name,
    github_repo, subnet_url). Only events at or after the current registration
    count; earlier ones belong to a previous occupant of the netuid.

    Each field is compared with its last non-blank value. Not counted: the first
    identity after registration, a field being filled or emptied, a name that only
    extends the old one ("gm" to "SayGM"), a site moving within its own domain, and
    edits that leave all three unchanged (logo, description, contact, another
    repository of the same owner).
    """
    latest, last = None, {}
    for event in _events(rows, registered_block):
        changed = None
        for what, field, norm, same in _FIELDS:
            value = norm(event.get(field))
            if not value:
                continue
            if what in last and not same(last[what], value) and changed is None:
                changed = {"block": int(event["block_number"]), "what": what, "before": last[what], "after": value}
            last[what] = value
        latest = changed or latest
    return latest


def project_start(rows, registered_block):
    """Block at which the current project took over the netuid, or None if it has run it
    since registration.

    A project starts when the subnet gets a new name and the team behind it is another one:
    the GitHub owner before the rename differs from the GitHub owner now (or one of the two
    is unknown). A rename with the same GitHub owner is a rebrand by the same team, a
    repository or website move alone is housekeeping, and a name that only extends the old
    one is no rename at all. Identity-set events carry the whole identity each time.
    """
    events = _events(rows, registered_block)
    if not events:
        return None
    owner_now = github_owner(events[-1].get("github_repo"))
    renames, name, owner_before = [], None, ""
    for event in events:
        value = norm_name(event.get("subnet_name"))
        if value:
            if name is not None and not _same_name(name, value):
                renames.append((int(event["block_number"]), owner_before))
            name = value
        owner_before = github_owner(event.get("github_repo"))
    for block, owner in reversed(renames):
        if not owner or not owner_now or owner != owner_now:
            return block
    return None


# ------------------------------------------------------------------ windows

def observed_window(blocks, registered_block):
    """Sample blocks at which the current subnet existed (registered at or before the block)."""
    return [b for b in blocks if b >= registered_block]
