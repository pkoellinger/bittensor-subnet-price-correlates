# Bittensor subnet price correlates

One row per Bittensor subnet, 128 subnets, measured at the end of 30 September 2026 (UTC).
The data are built for regressions with the subnet's token price as dependent variable and
for tests of out-of-sample prediction. This repository holds the dataset, a codebook, and the
code that collected every variable.

**Status (2 Oct 2026):** wave 1 is complete, validated and frozen under the git tag `wave1`.
Wave 2 is scheduled for 31 Oct 2026 (`WAVE2.md`); it adds the price change over October and
joins both waves into a panel. `PLAN.md` has the plan and the log of every design decision.

## Files

| Path | What it is |
|---|---|
| `data/final/subnets_wave1_2026-09-30.csv` | The dataset: 128 rows, 171 columns |
| `data/final/subnets_wave1_2026-09-30.rds` | The same as an R data frame; every column carries its label, unit, role and source as attributes |
| `codebook.csv` | One row per variable: label, type, unit, window, role, as-of time, source, script, link to price, notes |
| `collect/` | One script per block of variables; `collect/run_all.py --list` shows the order |
| `build/` | Joins the collected tables, validates the result, writes the `.rds`, runs the cross-checks |
| `snprice/` | Shared library (chain decoding, API clients with budgets, text matching, clustering) |
| `tests/` | 506 unit tests of the library |
| `config/` | Snapshot definition, alias table, podcast list, coding protocol, coder briefs, screening and reading rules for commentator posts |
| `data/chain/` | Tables read from the chain: reproducible without any API key |
| `data/evidence/` | What each coded or matched value rests on: page addresses, episode lists, session lists, coder answers |
| `data/manual/` | Everything decided by a person or a coder, with the reason |
| `PLAN.md` | Plan, status and the log of every design decision |
| `WAVE2.md` | Runbook for a follow-up wave and the panel that joins the waves |

Raw API answers and wallet-level tables are not in the repository (`data/raw`, `data/intermediate`).
Every script rebuilds them.

## Design

1. **Unit.** A subnet (netuid 1 to 128) at block T = 9,184,186, the last block of 30 Sep 2026 UTC.
   `subnet_uid` adds the registration block, because a netuid is reused when a subnet is deregistered.
2. **Pinned state.** Chain quantities are read from a public archive node at block T and at
   sample blocks every 900 blocks (eight a day). These columns need no API key to reproduce.
3. **Windows.** `_30d` is the 216,000 blocks before T (31 Aug to 30 Sep). `_lag30` is the
   216,000 blocks before that (1 to 31 Aug). `_90d` and `_12m` end at T.
4. **Time order.** The codebook gives each column a `role` (outcome, feature, feature_lag, flag,
   quality, id) and an `asof` time. `logret_30d` is the price change over September, so August
   features (`feature_lag`) can be tested against it today. Wave 2 (30 Oct 2026) adds forward outcomes.
5. **Link to price.** The codebook column `price_link` says where a variable moves with the
   price by construction: `mechanical (flow)` for purchases through the pool, `mechanical (gate)`
   for the emission columns, `likely two-way` for attention measures.
6. **No invented values.** A value comes from a script reading an API answer, or from two
   independent coders who must quote the page they rely on. Missing stays missing: a status
   column says why (`not_listed`, `dead`, `server_error`, `replaced_by_security_software`), and
   nothing is imputed.

Four subnets were registered inside September. Their windows start at registration
(`window_days_observed_30d`), and their lagged chain columns are missing.

## Variables

171 columns: 7 outcomes, 111 features, 32 lagged features, 9 flags, 6 quality measures, 6 identifiers.

| Block | Examples | Source | Script |
|---|---|---|---|
| Price (outcome) | `price_tao`, `price_tao_avg30`, `logret_30d` | chain | `01_chain_grid`, `05_aggregate_grid` |
| Miner burn | `burn_mean_30d` | chain | same |
| Paid miners | `miners_paid_coldkeys_30d`, `miner_hhi_coldkey_30d` | chain | same |
| Independent miner operators | `miners_lineage_clusters_best_30d` | chain, Taostats transfers | `06_lineage` |
| Emissions | `tao_emission_on_share_30d` | chain | same as price |
| Locks, owner and validator stakes, settings | `owner_lock_share_owner_alpha`, `validators_n` | chain | `02_chain_state` |
| Holders | `holders_top10_share`, `holders_hhi` | Taostats positions, balances from the chain at T | `07_holders` |
| Project clocks | `project_age_days`, `days_since_owner_change` | chain, Taostats history | `03_history_events` |
| Owner trading | `owner_net_buy_tao_30d` | Taostats | `08_owner_trades` |
| Validator baskets | `basket_net_buy_tao_30d` | Taostats | `09_baskets` |
| GitHub activity and documentation | `gh_commits_30d_org`, `doc_score` | GitHub | `10_links`, `11_github` |
| Website and coded facts | `website_live`, `product_live`, `api_public`, `mcp_server`, `team_named`, `category8` | subnet websites | `12_web`, `12b_dossiers`, `build/verify_evidence` |
| White paper | `whitepaper_available`, `wp_pages`, `wp_formal_mechanism` | subnet websites | `12e_whitepapers`, `build/whitepaper_features` |
| X account of the subnet | `x_followers`, `x_posts_30d` | X | `13_x_accounts` |
| Posts by independent commentators | `kol_posts_90d`, `kol_accounts_90d`, `kol_pos_posts_90d`, `kol_neg_posts_90d` | X, two coders, two readers | `14_kol`, `build/kol_polarity` |
| Podcasts | `podcast_episodes_12m` | RSS feeds, YouTube | `15_podcasts` |
| Exploit 26 summit | `exploit26_presented`, `exploit26_mentions_n` | stream.vidaio.io | `16_exploit` |

