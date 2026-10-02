"""Sample the chain every 900 blocks over the feature window and the lagged window.

For every sample block and subnet: pool reserves (price), miner burn, emission flag,
miner registration cost, and the incentive vector with the wallet behind every paid UID.

Writes
  data/chain/blocks_wave<N>.csv                sample block, UTC time, runtime spec
  data/chain/grid_wave<N>.csv                  one row per (sample block, subnet)
  data/intermediate/incentive_wave<N>.csv.gz   one row per (sample block, subnet, paid UID)

Source: public archive node only (no API key needed). Feeds price (Y1, Y2), miner burn
(Y3), miner counts and concentration (Y4, D1), the emission flag (Y15) and the
registration cost (C3).
"""
import csv
import gzip
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import chain, paths  # noqa: E402
from snprice.io import archive, read_table, write_table  # noqa: E402
from snprice.metrics import uid_weights  # noqa: E402
from snprice.windows import sample_blocks  # noqa: E402

P = "SubtensorModule"
MAX_MECH = 2
RAO = 10 ** 9
TIME_KEY = chain.key("Timestamp", "Now")
INCENTIVE_COLUMNS = ["block", "netuid", "uid", "weight", "owner", "hotkey", "coldkey", "uid_registered_block", "ip"]


def utc(seconds):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(seconds))


def sample_keys(netuids):
    keys = {("time",): TIME_KEY}
    for n in netuids:
        keys[("tao", n)] = chain.key(P, "SubnetTAO", chain.u16(n))
        keys[("alpha_in", n)] = chain.key(P, "SubnetAlphaIn", chain.u16(n))
        keys[("burn", n)] = chain.key(P, "MinerBurned", chain.u16(n))
        keys[("enabled", n)] = chain.key(P, "SubnetEmissionEnabled", chain.u16(n))
        keys[("owner", n)] = chain.key(P, "SubnetOwner", chain.u16(n))
        keys[("owner_hk", n)] = chain.key(P, "SubnetOwnerHotkey", chain.u16(n))
        keys[("registered", n)] = chain.key(P, "NetworkRegisteredAt", chain.u16(n))
        keys[("reg_cost", n)] = chain.key(P, "Burn", chain.u16(n))
        keys[("split", n)] = chain.key(P, "MechanismEmissionSplit", chain.twox64_concat(chain.u16(n)))
        for m in range(MAX_MECH):
            keys[("inc", n, m)] = chain.key(P, "Incentive", chain.u16(chain.mech_index(n, m)))
    return keys


