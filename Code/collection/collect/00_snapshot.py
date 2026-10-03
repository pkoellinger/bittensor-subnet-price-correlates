"""Pin the wave: the list of subnets at block T and their on-chain identity.

Writes  data/chain/roster_wave<N>.csv   one row per subnet at T

Source: public archive node only (no API key needed).
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import chain, paths  # noqa: E402
from snprice.events import contact_without_mailbox, norm_name  # noqa: E402
from snprice.io import archive, write_table  # noqa: E402
from snprice.windows import bounds  # noqa: E402

P = "SubtensorModule"
PLACEHOLDER_NAMES = {"", "unknown", "parked", "forsale", "available", "deprecated"}


def utc(seconds):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(seconds))


def main():
    cfg = paths.snapshot()
    T = cfg["t_block"]
    arch = archive()

    t_time = arch.timestamp(T)
    if not utc(t_time).startswith(cfg["snapshot_date"]):
        raise SystemExit(f"block {T} is at {utc(t_time)} UTC, not on {cfg['snapshot_date']}")
    print(f"T = block {T} = {utc(t_time)} UTC (runtime spec {arch.spec_version(T)})", flush=True)
    for name in ("window", "lag"):
        lo, hi = bounds(cfg, name)
        print(f"  {name:6s} ({lo}, {hi}]  = {utc(arch.timestamp(lo))} to {utc(arch.timestamp(hi))} UTC", flush=True)

    added = arch.read_map(P, "NetworksAdded", range(0, 257), T)
    netuids = sorted(n for n, v in added.items() if chain.decode_bool(v) and n != 0)
    print(f"{len(netuids)} subnets exist at T (netuid {netuids[0]} to {netuids[-1]})", flush=True)

    reg = arch.read_map(P, "NetworkRegisteredAt", netuids, T)
    first = arch.read_map(P, "FirstEmissionBlockNumber", netuids, T)
    tempo = arch.read_map(P, "Tempo", netuids, T)
    owner = arch.read_map(P, "SubnetOwner", netuids, T)
    owner_hk = arch.read_map(P, "SubnetOwnerHotkey", netuids, T)
    ident = arch.read_map(P, "SubnetIdentitiesV3", netuids, T,
                          part=lambda n: chain.blake2_128_concat(chain.u16(n)))

    lo30, _ = bounds(cfg, "window")
    rows = []
    for n in netuids:
        reg_block = chain.decode_uint(reg[n])
        if reg_block is None:
            raise SystemExit(f"netuid {n} has no registration block")
        first_block = chain.decode_uint(first[n])
        tempo_blocks = chain.decode_uint(tempo[n])
        if not tempo_blocks:
            raise SystemExit(f"netuid {n} has no tempo")
        identity = chain.decode_identity(ident[n]) or {}
        name = (identity.get("subnet_name") or "").strip()
        rows.append({
            "netuid": n,
            "subnet_uid": f"{n}-{reg_block}",
            "registered_block": reg_block,
            "registered_utc": utc(arch.timestamp(reg_block)),
            "first_emission_block": first_block,
            "first_emission_utc": utc(arch.timestamp(first_block)) if first_block else None,
            "tempo": tempo_blocks,
            "flag_registered_in_window": int(reg_block > lo30),
            "owner_coldkey": chain.decode_account(owner[n]),
            "owner_hotkey": chain.decode_account(owner_hk[n]),
            "subnet_name": name,
            "flag_placeholder_identity": int(norm_name(name) in PLACEHOLDER_NAMES),
            "github_repo": (identity.get("github_repo") or "").strip(),
            "subnet_url": (identity.get("subnet_url") or "").strip(),
            "subnet_contact": contact_without_mailbox(identity.get("subnet_contact")),
            "discord": (identity.get("discord") or "").strip(),
            "description": " ".join((identity.get("description") or "").split()),
        })
        if n % 32 == 0:
            print(f"  netuid {n} done (archive calls so far {arch.calls})", flush=True)

    out = paths.CHAIN / f"roster_wave{cfg['wave']}.csv"
    write_table(out, rows)
    print(f"wrote {out.relative_to(paths.PROJECT)}: {len(rows)} subnets, {arch.calls} archive calls")
    print("  placeholder identity:", [r["netuid"] for r in rows if r["flag_placeholder_identity"]])
    print("  registered inside the 30-day window:", [r["netuid"] for r in rows if r["flag_registered_in_window"]])


if __name__ == "__main__":
    main()
