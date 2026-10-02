"""Group miner wallets into operators by where their start-up TAO came from.

Method of the team note "Miner concentration across the top 16 subnets and SN111,
HHI by funding lineage" (18 Sep 2026), lower-bound and best-estimate lenses only:

  * A funding link is TAO received BEFORE the wallet registered, of at least the
    threshold amount (20% of the registration cost, minimum 0.01 TAO), among the
    50 largest such transfers.
  * Two wallets that share a funder are one operator, unless the funder is
    exchange-like (more than 1,500 lifetime transfers). An address that links
    two or more wallets but was not profiled never links.
  * Funders of funders are followed one level, and only through funders with at
    most 100 inbound transfers.
  * Best estimate = lower bound, plus wallets on the same miner IP, plus wallets
    paid out of the same exchange wallet within 50 blocks with amounts within 10%.

Wider lenses (exchange funders as links, shared withdrawal destinations) are
deliberately left out: they merge strangers.
"""
from collections import Counter, defaultdict

from .metrics import hhi_from_amounts

EXCHANGE_MIN_TX = 1500
LEVEL2_MAX_INBOUND = 100
LEVEL2_ROWS = 3
MAX_FUNDERS = 50
BATCH_BLOCKS = 50
BATCH_TOL = 0.10
MODES = ("lower", "best")


def material_funders(transfers, coldkey, reg_block, threshold):
    """Level-1 funders of a wallet: material inbound transfers before registration.

    transfers: dicts with from, to, amount (TAO), block. Returns rows
    {frm, amt, blk}, largest first, at most 50.
    """
    rows = [
        {"frm": t["from"], "amt": float(t["amount"]), "blk": int(t["block"])}
        for t in transfers
        if t["to"] == coldkey and t["from"] != coldkey
        and int(t["block"]) < reg_block and float(t["amount"]) >= threshold
    ]
    rows.sort(key=lambda r: -r["amt"])
    return rows[:MAX_FUNDERS]


def is_exchange(profiles, address):
    p = profiles.get(address)
    return bool(p) and (p.get("total") or 0) > EXCHANGE_MIN_TX


class Partition:
    """Union-find over wallets and funder addresses."""

    def __init__(self, sample):
        self.sample = list(sample)
        self._p = {}
        self.stats = Counter()
        for c in self.sample:
            self.root(c)

    def has(self, x):
        return x in self._p

    def root(self, x):
        self._p.setdefault(x, x)
        while self._p[x] != x:
            self._p[x] = self._p[self._p[x]]
            x = self._p[x]
        return x

    def union(self, a, b):
        self._p[self.root(a)] = self.root(b)

    def n_clusters(self):
        return len({self.root(c) for c in self.sample})

    def sizes(self):
        return Counter(self.root(c) for c in self.sample)


