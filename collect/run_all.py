"""Run the collection and build steps of a wave in order.

    python collect/run_all.py                       wave 1 (config/snapshot.json)
    python collect/run_all.py --config snapshot_wave2.json
    python collect/run_all.py --from 06_lineage     start at a step (earlier ones are cached anyway)
    python collect/run_all.py --list                show the steps

Every step is a script of its own and can be run alone. Steps read the saved answers of
earlier runs, so repeating a step costs no API calls. The run stops at the three places
where a person has to act (marked HAND below) and says what is needed.

Keys: TAOSTATS_API_KEY for the Taostats steps, X_BEARER_TOKEN for the X steps, a GitHub token
(GITHUB_TOKEN or a logged-in `gh`) for the GitHub steps. Chain steps need no key.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (step, command, what it needs)
STEPS = [
    ("00_snapshot", "collect/00_snapshot.py", "chain"),
    ("01_chain_grid", "collect/01_chain_grid.py", "chain, about one hour"),
    ("02_chain_state", "collect/02_chain_state.py", "chain"),
    ("05_aggregate_grid", "collect/05_aggregate_grid.py", ""),
    ("10_links", "collect/10_links.py", "Taostats, GitHub"),
    ("11_github", "collect/11_github.py", "GitHub"),
    ("12_web", "collect/12_web.py", "Chrome"),
    ("12c_site_handles", "collect/12c_site_handles.py", "Chrome"),
    ("12d_x_handle_guess", "collect/12d_x_handle_guess.py", "X (profile lookups)"),
    ("10_links_again", "collect/10_links.py", "second pass: adds the X handles found by the two steps before"),
    ("13_x_accounts", "collect/13_x_accounts.py", "X (profile lookups and counts)"),
    ("07_holders", "collect/07_holders.py", "Taostats, chain; run as close to T as possible"),
    ("03_history_events", "collect/03_history_events.py", "Taostats, chain"),
    ("08_owner_trades", "collect/08_owner_trades.py", "Taostats, chain"),
    ("09_baskets", "collect/09_baskets.py", "Taostats"),
    ("04_registrations", "collect/04_registrations.py", "Taostats"),
    ("18_tao_usd", "collect/18_tao_usd.py", "Taostats"),
    ("06_lineage", "collect/06_lineage.py", "Taostats, about five hours"),
    ("15_podcasts", "collect/15_podcasts.py", "RSS feeds, YouTube pages"),
    ("16_exploit", "collect/16_exploit.py", "stream.vidaio.io"),
    ("12b_dossiers", "collect/12b_dossiers.py", ""),
    ("HAND_website_coding", None,
     "two coders fill data/manual/web_coding_coder_A.json and _B.json from the dossiers (config/coding_protocol.md)"),
    ("verify_evidence", "build/verify_evidence.py", "stops while items are open: add data/manual/web_coding_third_reading.csv"),
    ("12e_whitepapers", "collect/12e_whitepapers.py", "Chrome"),
    ("HAND_whitepaper_coding", None,
     "two coders fill data/manual/whitepaper_coding_coder_A.json and _B.json from the excerpts"),
    ("whitepaper_features", "build/whitepaper_features.py", "stops while items are open"),
    ("14_kol_candidates", "collect/14_kol.py candidates", "X (profile lookups and counts)"),
    ("HAND_account_approval", None, "the project owner approves accounts in config/kol_accounts.csv; no post is read before"),
    ("14_kol_posts", "collect/14_kol.py posts", "X (reads posts of the approved accounts)"),
    ("HAND_polarity_coding", None,
     "two coders fill data/manual/kol_polarity_coder_A.json and _B.json (config/polarity_criteria.md)"),
    ("kol_polarity", "build/kol_polarity.py", "stops while pairs lack a label"),
    ("build_dataset", "build/build_dataset.py", ""),
    ("validate", "build/validate.py --final", ""),
    ("build_rds", None, "Rscript build/build_rds.R data/final/<dataset>.csv codebook.csv"),
]


def main():
    args = sys.argv[1:]
    if "--list" in args:
        for name, command, needs in STEPS:
            print(f"{name:24} {command or '(by hand)':34} {needs}")
        return
    env = dict(os.environ)
    if "--config" in args:
        env["SNPRICE_SNAPSHOT"] = args[args.index("--config") + 1]
    start = args[args.index("--from") + 1] if "--from" in args else STEPS[0][0]
    names = [s[0] for s in STEPS]
    if start not in names:
        raise SystemExit(f"unknown step {start}; see --list")
    for name, command, needs in STEPS[names.index(start):]:
        if command is None:
            print(f"\nSTOP at {name}: {needs}\nWhen that is done, continue with: "
                  f"python collect/run_all.py --from {names[names.index(name) + 1]}")
            return
        print(f"\n=== {name} ({needs})" if needs else f"\n=== {name}", flush=True)
        result = subprocess.run([sys.executable, "-u"] + command.split(), cwd=ROOT, env=env)
        if result.returncode != 0:
            raise SystemExit(f"{name} stopped with exit status {result.returncode}")
    print("\nall steps done")


if __name__ == "__main__":
    main()
