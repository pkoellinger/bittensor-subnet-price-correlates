"""Chain state per subnet at block T and at T - 30 days of blocks.

Supply and burn (B5), owner holdings and locks (B3, B4, Y22), validator structure
(C5), protocol settings (C6), registered and immune UIDs (D1), TAO recycled for
miner registrations (C3), startup mode (C8).

Writes  data/chain/state_wave<N>.csv   one row per (label in {t, lag}, subnet)

Source: public archive node only (no API key needed).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import chain, paths  # noqa: E402
from snprice.io import archive, read_table, write_table  # noqa: E402
from snprice.metrics import hhi_from_amounts  # noqa: E402
from snprice.windows import bounds  # noqa: E402

P = "SubtensorModule"
RAO = 10 ** 9
DIVIDEND_SAMPLES = 30          # one a day over the 30 days before the state block


def nkey(item, n):
    return chain.key(P, item, chain.u16(n))


def bkey(item, n):             # maps hashed with Blake2_128Concat(netuid)
    return chain.key(P, item, chain.blake2_128_concat(chain.u16(n)))


def tkey(pallet, item, n):     # maps hashed with Twox64Concat(netuid)
    return chain.key(pallet, item, chain.twox64_concat(chain.u16(n)))


def account(ss58):
    return chain.blake2_128_concat(chain.ss58_decode(ss58))


def state_at(arch, netuids, block, cfg, with_uid_ages):
    """Return {netuid: dict of columns} for one block."""
    simple = {}
    for n in netuids:
        simple.update({
            ("alpha_in", n): nkey("SubnetAlphaIn", n),
            ("alpha_out", n): nkey("SubnetAlphaOut", n),
            ("protocol", n): nkey("SubnetProtocolAlpha", n),
            ("burned", n): tkey("AlphaAssets", "AlphaBurned", n),
            ("recycled_alpha", n): tkey("AlphaAssets", "AlphaRecycled", n),
            ("owner", n): nkey("SubnetOwner", n),
            ("owner_hk", n): nkey("SubnetOwnerHotkey", n),
            ("registered", n): nkey("NetworkRegisteredAt", n),
            ("first_emission", n): nkey("FirstEmissionBlockNumber", n),
            ("owner_lock", n): nkey("OwnerLock", n),
            ("decaying_owner_lock", n): nkey("DecayingOwnerLock", n),
            ("autolock", n): nkey("OwnerCutAutoLockEnabled", n),
            ("permit", n): nkey("ValidatorPermit", n),
            ("stake_weight", n): nkey("StakeWeight", n),
            ("commit_reveal", n): nkey("CommitRevealWeightsEnabled", n),
            ("yuma3", n): bkey("Yuma3On", n),
            ("liquid_alpha", n): bkey("LiquidAlphaOn", n),
            ("max_uids", n): nkey("MaxAllowedUids", n),
            ("n_uids", n): nkey("SubnetworkN", n),
            ("mech_count", n): tkey(P, "MechanismCountCurrent", n),
            ("immunity", n): nkey("ImmunityPeriod", n),
            ("rao_recycled", n): nkey("RAORecycledForRegistration", n),
        })
    simple[("unlock_rate",)] = chain.key(P, "UnlockRate")
    v = arch.read(list(simple.values()), block)
    g = lambda *k: v[simple[k]]  # noqa: E731
    unlock_rate = chain.decode_uint(g("unlock_rate"), default=934866)

    owner = {n: chain.decode_account(g("owner", n)) for n in netuids}
    owner_hk = {n: chain.decode_account(g("owner_hk", n)) for n in netuids}

    # second round: things keyed by the owner's accounts
    second = {}
    for n in netuids:
        if owner[n]:
            second[("staking_hotkeys", n)] = chain.key(P, "StakingHotkeys", account(owner[n]))
            second[("decaying_flag", n)] = chain.key(P, "DecayingLock", account(owner[n]), chain.u16(n))
        if owner_hk[n]:
            second[("owner_hk_alpha", n)] = chain.key(P, "TotalHotkeyAlpha", account(owner_hk[n]), chain.u16(n))
            second[("owner_hk_uid", n)] = chain.key(P, "Uids", chain.u16(n), account(owner_hk[n]))
    v2 = arch.read(list(second.values()), block)
    g2 = lambda *k: v2.get(second.get(k)) if k in second else None  # noqa: E731

    # third round: the owner's stake positions on its own subnet, and its own locks
    third = {}
    lock_keys = {}
    for n in netuids:
        if not owner[n]:
            continue
        for hk in chain.decode_vec_account(g2("staking_hotkeys", n)) or []:
            h = account(hk)
            third[("shares", n, hk)] = chain.key(P, "AlphaV2", h, account(owner[n]), chain.u16(n))
            third[("hk_alpha", n, hk)] = chain.key(P, "TotalHotkeyAlpha", h, chain.u16(n))
            third[("hk_shares", n, hk)] = chain.key(P, "TotalHotkeySharesV2", h, chain.u16(n))
        prefix = chain.key(P, "Lock", account(owner[n]), chain.u16(n))
        lock_keys[n] = arch.keys(prefix, block)
        for k in lock_keys[n]:
            third[("lock", n, k)] = k
    v3 = arch.read(list(third.values()), block) if third else {}

    # dividend share of the owner hotkey, averaged over daily samples before the block
    div_blocks = [block - cfg["blocks_per_day"] * d for d in range(DIVIDEND_SAMPLES)]
    div_share = {n: [] for n in netuids}
    for b in div_blocks:
        dk = {n: nkey("Dividends", n) for n in netuids}
        uk = {n: chain.key(P, "Uids", chain.u16(n), account(owner_hk[n])) for n in netuids if owner_hk[n]}
        rk = {n: nkey("NetworkRegisteredAt", n) for n in netuids}
        dv = arch.read(list(dk.values()) + list(uk.values()) + list(rk.values()), b)
        for n in netuids:
            if dv[rk[n]] != g("registered", n):
                continue                       # another subnet occupied this netuid then
            vec = chain.decode_vec_u16(dv[dk[n]]) or []
            total = sum(vec)
            if total <= 0:
                continue
            uid = chain.decode_uint(dv[uk[n]]) if n in uk else None
            div_share[n].append((vec[uid] / total) if uid is not None and uid < len(vec) else 0.0)
        arch.forget(b)

    ages = {}
    if with_uid_ages:
        ak = {(n, u): chain.key(P, "BlockAtRegistration", chain.u16(n), chain.u16(u))
              for n in netuids for u in range(chain.decode_uint(g("n_uids", n), 0))}
        av = arch.read(list(ak.values()), block)
        for (n, u), k in ak.items():
            ages.setdefault(n, []).append(chain.decode_uint(av[k], 0))

    rows = {}
    for n in netuids:
        alpha_in = chain.decode_uint(g("alpha_in", n), 0) / RAO
        alpha_out = chain.decode_uint(g("alpha_out", n), 0) / RAO
        issued = alpha_in + alpha_out
        burned = chain.decode_uint(g("burned", n))
        protocol = chain.decode_uint(g("protocol", n), 0) / RAO
        staked = alpha_out - (burned or 0) / RAO - protocol

        # owner's alpha on its own subnet
        owner_alpha = 0.0
        for hk in (chain.decode_vec_account(g2("staking_hotkeys", n)) or []) if owner[n] else []:
            shares = chain.decode_decimal(v3[third[("shares", n, hk)]]) or 0.0
            hk_shares = chain.decode_decimal(v3[third[("hk_shares", n, hk)]]) or 0.0
            hk_alpha = chain.decode_uint(v3[third[("hk_alpha", n, hk)]], 0) / RAO
            if hk_shares > 0:
                owner_alpha += shares * hk_alpha / hk_shares

        # locks
        perpetual_flag = chain.decode_bool(g2("decaying_flag", n))      # False = perpetual, None = decays
        own_perpetual = perpetual_flag is False
        own_locked = 0.0
        for k in lock_keys.get(n, []):
            lock = chain.decode_lock(v3[k])
            if not lock:
                continue
            mass = lock["locked_mass_rao"] / RAO
            own_locked += mass if own_perpetual else chain.decayed_mass(mass, lock["last_update"], block, unlock_rate)
        ol = chain.decode_lock(g("owner_lock", n))
        dl = chain.decode_lock(g("decaying_owner_lock", n))
        hk_locked = (ol["locked_mass_rao"] / RAO if ol else 0.0) + (
            chain.decayed_mass(dl["locked_mass_rao"] / RAO, dl["last_update"], block, unlock_rate) if dl else 0.0)

        permit = chain.decode_vec_bool(g("permit", n)) or []
        stake_w = chain.decode_vec_u16(g("stake_weight", n)) or []
        validator_weights = [w for w, p in zip(stake_w, permit) if p]
        owner_hk_alpha = chain.decode_uint(g2("owner_hk_alpha", n), 0) / RAO
        immunity = chain.decode_uint(g("immunity", n), default=4096)
        uid_ages = ages.get(n)
        first_emission = chain.decode_uint(g("first_emission", n))

        rows[n] = {
            "netuid": n,
            "state_block": block,
            "registered_block": chain.decode_uint(g("registered", n)),
            "owner_coldkey": owner[n],
            "alpha_issued": round(issued, 6),
            "alpha_in_pool": round(alpha_in, 6),
            "alpha_staked_by_wallets": round(staked, 6),
            "alpha_protocol_owned": round(protocol, 6),
            "alpha_burned": round(burned / RAO, 6) if burned is not None else None,
            "alpha_burned_share": (burned / RAO / issued) if burned is not None and issued > 0 else None,
            "owner_alpha": round(owner_alpha, 6),
            "owner_alpha_share_issued": owner_alpha / issued if issued > 0 else None,
            "stake_share_owner_validator": owner_hk_alpha / staked if staked > 0 else None,
            "owner_locked_alpha": round(own_locked, 6),
            "owner_lock_share_owner_alpha": min(1.0, own_locked / owner_alpha) if owner_alpha > 0 else None,
            "ownerhk_locked_alpha": round(hk_locked, 6),
            "ownerhk_lock_share_issued": hk_locked / issued if issued > 0 else None,
            "owner_lock_perpetual": int(own_perpetual and own_locked > 0),
            "owner_cut_autolock": int(chain.decode_bool(g("autolock", n), default=False)),
            "validators_n": sum(permit),
            "owner_validator_div_share": (sum(div_share[n]) / len(div_share[n])) if div_share[n] else None,
            "validator_stake_hhi": hhi_from_amounts(validator_weights),
            "commit_reveal_on": int(chain.decode_bool(g("commit_reveal", n), default=True)),
            "yuma3_on": int(chain.decode_bool(g("yuma3", n), default=False)),
            "liquid_alpha_on": int(chain.decode_bool(g("liquid_alpha", n), default=False)),
            "mech_count": chain.decode_uint(g("mech_count", n), default=1),
            "max_neurons": chain.decode_uint(g("max_uids", n), default=256),
            "uids_registered_now": chain.decode_uint(g("n_uids", n), default=0),
            "uids_immune_share_now": (sum(1 for a in uid_ages if block - a < immunity) / len(uid_ages))
            if uid_ages else None,
            "rao_recycled_cumulative": chain.decode_uint(g("rao_recycled", n), default=0),
            "startup_mode": int(first_emission is None),
        }
    return rows


def main():
    cfg = paths.snapshot()
    wave, T = cfg["wave"], cfg["t_block"]
    roster = read_table(paths.CHAIN / f"roster_wave{wave}.csv")
    netuids = [int(r["netuid"]) for r in roster]
    arch = archive()
    arch.batch = 3000
    lag_block = bounds(cfg, "lag")[1]

    out = []
    for label, block, ages in (("t", T, True), ("lag", lag_block, False)):
        print(f"state at {label} (block {block})", flush=True)
        rows = state_at(arch, netuids, block, cfg, with_uid_ages=ages)
        for n in netuids:
            out.append({"label": label, **rows[n]})
        print(f"  done, {arch.calls} archive calls so far", flush=True)

    write_table(paths.CHAIN / f"state_wave{wave}.csv", out)
    t_rows = {r["netuid"]: r for r in out if r["label"] == "t"}
    print(f"wrote state for {len(netuids)} subnets x 2 blocks")
    for n in (64, 111, 17):
        r = t_rows[n]
        print(f"  SN{n}: issued {r['alpha_issued']:,.0f}, burned share {r['alpha_burned_share']:.3f}, owner alpha "
              f"{r['owner_alpha']:,.0f}, owner locked {r['owner_locked_alpha']:,.0f}, locked to owner hotkey "
              f"{r['ownerhk_locked_alpha']:,.0f}, validators {r['validators_n']}, owner div share "
              f"{r['owner_validator_div_share']}")


if __name__ == "__main__":
    main()
