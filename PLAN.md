# PLAN: Bittensor subnet price-correlates dataset

**Status:** IN PROGRESS
**Created:** 2026-10-02
**Last updated:** 2026-10-02
**Owner:** Philipp Koellinger (decisions), Claude (build)

## Goal

A dataset with one row per Bittensor subnet for regressions with the alpha token price as dependent variable: main correlates and the best achievable out-of-sample prediction. Deliverables: a CSV, an R `.rds` with variable labels, a codebook, and the collection code for every variable, so that others can replicate it. Done when wave 1 (snapshot 30 Sep 2026) passes `build/validate.py` and wave 2 (30 Oct 2026) has added forward outcomes.

## Constraints

- **Deadline:** wave 1 frozen before 30 Oct 2026; wave 2 on or after 31 Oct 2026.
- **Budget:** X API $75 in total ($50 wave 1, $25 wave 2); Taostats at most 10,000 calls per wave and 15 calls a minute.
- **Dependencies:** Taostats API key, X bearer token, GitHub token, the public archive node; optional YouTube API key.
- **Non-goals:** the regression and cross-validation analysis itself (separate plan); Discord data; graded quality ratings; variables that respond mechanically to the token price.
- **Hard rule:** no invented data. Every value comes from a script reading an API response, or from a coding table with evidence. Missing stays NA.

## Approach

All on-chain quantities are read from the public archive node at one pinned block (T = block 9,184,186, end of 30 Sep 2026 UTC) and at the daily snapshot blocks of the window, so those columns can be reproduced without any API key. Indexed data (transfers, stake events, metagraph history) come from Taostats; repository data from the GitHub API; attention data from the X API, podcast feeds and the Exploit 26 talk archive. Web facts are coded by two independent coders under a fixed search protocol, with evidence checked by script. One script per variable block writes an intermediate table; `build/build_dataset.py` merges them.

Because only 92 to 128 subnets are usable, the design adds time: features for September, lagged copies for August, and a second wave 30 days later that supplies forward outcomes.

### Alternatives Considered

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| Snapshot + lagged features + follow-up wave | Time order; a real forward test; start of a panel | Second run needed | **Chosen** |
| Single snapshot only | Simplest | Only same-day correlates; price feeds back into most features | Rejected: circular |
| Taostats "latest" values for chain state | Few calls | Not pinned to a block, not reproducible | Rejected: archive node instead |
| Likert quality ratings by an LLM | Richer signal | Not reproducible, noisy | Rejected by Philipp: checklists only |

## Phases

### Phase 0: Core library, test-first — IN PROGRESS

**Goal:** shared code whose failure modes are tested before any long data pull.

- [x] Repository scaffold
- [x] `snprice/metrics.py`: pooled shares, HHI, holder bounds
- [x] `snprice/chain.py`: storage keys, decoding, cached archive reads
- [x] `snprice/fetch.py`: throttled Taostats client, ledger, "no data is an error, never zero"
- [x] `snprice/events.py`: owner trade netting, basket flows, identity changes, windows
- [x] `snprice/lineage.py`: funding-lineage clustering
- [x] `snprice/textmatch.py`: subnet mention matching
- [x] `snprice/xapi.py`: X client with spend ledger and approval gate
- [ ] `collect/00_snapshot.py`: T, daily blocks, roster, identities
- [ ] Measurement: can miner incentive be read from the archive at 900-block resolution within three hours?

**Exit criteria:** tests pass; roster has 128 rows; chain price equals the Taostats pool price at the pool-history blocks.

### Phase 1: Perishable and on-chain data — NOT STARTED

**Goal:** everything that only exists as "latest", then the pinned chain state and the Taostats pulls.
**Depends on:** Phase 0

- [ ] Holder candidates, GitHub current state, site snapshots, X profile lookups
- [ ] `01_price`, `02_chain_state` (archive node)
- [ ] `03_history_events` to `09_baskets` (single Taostats worker, resumable)

**Exit criteria:** one intermediate table per block; cross-checks pass; no unexplained NA.

### Phase 2: Links, GitHub windows, web facts, category — NOT STARTED