def cluster(sample, funding, level2, profiles, ips=None, mode="lower"):
    """Partition the traced wallets into operators.

    sample    traced wallets (coldkeys)
    funding   {wallet: [{frm, amt, blk}, ...]}  level-1 funders (see material_funders)
    level2    {funder: {"total": inbound transfer count, "rows": [{frm, amt, blk}, ...]}}
    profiles  {address: {"total": lifetime transfers}} for addresses that link wallets
    ips       {wallet: set of miner IPs}  (best lens only)
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    sample = list(sample)
    in_sample = set(sample)
    ips = ips or {}

    def l1(c):
        return [r for r in funding.get(c, []) if r["frm"] != c]

    def l2(f):
        t = level2.get(f)
        if not t or (t.get("total") or 0) > LEVEL2_MAX_INBOUND:
            return []
        return [g for g in t["rows"][:LEVEL2_ROWS] if g["frm"] != f]

    # which traced wallets does each address fund, directly or one level up
    occ = defaultdict(set)
    for c in sample:
        for r in l1(c):
            occ[r["frm"]].add(c)
            for g in l2(r["frm"]):
                occ[g["frm"]].add(c)

    part = Partition(sample)

    def usable(a):
        if a in in_sample or len(occ[a]) < 2:
            return True          # links nothing by itself
        if a not in profiles:
            part.stats["unprofiled_links"] += 1
            return False
        if is_exchange(profiles, a):
            part.stats["exchange_links"] += 1
            return False
        return True

    for c in sample:
        for r in l1(c):
            f = r["frm"]
            if not usable(f):
                continue
            part.union(c, f)
            if f not in in_sample:
                for g in l2(f):
                    if usable(g["frm"]):
                        part.union(f, g["frm"])

    if mode == "best":
        by_ip = defaultdict(set)
        for c in sample:
            for ip in ips.get(c, ()):
                if ip and ip != "0.0.0.0":
                    by_ip[ip].add(c)
        for group in by_ip.values():
            group = sorted(group)
            for other in group[1:]:
                if part.root(group[0]) != part.root(other):
                    part.stats["ip_merges"] += 1
                part.union(group[0], other)

        by_exchange = defaultdict(list)
        for c in sample:
            for r in l1(c):
                if len(occ[r["frm"]]) >= 2 and is_exchange(profiles, r["frm"]):
                    by_exchange[r["frm"]].append((r["blk"], r["amt"], c))
        for payouts in by_exchange.values():
            payouts.sort()
            for i in range(len(payouts)):
                for j in range(i + 1, len(payouts)):
                    if payouts[j][0] - payouts[i][0] > BATCH_BLOCKS:
                        break
                    a, b = payouts[i], payouts[j]
                    if a[2] != b[2] and min(a[1], b[1]) / max(a[1], b[1]) >= 1 - BATCH_TOL:
                        if part.root(a[2]) != part.root(b[2]):
                            part.stats["batch_merges"] += 1
                        part.union(a[2], b[2])
    return part


def lineage_summary(shares, sample, funding, level2, profiles, ips, owner_addresses, owner_side):
    """Operator counts and concentration for one subnet and window.

    shares           {wallet: share of paid incentive}, all paid wallets
    sample           the wallets that were traced (a subset of shares)
    owner_addresses  owner coldkey and owner hotkey(s)
    owner_side       wallets that received TAO from, or sent TAO to, the owner

    Owner-linked wallets are reported as a share and left out of the operator
    counts and of the concentration index.

    Operators are counted among the traced wallets. A wallet too small to be traced
    is not counted as an operator: subnets with hundreds of dust wallets would
    otherwise seem to have hundreds of operators. Its pay is reported in
    `untraced_share`, and in the concentration index it stands alone.

    clusters_ub    operators when wallets are merged only through a shared funder that is
                   not an exchange: an upper bound on the number of operators
    clusters_best  the same after merging wallets on one miner IP and wallets paid out
                   of an exchange in one batch: never more than clusters_ub
    """
    empty = {"clusters_ub": 0, "clusters_best": 0, "hhi_best": None, "owner_linked_share": None,
             "untraced_share": None, "unattrib_share": None, "roots_best": {}, "owner_linked": []}
    total = sum(shares.values())
    if total <= 0:
        return empty

    in_sample = set(sample)
    lower = cluster(sample, funding, level2, profiles, ips, "lower")
    best = cluster(sample, funding, level2, profiles, ips, "best")

    linked = {c for c in sample if any(r["frm"] in owner_addresses for r in funding.get(c, []))}
    linked |= set(owner_side) & set(shares)
    owner_roots = {lower.root(c) for c in linked if c in in_sample}
    owner_roots |= {lower.root(a) for a in owner_addresses if lower.has(a)}
    linked |= {c for c in sample if lower.root(c) in owner_roots}

    def aggregate(part):
        agg = defaultdict(float)
        for c, s in shares.items():
            if c in linked:
                continue
            agg[part.root(c) if c in in_sample else c] += s
        return agg

    def operators(part):
        return len({part.root(c) for c in sample if c in shares and c not in linked})

    agg_best = aggregate(best)
    sizes = lower.sizes()
    blind = sum(
        shares[c] for c in sample
        if c in shares and c not in linked and sizes[lower.root(c)] == 1
        and any(is_exchange(profiles, r["frm"]) for r in funding.get(c, []))
    )
    return {
        "clusters_ub": operators(lower),
        "clusters_best": operators(best),
        "hhi_best": hhi_from_amounts(agg_best.values()),
        "owner_linked_share": sum(shares[c] for c in linked if c in shares) / total,
        "untraced_share": sum(s for c, s in shares.items() if c not in in_sample) / total,
        "unattrib_share": blind / total,
        "roots_best": {c: best.root(c) for c in sample},
        "owner_linked": sorted(linked),
    }