`codebook.csv` defines every column.

## Replicate

Requirements: Python 3 (run with 3.12; standard library only), `curl`, Chrome, and R (run with 4.6.1) for the `.rds`.

```bash
python -m unittest discover -s tests          # 506 tests, under a second
python collect/run_all.py --list              # the steps in order
python collect/run_all.py                     # runs them; stops where a person has to act
python build/build_dataset.py && python build/validate.py --final
Rscript build/build_rds.R data/final/subnets_wave1_2026-09-30.csv codebook.csv
python build/check_sources.py                 # chain prices against Taostats
python build/check_doc_checklist.py           # documentation checklist against a reader
```

| Key | Used for | Where |
|---|---|---|
| none | all columns with source "chain" | |
| `TAOSTATS_API_KEY` | transfers, stake events, owner and identity history, holder lists | environment or `.env` |
| GitHub token | repository data | `GITHUB_TOKEN`, or a logged-in `gh` |
| `X_BEARER_TOKEN` | X profiles, post counts, posts of approved accounts | environment or `.env` |

Wave 1 needs about 5,600 Taostats calls (at most 15 a minute, so the Taostats steps take about
six hours; tracing miner funding is three quarters of it), about 2,000 GitHub calls, about 2,000
batched requests to the archive node, and about $26 on X ($7 for profiles and counts, $18 for
the 3,497 posts of the nine approved accounts; the X API is prepaid). Every answer is saved,
so a repeated run makes no call twice. Call counts and spending are kept in a ledger with hard
ceilings (`config/snapshot.json`).

Five steps need a person or two independent coders: the double coding of website facts, of two
white paper features and of the commentator posts, the double reading of posts that name a
subnet by its number alone, and the approval of the X accounts whose posts are read.
`config/coding_protocol.md`, `config/polarity_criteria.md`, `config/kol_attribution.md` and
`config/kol_rule.md` give the rules; `config/coder_briefs.md` holds the instructions the
coders of wave 1 received, and `build/coding_material.py` hands out their material.

## Choices that shape the data

The full list with reasons is the decisions log in `PLAN.md`. The ones a user must know:

- **Variables that follow the price by construction are left out**: market capitalisation, pool
  depth, volume, volatility, past returns, staking flows, emission share.
- **"Emissions on" is measured by TAO actually injected**, not by the emission flag. The flag was
  switched on for nearly all subnets on 9 Sep 2026 (79 before, 126 after), while about 90
  subnets receive TAO. Both columns are in the data and both depend on the price. "On" is not
  "material": the amount rises steeply with the price, and at T the 32 largest recipients
  took 94% of all TAO injected. The amounts themselves are left out as price-driven.
- **Burn is missing, not zero, where nothing is paid.** For a subnet that has not started
  emissions the chain stores a burn of 0 by default. Four subnets were in this state at T
  (`startup_mode`); their burn, owner-cut and dividend columns are missing, and no miner counts as paid.
- **Project age** counts from the latest rename that came with another GitHub owner, else from
  registration. A rename by the same team is a rebrand; a wallet or repository move alone is not a new project.
- **Owner trades count for the owner of the day.** 30 subnets changed their owner key in the 90
  days before T. A trade counts for the key that owned the subnet when it was made. For the
  miner columns, every key that owned the subnet since the current project started counts as
  the owner.
- **Miner concentration** pools incentive over the window by wallet. The lineage columns go one
  step further and merge wallets funded from the same address. Operators are counted among
  wallets that earned at least 0.1% of miner pay, so that dust wallets do not pass for
  operators. `_ub` merges on funding links alone and is an upper bound on the number of
  operators; `_best` also merges wallets on one miner IP or paid out of an exchange in one batch.
- **Holder concentration** is a lower and an upper bound. The largest positions are traced and
  valued on chain at T; the untraced remainder (median 0.8%) sets the gap between the bounds.
- **Podcast appearances** count episodes whose title names the subnet. A mention by number alone
  ("Subnet 78") counts only for the project that held the netuid on that day.
- **Website facts** are coded 0 when the saved pages do not show them, and missing when the
  site could not be read.
