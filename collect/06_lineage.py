"""Miner operators by funding lineage (Y4), and owner-linked miners (D3), for the 30-day window.

Method: snprice/lineage.py (the two cautious lenses of the 18 Sep 2026 note: funding links
only, which gives an upper bound on the number of operators, and the best estimate, which also
merges wallets on one miner IP and wallets paid out of an exchange in one batch).

Taostats calls
  A  largest inbound transfers of each traced wallet before it registered
       /api/transfer/v1?to=<wallet>&block_end=<reg-1>&amount_min=<threshold>&order=amount_desc&limit=50
  C  for wallets with at least 0.5% share: inbound transfers of their three largest funders
  B  lifetime transfer count (up to T) of every address that links two or more wallets, and of the
     funders of wallets with at least 0.5% share  (more than 1,500 = exchange-like)
  D  transfers out of and into the subnet owner's coldkeys (owner-linked wallets): the current
     key and every key that owned the subnet since the current project started
     (snprice.events.project_owner_keys), the newest 600 transfers of each in either direction

Traced wallets: share of paid incentive at or above the floor (0.1%), largest first, at most
`lineage_max_wallets_per_subnet` per subnet (250; no subnet reached it in wave 1, where the
largest count was 207). If the planned calls exceed the cap, the floor is raised for all
subnets alike. Operators are counted among the traced wallets; smaller wallets are reported
as the untraced share.
The funding threshold is 20% of the miner registration cost at the time the wallet registered
(the chain sample nearest to its registration; the window median if it registered earlier
than the samples reach), with a minimum of 0.01 TAO.

Reads   data/intermediate/miner_shares_wave<N>.csv, data/chain/grid_wave<N>.csv
Writes  data/intermediate/lineage_wave<N>.csv            one row per subnet
        data/intermediate/lineage_wallets_wave<N>.csv    wallet-level partition (not committed)
"""
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.events import project_owner_keys  # noqa: E402
from snprice.io import read_table, taostats, write_table  # noqa: E402
from snprice.lineage import LEVEL2_ROWS, lineage_summary  # noqa: E402
from snprice.windows import sample_blocks  # noqa: E402

RAO = 10 ** 9
MIN_THRESHOLD_TAO = 0.01
FLOORS = (0.001, 0.002, 0.005, 0.01, 0.02)
OWNER_PAGES = 3


def slim(rows):
    return [{"frm": r["from"]["ss58"], "to": r["to"]["ss58"], "amt": int(r["amount"]) / RAO,
             "blk": int(r["block_number"])} for r in rows]


