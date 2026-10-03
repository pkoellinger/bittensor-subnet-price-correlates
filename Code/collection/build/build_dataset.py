"""Assemble the dataset: one row per subnet, columns as listed in codebook.csv.

Every value is taken from a table written by a collection script; this script only joins
them, computes the few derived columns named below and writes the result. It invents
nothing: a value that no collection script delivered stays missing.

Derived here
  price_usd              price_tao x tao_usd
  reg_recycled_tao_30d   change of the chain's cumulative counter between T-30d and T
  team_id, team_n_subnets  snprice.teams.team_ids on the links table
  columns ending in _lag30 that describe a state (locks, stakes, validators) are the values
  at block T-30d, and are missing if another subnet held the netuid then
  whitepaper_available   set to 0 where the white paper's link is dead (HTTP 404 or 410)

Reads   Input/codebook.csv and the tables in data/chain, Temp/collection-cache/intermediate, data/evidence
Writes  Input/subnets_wave<N>_<snapshot date>.csv
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.io import read_table, write_table  # noqa: E402
from snprice.teams import team_ids  # noqa: E402

RAO = 10 ** 9
STATE_AT_T = ("startup_mode", "uids_registered_now", "uids_immune_share_now", "owner_lock_share_owner_alpha",
              "ownerhk_lock_share_issued", "owner_lock_perpetual", "owner_cut_autolock", "stake_share_owner_validator",
              "owner_alpha_share_issued", "alpha_burned_share", "validators_n", "owner_validator_div_share",
              "validator_stake_hhi", "commit_reveal_on", "yuma3_on", "liquid_alpha_on", "mech_count", "max_neurons")
STATE_LAGGED = ("owner_lock_share_owner_alpha", "ownerhk_lock_share_issued", "stake_share_owner_validator",
                "owner_alpha_share_issued", "alpha_burned_share", "validators_n", "owner_validator_div_share",
                "validator_stake_hhi")
OPTIONAL = {"lineage", "whitepaper_features", "kol"}          # tables that may not exist yet


def by_netuid(path):
    return {int(r["netuid"]): r for r in read_table(path)}


def convert(value, kind):
    if value is None or value == "":
        return None
    if kind in ("integer", "binary"):
        return int(round(float(value)))
    if kind == "number":
        return float(value)
    return str(value)


def main():
    cfg = paths.snapshot()
    wave = cfg["wave"]
    I, E, C = paths.INTERMEDIATE, paths.EVIDENCE, paths.CHAIN
    codebook = read_table(paths.CODEBOOK)

    roster = by_netuid(C / f"roster_wave{wave}.csv")
    state = {"t": {}, "lag": {}}
    for r in read_table(C / f"state_wave{wave}.csv"):
        state[r["label"]][int(r["netuid"])] = r
    links = read_table(E / f"links_wave{wave}.csv")
    teams = team_ids(links)
    tao_usd = {r["label"]: float(r["tao_usd"]) for r in read_table(I / f"tao_usd_wave{wave}.csv")}

    tables = {name: by_netuid(I / f"{name}_wave{wave}.csv") for name in
              ("grid_agg", "github", "web", "web_coding", "x_accounts", "history", "owner_trades", "baskets",
               "podcasts", "exploit", "holders", "registrations")}
    pending = []
    for name in sorted(OPTIONAL):
        path = I / f"{name}_wave{wave}.csv"
        if path.exists():
            tables[name] = by_netuid(path)
        else:
            pending.append(path.name)
    papers = by_netuid(E / f"whitepapers_wave{wave}.csv") if (E / f"whitepapers_wave{wave}.csv").exists() else {}

    rows = []
    for n in sorted(roster):
        r, st, lag = roster[n], state["t"][n], state["lag"][n]
        same_subnet_at_lag = lag["registered_block"] == st["registered_block"]
        row = {"netuid": n, "subnet_uid": r["subnet_uid"], "wave": wave, "snapshot_date": cfg["snapshot_date"],
               "subnet_name": r["subnet_name"], "flag_placeholder_identity": r["flag_placeholder_identity"],
               "flag_registered_in_window": r["flag_registered_in_window"], **teams[n]}
        for table in tables.values():
            for key, value in table.get(n, {}).items():
                if key != "netuid":
                    row.setdefault(key, value)
        for key in STATE_AT_T:
            row[key] = st[key]
        for key in STATE_LAGGED:
            row[f"{key}_lag30"] = lag[key] if same_subnet_at_lag else None
        row["tao_usd"] = tao_usd["t"]
        row["price_usd"] = float(row["price_tao"]) * tao_usd["t"] if row.get("price_tao") else None
        row["reg_recycled_tao_30d"] = ((int(st["rao_recycled_cumulative"]) - int(lag["rao_recycled_cumulative"])) / RAO
                                       if same_subnet_at_lag else None)
        paper = papers.get(n)
        if paper:
            row["wp_pages"], row["wp_references"] = paper["wp_pages"], paper["wp_references"]
            if (paper["problem"] or "").startswith(("error: HTTP 404", "error: HTTP 410")):
                row["whitepaper_available"] = 0                 # the link to the white paper is dead
        rows.append(row)

    names = [c["name"] for c in codebook]
    produced = set().union(*(r.keys() for r in rows))
    missing = [c for c in names if c not in produced]
    if missing and not pending:
        raise SystemExit(f"codebook columns that no table delivers: {missing}")
    if missing:
        print(f"NOT FINAL: {pending} not collected yet; these columns are empty for now: {missing}")
    kinds = {c["name"]: c["type"] for c in codebook}
    final = [{name: convert(r.get(name), kinds[name]) for name in names} for r in rows]

    out = paths.FINAL / f"subnets_wave{wave}_{cfg['snapshot_date']}.csv"
    paths.FINAL.mkdir(parents=True, exist_ok=True)
    write_table(out, final, columns=names)
    print(f"wrote {out.relative_to(paths.PROJECT)}: {len(final)} rows, {len(names)} columns")
    unused = sorted(produced - set(names))
    print(f"collected but not in the codebook ({len(unused)}): {unused}")


if __name__ == "__main__":
    main()