- **Commentator posts** come from nine X accounts that pass a written rule and that the project
  owner approved before any post was read (`config/kol_rule.md`, `config/kol_accounts.csv`).
  Their original posts of the 90 days before T count (no reposts, no replies) when they name
  the subnet by number, handle or name; a post that names several subnets counts for each.
  Two coders labelled every post-subnet pair. A direction (speaks well, speaks badly) counts
  only if both chose it; everything else is neutral.
- **A subnet number can mean an earlier project.** A post that gives only the number counts
  for the project that held the netuid on the day of the post. A post written later can still
  mean the predecessor, for example when it looks back at a subnet that held the number a
  year earlier. The 125 pairs matched by the number alone
  were therefore read by two readers who had the netuid's history, and a pair was dropped
  where both found that the number stands for another project (`config/kol_attribution.md`).

## Quality checks

- Chain prices equal Taostats' pool history at the same block to at least seven significant
  digits (six subnets, largest difference 0.000000002 TAO; `build/check_sources.py`).
- The chain's burn measure equals the owner share of incentive attributed by this code at the
  58,351 subnet-samples where burn is measured: median difference 0.0000, 95th percentile 0.0003,
  largest 0.024.
- Stake positions valued by this code equal Taostats' stake history at block T to twelve digits
  (three positions).
- Protocol settings at T (commit-reveal, Yuma 3, liquid alpha, mechanisms, maximum UIDs,
  registration block) equal Taostats' subnet history at the same block: 72 of 72 values for
  twelve subnets (`build/check_sources.py`). Against Taostats' latest values, taken 1.3 days
  after T, the five settings agree for all 128 subnets.
- Replication: the chain state at T, read again from the archive node into an empty cache,
  reproduces all 4,096 cells of the state table.
- Double coding of website facts: the coders agreed on 92% to 100% of answers per item
  (Cohen's kappa 0.84 to 1.00) and on 86% of categories (kappa 0.85). Every quote was found on
  the page it cites.
- White paper features: the coders agreed on all 64 answers.
- Commentator posts: the two coders gave the same label to 94% of the 937 post-subnet pairs
  (Cohen's kappa 0.89). 53 of their 57 disagreements are between "speaks well" and neutral,
  and such a pair counts as neutral. The two readers of the 125 pairs matched by the number
  alone gave the same answer in every case: 7 pairs were dropped, 6 because the number meant
  an earlier project and 1 because it was no subnet number.
- Documentation checklist against a reader on a fresh sample of 15 repositories: 90% of answers
  agree. README, licence, contributing guide and docs site agree in all 15; miner guide in 14;
  validator guide in 12; incentive description and hardware requirements in 11 each
  (`build/check_doc_checklist.py`).
- `build/validate.py` checks structure, value ranges, identities between columns and five
  anchor values from independent sources.

## Limits

- 128 observations. Many features, few rows: plan the analysis before looking at results, and
  keep subnets of the same team in the same cross-validation fold (`team_id`).
- A snapshot gives correlates, not causes. Attention and price move each other.
- Website, GitHub star, follower and holder-count columns are as of collection (2 Oct 2026),
  not as of T; the codebook marks them.
- 36 subnets have no X account that could be verified, 24 no GitHub repository, 22 no website.
  14 subnets carry a placeholder identity on chain (`flag_placeholder_identity`).
- `doc_incentive_desc` and `doc_requirements` are conservative: the rule wants a heading or a
  file of its own, and misses what a README states in running text. `doc_score` inherits this.
- Holder concentration is by wallet. A holder who splits a stake across wallets looks
  dispersed, so `holders_top10_share` and `holders_hhi` understate concentration by holder.
- Summit mentions come from speech-recognition transcripts and are a lower bound.
- Lineage clustering cannot attribute wallets funded only from exchanges. At the median subnet
  30% of miner pay goes to such wallets (`miners_unattrib_share_30d`), so operator counts are
  not comparable across subnets without that column. Wallets below 0.1% of miner pay are not
  traced (at most 3.8% of pay in any subnet).
- Two sites could not be read: the security software on the collecting computer blocked them
  (subnets 89 and 103). Their website facts are missing, not 0. A third site (subnet 120)
  answered with a server error on three visits in the morning of 2 Oct 2026 and was read in
  the afternoon of the same day.
- The commentator columns measure nine English-language accounts on X, not "the market's
  attention". Posts deleted before collection are not in the data: X counted 3,552 original
  posts in the window and delivered 3,497. A text posted twice counts twice. Posts that speak
  badly of a subnet are rare (14 of 920 counted pairs, in 8 subnets), so the `kol_neg_*`
  columns vary little. Half of all counted pairs name one of ten subnets; 53 subnets were
  not named at all.

## Who made this

Philipp Koellinger with Claude (Anthropic). Philipp Koellinger is a co-founder of Claims,
subnet 111, which is one of the 128 observations. It went through the same public-data
pipeline as every other subnet.

The category scheme is taken from the Bittensor Subnet Catalog by Christian Roessler (20 Aug 2026).
