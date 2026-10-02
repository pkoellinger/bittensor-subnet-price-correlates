"""Project clocks per subnet (Y12): registration, owner change, identity change, first emission.

Sources
  roster (chain)              registration and first-emission blocks
  Taostats /api/subnet/owner/v1         owner changes; each one is checked against chain state
  Taostats /api/subnet/identity_set/v1  identity-set events with the identity fields

Writes  data/intermediate/history_wave<N>.csv   one row per subnet

project_age_days counts from the most recent of registration and a real identity
change (different name, GitHub owner or website host). Owner-key changes are reported
in their own column but do not reset the project age: a key swap can be a wallet
migration by the same team.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import chain, paths  # noqa: E402
from snprice.events import last_real_identity_change  # noqa: E402
from snprice.io import archive, read_table, taostats, write_table  # noqa: E402
from snprice.windows import bounds  # noqa: E402

P = "SubtensorModule"


def epoch(text):
    return time.mktime(time.strptime(text, "%Y-%m-%d %H:%M:%S")) - time.timezone


def main():
    cfg = paths.snapshot()
    wave, T = cfg["wave"], cfg["t_block"]
    roster = read_table(paths.CHAIN / f"roster_wave{wave}.csv")
    tao, arch = taostats(), archive()
    t_time = arch.timestamp(T)
    window_start = bounds(cfg, "window")[0]

    owner_rows = tao.get_all("/api/subnet/owner/v1", per_page=200, block_end=T)
    ident_rows = tao.get_all("/api/subnet/identity_set/v1", per_page=200, block_end=T)
    print(f"{len(owner_rows)} owner-history rows, {len(ident_rows)} identity-set events up to T", flush=True)

    out, checked, mismatches = [], 0, 0
    for r in roster:
        n, reg_block = int(r["netuid"]), int(r["registered_block"])

        changes = sorted((int(o["block_number"]) for o in owner_rows
                          if int(o["netuid"]) == n and int(o["block_number"]) > reg_block
                          and (o.get("previous_owner") or {}).get("ss58")
                          and (o.get("owner") or {}).get("ss58") != (o.get("previous_owner") or {}).get("ss58")))
        owner_change_block = changes[-1] if changes else None
        if owner_change_block:
            k = chain.key(P, "SubnetOwner", chain.u16(n))
            before = arch.read([k], owner_change_block - 1)[k]
            after = arch.read([k], owner_change_block)[k]
            checked += 1
            if before == after:
                mismatches += 1
                print(f"  netuid {n}: Taostats reports an owner change at {owner_change_block}, chain shows none",
                      flush=True)
                owner_change_block = None

        ident = last_real_identity_change([i for i in ident_rows if int(i["netuid"]) == n], reg_block)
        ident_block = ident["block"] if ident else None

        def days_since(block):
            return (t_time - arch.timestamp(block)) / 86400.0 if block else None

        start_block = max(reg_block, ident_block or 0)
        out.append({
            "netuid": n,
            "days_since_registration": (t_time - epoch(r["registered_utc"])) / 86400.0,
            "days_since_first_emission": ((t_time - epoch(r["first_emission_utc"])) / 86400.0
                                          if r["first_emission_utc"] else None),
            "owner_change_block": owner_change_block,
            "days_since_owner_change": days_since(owner_change_block),
            "owner_changed_in_window": int(bool(owner_change_block and owner_change_block > window_start)),
            "identity_change_block": ident_block,
            "identity_change_what": ident["what"] if ident else None,
            "identity_change_before": ident["before"] if ident else None,
            "identity_change_after": ident["after"] if ident else None,
            "days_since_identity_change": days_since(ident_block),
            "project_start_block": start_block,
            "project_start_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(arch.timestamp(start_block))),
            "project_age_days": days_since(start_block),
        })

    write_table(paths.INTERMEDIATE / f"history_wave{wave}.csv", out)
    print(f"wrote history for {len(out)} subnets; owner changes checked on chain: {checked}, "
          f"not confirmed: {mismatches}; with an owner change: {sum(1 for o in out if o['owner_change_block'])}; "
          f"with a real identity change: {sum(1 for o in out if o['identity_change_block'])}")
    probe = next(o for o in out if o["netuid"] == 111)
    print("  SN111:", {k: probe[k] for k in ("owner_change_block", "identity_change_block", "identity_change_what",
                                             "project_start_utc", "project_age_days")})


if __name__ == "__main__":
    main()