**Depends on:** Phase 1

- [ ] `10_links`, `11_github` (docs checklist validated by hand on 15 repos)
- [ ] `12_web`, `17_category_team`: two coders per item, `build/verify_evidence.py` passes

**Exit criteria:** every coded "yes" verified against a saved snapshot; agreement reported.

### Phase 3: Attention — NOT STARTED

**Depends on:** Phase 1

- [ ] `13_x_accounts`: profiles and post counts
- [ ] `14_kol`: account list by written rule, approved by Philipp before any post is read
- [ ] `15_podcasts`, `16_exploit`

**Exit criteria:** X ledger at or under $50; evidence tables complete.

### Phase 4: Build, validate, freeze, document — NOT STARTED

**Depends on:** Phases 1 to 3

- [ ] `build_dataset.py`, `validate.py`, `build_rds.R`, codebook, README
- [ ] Tag and hash wave 1

**Exit criteria:** validation passes; Philipp has reviewed the dataset.

### Phase 5: Wave 2 — NOT STARTED

**Depends on:** Phase 4, date ≥ 31 Oct 2026

- [ ] `collect/run_all.py --snapshot-date 2026-10-30`
- [ ] `build/build_panel.py`: forward outcomes, evictions, consistency check against wave 1

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Rate-limited Taostats response read as zero | High | Med | Client raises on missing data; tests |
| Taostats monthly quota exhausted | Med | Med | Ledger ceiling, 15 calls a minute |
| Lineage merges strangers through exchange wallets | High | Med | Lower-bound and best lenses only; unattributable share reported |
| Daily snapshots miss intra-day winner changes | Med | High | Chain grid every 900 blocks if affordable |
| Runtime upgrades inside the window | Med | High | Decoding per block; absent item = NA |
| Coding of web facts invents a fact | High | Low | Two coders, evidence checked by script |
| Redistribution terms (X, Taostats) | Med | Low | Only aggregates, IDs and URLs are committed |

## Key Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-10-01 | Variable set fixed by Philipp; all proposed redefinitions accepted | Lean set because N ≤ 128 |
| 2026-10-01 | Exclude variables that respond mechanically to price (market cap, pool depth, volume, volatility, past returns, net staking flow, root proportion, emission share, staked share of alpha) | A same-day cross-section would otherwise be partly tautological |
| 2026-10-01 | Discord dropped | Channel activity cannot be read without a bot in the server |
| 2026-10-01 | No Likert ratings; documentation and white paper measured by checklists and objective features | Reproducibility |
| 2026-10-01 | Timing: snapshot + lagged features + wave 2 after 30 days | Time order and a forward test |
| 2026-10-01 | X budget $75; podcasts: Novelty Search, Hash Rate, Ventura Labs, Revenue Search, TAO Pod, Bittensor Guru | |
| 2026-10-02 | T = block 9,184,186 (end of 30 Sep 2026 UTC) | Taostats' daily snapshot block; clean calendar windows |
| 2026-10-02 | Owner buying and basket buying kept but labelled `mechanical (flow)`; lagged versions built | They move the price in the same window by construction |
| 2026-10-02 | "Funds invested" = active basket trades; holdings only as description | Holdings are mostly passive accrual and index rules |
| 2026-10-02 | Mention polarity: two coders, written criteria, both must agree | Polarity cannot be measured without classification |
| 2026-10-02 | Project age ignores pure owner-key swaps | A swap can be a wallet migration by the same team |
| 2026-10-02 | Dropped for lack of variance: leased subnet (0 of 128), collateral flag (1 of 128), subnets per owner key (always 1) | |
| 2026-10-02 | Miner shares are pooled over the window, not averaged per day | Weighs each day by what was actually paid out |

## Open Questions

- [ ] Monthly call allowance of the Taostats plan (sets the ledger ceiling).
- [ ] Influencer account list (to be approved before any post is read).
- [ ] YouTube API key, or collection of the YouTube-only shows through the browser.
- [ ] Wave 2: scheduled run or manual trigger.
- [ ] Taostats terms on publishing derived data, before the repository goes public.