def main():
    cfg = paths.snapshot()
    wave, T = cfg["wave"], cfg["t_block"]
    roster = {int(r["netuid"]): r for r in read_table(paths.CHAIN / f"roster_wave{wave}.csv")}
    tao = taostats()

    shares, first_reg, ips = defaultdict(dict), {}, {}
    for r in read_table(paths.INTERMEDIATE / f"miner_shares_wave{wave}.csv"):
        if r["window"] != "30d":
            continue
        n = int(r["netuid"])
        shares[n][r["coldkey"]] = float(r["share"])
        first_reg[(n, r["coldkey"])] = int(r["first_registered_block"]) if r["first_registered_block"] else None
        ips[(n, r["coldkey"])] = set((r["ips"] or "").split("|")) - {""}

    # registration cost over time, for the funding threshold
    window = set(sample_blocks(cfg, "window"))
    cost = defaultdict(dict)
    for r in read_table(paths.CHAIN / f"grid_wave{wave}.csv"):
        if r["reg_cost_tao"] is not None:
            cost[int(r["netuid"])][int(r["block"])] = float(r["reg_cost_tao"])

    def threshold(n, reg_block):
        series = cost[n]
        if not series:
            return MIN_THRESHOLD_TAO
        if reg_block and reg_block >= min(series):
            nearest = min(series, key=lambda b: abs(b - reg_block))
            base = series[nearest]
        else:
            base = statistics.median(v for b, v in series.items() if b in window) if window & set(series) \
                else statistics.median(series.values())
        return max(MIN_THRESHOLD_TAO, 0.2 * base)

    # choose the share floor so that the job stays under the call cap
    def sample_for(floor):
        return {n: [c for c, s in sorted(sh.items(), key=lambda kv: -kv[1]) if s >= floor]
                [:cfg["lineage_max_wallets_per_subnet"]] for n, sh in shares.items()}

    for floor in FLOORS:
        sample = sample_for(floor)
        pairs = sum(len(v) for v in sample.values())
        planned = int(pairs * 1.7) + 2 * OWNER_PAGES * len(sample)
        print(f"share floor {floor:.1%}: {pairs} wallet-subnet pairs, about {planned} calls", flush=True)
        if planned <= cfg["lineage_call_cap"]:
            break
    else:
        raise SystemExit("lineage does not fit under the call cap even at the highest floor")

    # owner keys of the current project (Taostats owner history; the last change of every subnet was
    # checked on chain by 03_history_events)
    project_start = {int(h["netuid"]): int(h["project_start_block"])
                     for h in read_table(paths.INTERMEDIATE / f"history_wave{wave}.csv")}
    owner_changes = defaultdict(list)
    for o in tao.get_all("/api/subnet/owner/v1", per_page=200, block_end=T):
        n = int(o["netuid"])
        previous = (o.get("previous_owner") or {}).get("ss58")
        if n in roster and int(o["block_number"]) > int(roster[n]["registered_block"]) and previous \
                and o["owner"]["ss58"] != previous:
            owner_changes[n].append({"block": int(o["block_number"]), "owner": o["owner"]["ss58"],
                                     "previous_owner": previous})

    out, wallet_rows = [], []
    profiles = {}

    def profile(address):
        if address not in profiles:
            body = tao.get("/api/transfer/v1", address=address, block_end=T, limit=1)
            profiles[address] = {"total": (body.get("pagination") or {}).get("total_items") or 0}
        return profiles[address]

    done = 0
    for n in sorted(roster):
        sh = shares.get(n, {})
        if not sh:
            out.append({"netuid": n, "lineage_share_floor": floor, "lineage_wallets_traced": 0})
            continue
        owner, owner_hk = roster[n]["owner_coldkey"], roster[n]["owner_hotkey"]
        traced = sample[n]
        funding, level2 = {}, {}

        # pass A
        for c in traced:
            reg = first_reg.get((n, c))
            if not reg:
                funding[c] = []
                continue
            theta = int(threshold(n, reg) * RAO)
            body = tao.get("/api/transfer/v1", to=c, block_end=reg - 1, amount_min=theta,
                           order="amount_desc", limit=50)
            funding[c] = [r for r in slim(body["data"]) if r["frm"] != c]

        occ = defaultdict(set)
        for c in traced:
            for r in funding[c]:
                occ[r["frm"]].add(c)

        # pass C: one level up for material wallets
        for c in traced:
            if sh[c] < cfg["lineage_level2_share_floor"]:
                continue
            reg = first_reg.get((n, c))
            theta = int(threshold(n, reg) * RAO)
            for r in funding[c][:LEVEL2_ROWS]:
                f = r["frm"]
                if f in sh or f in level2 or len(occ[f]) >= 2:
                    continue
                body = tao.get("/api/transfer/v1", to=f, block_end=reg - 1, amount_min=theta,
                               order="block_number_asc", limit=5)
                level2[f] = {"total": (body.get("pagination") or {}).get("total_items") or 0,
                             "rows": [g for g in slim(body["data"]) if g["frm"] != f]}
        for c in traced:
            for r in funding[c][:LEVEL2_ROWS]:
                for g in level2.get(r["frm"], {}).get("rows", [])[:LEVEL2_ROWS]:
                    occ[g["frm"]].add(c)

        # pass B: profile linking addresses and the funders of material wallets
        need = {a for a, cs in occ.items() if len(cs) >= 2 and a not in sh}
        need |= {r["frm"] for c in traced if sh[c] >= cfg["lineage_level2_share_floor"] for r in funding[c][:1]}
        local_profiles = {a: profile(a) for a in sorted(need)}

        # pass D: wallets that exchanged TAO with the owner. The owner is every key that owned the
        # subnet since the current project started: a team that moved to a new wallet is the same team.
        owner_keys = project_owner_keys(owner_changes[n], owner, project_start[n]) if owner else set()
        owner_side = set()
        for key in sorted(owner_keys, key=lambda k: k != owner):       # the current owner first
            for direction in ("from", "to"):
                rows = tao.get_all("/api/transfer/v1", per_page=200, max_pages=OWNER_PAGES, partial_ok=True,
                                   block_end=T, order="block_number_desc", **{direction: key})
                for r in slim(rows):
                    other = r["to"] if direction == "from" else r["frm"]
                    if other in sh:
                        owner_side.add(other)

        summary = lineage_summary(sh, traced, funding, level2, local_profiles,
                                  {c: ips.get((n, c), set()) for c in traced}, (owner_keys | {owner_hk}) - {None},
                                  owner_side)
        out.append({
            "netuid": n,
            "lineage_share_floor": floor,
            "lineage_wallets_traced": len(traced),
            "miners_lineage_clusters_ub_30d": summary["clusters_ub"],
            "miners_lineage_clusters_best_30d": summary["clusters_best"],
            "miner_hhi_lineage_best_30d": summary["hhi_best"],
            "miners_unattrib_share_30d": summary["unattrib_share"],
            "lineage_untraced_share_30d": summary["untraced_share"],
            "owner_linked_incentive_share_30d": summary["owner_linked_share"],
        })
        for c in traced:
            wallet_rows.append({"netuid": n, "coldkey": c, "share": sh[c], "root_best": summary["roots_best"][c],
                                "owner_linked": int(c in summary["owner_linked"]),
                                "funders": "|".join(r["frm"] for r in funding[c][:3])})
        done += 1
        if done % 8 == 0:
            print(f"  {done} subnets done (netuid {n}), Taostats {tao.stats}", flush=True)

    write_table(paths.INTERMEDIATE / f"lineage_wave{wave}.csv", out)
    write_table(paths.INTERMEDIATE / f"lineage_wallets_wave{wave}.csv", wallet_rows)
    print(f"wrote lineage for {done} subnets with paid miners; Taostats {tao.stats}")


if __name__ == "__main__":
    main()