def main():
    cfg = paths.snapshot()
    wave = cfg["wave"]
    roster = read_table(paths.CHAIN / f"roster_wave{wave}.csv")
    netuids = [int(r["netuid"]) for r in roster]
    keys = sample_keys(netuids)
    blocks = sample_blocks(cfg, "all")
    arch = archive()
    arch.batch = 3000
    arch.pace = 0.25

    coldkey_of = {}     # hotkey hex -> coldkey ss58 (as of the first block the hotkey was seen paid)
    ip_of = {}          # (netuid, hotkey hex) -> IPv4 or None
    reg_of = {}         # (netuid, uid, hotkey hex) -> block at which that UID was registered
    grid_rows, block_rows = [], []
    paths.INTERMEDIATE.mkdir(parents=True, exist_ok=True)
    inc_path = paths.INTERMEDIATE / f"incentive_wave{wave}.csv.gz"
    started = time.time()

    with gzip.open(str(inc_path) + ".tmp", "wt", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=INCENTIVE_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for i, b in enumerate(blocks, 1):
            vals = arch.read(list(keys.values()), b)
            get = lambda *k: vals[keys[k]]  # noqa: E731
            when = chain.decode_uint(get("time")) / 1000.0
            block_rows.append({"block": b, "utc": utc(when), "spec": arch.spec_version(b)})

            weights = {
                n: uid_weights([chain.decode_vec_u16(get("inc", n, m)) for m in range(MAX_MECH)],
                               chain.decode_vec_u16(get("split", n)))
                for n in netuids
            }

            # hotkey behind every paid UID at this block
            hk_keys = {(n, uid): chain.key(P, "Keys", chain.u16(n), chain.u16(uid))
                       for n, w in weights.items() for uid in w}
            hk_vals = arch.read(list(hk_keys.values()), b) if hk_keys else {}
            hotkey = {}
            new_keys = {}
            for (n, uid), k in hk_keys.items():
                hk = hk_vals[k]
                if hk is None:
                    raise SystemExit(f"block {b}: netuid {n} uid {uid} is paid but has no hotkey")
                hotkey[(n, uid)] = hk
                raw_hk = bytes.fromhex(hk[2:])
                if hk not in coldkey_of:
                    new_keys[("cold", hk)] = chain.key(P, "Owner", chain.blake2_128_concat(raw_hk))
                if (n, hk) not in ip_of:
                    new_keys[("axon", n, hk)] = chain.key(P, "Axons", chain.u16(n), chain.blake2_128_concat(raw_hk))
                if (n, uid, hk) not in reg_of:
                    new_keys[("reg", n, uid, hk)] = chain.key(P, "BlockAtRegistration", chain.u16(n), chain.u16(uid))
            new_vals = arch.read(list(new_keys.values()), b) if new_keys else {}
            for ident, k in new_keys.items():
                if ident[0] == "cold":
                    coldkey_of[ident[1]] = chain.decode_account(new_vals[k])
                elif ident[0] == "axon":
                    axon = chain.decode_axon(new_vals[k])
                    ip_of[(ident[1], ident[2])] = axon["ip"] if axon and axon["ip_type"] == 4 else None
                else:
                    reg_of[ident[1:]] = chain.decode_uint(new_vals[k])

            for n in netuids:
                tao, alpha_in = chain.decode_uint(get("tao", n)), chain.decode_uint(get("alpha_in", n))
                owner = chain.decode_account(get("owner", n))
                owner_hk = get("owner_hk", n)
                reg_cost = chain.decode_uint(get("reg_cost", n))
                owner_weight = 0.0
                for uid, w in weights[n].items():
                    hk = hotkey[(n, uid)]
                    coldkey = coldkey_of[hk]
                    is_owner = (hk == owner_hk) or (coldkey is not None and coldkey == owner)
                    if is_owner:
                        owner_weight += w
                    writer.writerow({
                        "block": b, "netuid": n, "uid": uid, "weight": repr(w), "owner": int(is_owner),
                        "hotkey": chain.decode_account(hk), "coldkey": coldkey,
                        "uid_registered_block": reg_of[(n, uid, hk)], "ip": ip_of[(n, hk)],
                    })
                grid_rows.append({
                    "block": b,
                    "netuid": n,
                    "registered_block": chain.decode_uint(get("registered", n)),
                    "tao_in": tao / RAO if tao is not None else None,
                    "alpha_in": alpha_in / RAO if alpha_in is not None else None,
                    "price_tao": (tao / alpha_in) if tao and alpha_in else None,
                    "miner_burned": chain.decode_fixed(get("burn", n), 32, default=0.0),
                    "emission_enabled": int(chain.decode_bool(get("enabled", n), default=True)),
                    "reg_cost_tao": reg_cost / RAO if reg_cost is not None else None,
                    "paid_uids": len(weights[n]),
                    "owner_incentive_share": owner_weight if weights[n] else None,
                })
            arch.forget(b)
            if i % 20 == 0 or i == len(blocks):
                rate = (time.time() - started) / i
                print(f"  {i}/{len(blocks)} samples, block {b} ({utc(when)}), {arch.calls} archive calls, "
                      f"{len(coldkey_of)} hotkeys, about {rate * (len(blocks) - i) / 60:.0f} min left", flush=True)

    Path(str(inc_path) + ".tmp").replace(inc_path)
    write_table(paths.CHAIN / f"blocks_wave{wave}.csv", block_rows)
    write_table(paths.CHAIN / f"grid_wave{wave}.csv", grid_rows)
    print(f"wrote grid ({len(grid_rows)} rows), blocks ({len(block_rows)} rows) and {inc_path.name}")

    # the chain's own burn measure must agree with the owner share of the incentive we attributed
    diffs = sorted(abs(r["miner_burned"] - r["owner_incentive_share"]) for r in grid_rows
                   if r["owner_incentive_share"] is not None)
    if diffs:
        print(f"check MinerBurned vs attributed owner share over {len(diffs)} subnet-samples: "
              f"median {diffs[len(diffs) // 2]:.4f}, 95th pct {diffs[int(len(diffs) * 0.95)]:.4f}, max {diffs[-1]:.4f}")


if __name__ == "__main__":
    main()
