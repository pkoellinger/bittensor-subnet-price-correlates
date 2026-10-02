# PLAN: Bittensor subnet price-correlates dataset

**Status:** IN PROGRESS (wave 1 collected except commentator posts, which wait for approval of the account list)
**Created:** 2026-10-02
**Last updated:** 2026-10-02
**Owner:** Philipp Koellinger (decisions), Claude (build)

## Goal

A dataset with one row per Bittensor subnet for regressions with the alpha token price as dependent variable: main correlates and the best achievable out-of-sample prediction. Deliverables: a CSV, an R `.rds` with variable labels, a codebook, and the collection code for every variable, so that others can replicate it. Done when wave 1 (snapshot 30 Sep 2026) passes `build/validate.py --final` and wave 2 (30 Oct 2026) has added forward outcomes.

## Constraints

- **Deadline:** wave 1 frozen before 30 Oct 2026; wave 2 on or after 31 Oct 2026.
- **Budget:** X API $75 in total ($50 wave 1, $25 wave 2); Taostats at most 10,000 calls per wave and 15 calls a minute.
- **Dependencies:** Taostats API key, X bearer token, GitHub token, the public archive node, Chrome.
- **Non-goals:** the regression and cross-validation analysis itself (separate plan); Discord data; graded quality ratings; variables that respond mechanically to the token price.
- **Hard rule:** no invented data. Every value comes from a script reading an API response, or from a coding table with evidence. Missing stays NA.

## Approach

All on-chain quantities are read from a public archive node at one pinned block (T = block 9,184,186, end of 30 Sep 2026 UTC) and at sample blocks every 900 blocks through the 30 days before T and the 30 days before that, so those columns can be reproduced without any API key. Indexed data (transfers, stake events, owner and identity history) come from Taostats; repository data from the GitHub API; attention data from the X API, podcast feeds, YouTube pages and the Exploit 26 session archive. Facts that no API reports are read off the subnets' own websites by two independent coders, with every "yes" checked by script against a saved page. One script per variable block writes an intermediate table; `build/build_dataset.py` joins them.

Because only 128 subnets exist, the design adds time: features for September, lagged copies for August, and a second wave 30 days later that supplies forward outcomes.

### Alternatives Considered

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| Snapshot + lagged features + follow-up wave | Time order; a real forward test; start of a panel | Second run needed | **Chosen** |
| Single snapshot only | Simplest | Only same-day correlates; price feeds back into most features | Rejected: circular |
| Taostats "latest" values for chain state | Few calls | Not pinned to a block, not reproducible | Rejected: archive node instead |
| Likert quality ratings by an LLM | Richer signal | Not reproducible, noisy | Rejected by Philipp: checklists only |

## Phases

### Phase 0: Core library, test-first — DONE

- [x] Repository scaffold; shared library `snprice/` with 448 unit tests (`python -m unittest discover -s tests`)
- [x] Measurement: miner incentive and the wallet behind every paid UID can be read from the chain at 900-block resolution in about one hour

### Phase 1: Chain and Taostats data — DONE except lineage (running)

- [x] `00_snapshot`, `01_chain_grid`, `02_chain_state`, `05_aggregate_grid` (chain only)
- [x] `03_history_events`, `04_registrations`, `07_holders`, `08_owner_trades`, `09_baskets`, `18_tao_usd`
- [ ] `06_lineage` (about 4,200 Taostats calls; running)

### Phase 2: Links, GitHub, websites, coded facts — DONE

- [x] `10_links`, `11_github`; documentation checklist checked by a reader on two samples of 15 repositories (`build/check_doc_checklist.py`)
- [x] `12_web` (382 pages of 106 sites), `12b_dossiers`, double coding of five facts and the category, `build/verify_evidence.py`
- [x] `12e_whitepapers`: 32 of 35 white papers read; two features by rule, two by double coding

### Phase 3: Attention — DONE except commentator posts

- [x] `13_x_accounts` (92 subnets with an X account), `12c_site_handles`, `12d_x_handle_guess`
- [x] `15_podcasts` (219 episodes of six shows), `16_exploit` (51 sessions)
- [x] `14_kol.py candidates`: 15 candidate accounts screened without reading any post
- [x] Written and tested without reading a post: `14_kol.py posts`, `config/polarity_criteria.md`, `build/kol_polarity.py`
- [ ] **Waiting for Philipp:** approval of the account list in `config/kol_accounts.csv` (all 15 candidates are listed with a recommendation; `approved` is empty). Then: run `14_kol.py posts`, two coders label the pairs, run `build/kol_polarity.py`, add the ten `kol_*` columns to the codebook

### Phase 4: Build, validate, freeze, document — IN PROGRESS

- [x] `codebook.csv`, `build/build_dataset.py`, `build/validate.py`, `build/build_rds.R`, README
- [x] Cross-checks: `build/check_sources.py` (chain prices against Taostats), `build/check_doc_checklist.py`
- [ ] Final build with lineage and commentator columns; tag and hash wave 1

### Phase 5: Wave 2 — NOT STARTED

**Depends on:** Phase 4, date ≥ 31 Oct 2026

- [ ] `python collect/find_block.py 2026-10-30`, write `config/snapshot_wave2.json`, `python collect/run_all.py --config snapshot_wave2.json`
- [ ] `build/build_panel.py`: long format keyed by `subnet_uid` and wave, forward outcomes (`logret_fwd30`, `evicted_fwd30`), check that wave 2's lagged columns equal wave 1's values

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Rate-limited Taostats response read as zero | High | Med | Client raises on missing data; tests |
| Taostats monthly quota exhausted | Med | Med | Ledger ceiling, 15 calls a minute; wave 1 uses about 5,800 calls |
| Lineage merges strangers through exchange wallets | High | Med | Lower-bound and best lenses only; unattributable share reported |
| Runtime upgrades inside the window | Med | High | Decoding per block; absent item = NA |
| Coding of web facts invents a fact | High | Low | Two coders, every quote checked by script against the saved page |
| A site is down or blocked on the day of collection | Med | Med | Status recorded; second visit; coded facts missing where the site could not be read |
| YouTube or site layouts change before wave 2 | Med | Med | Parsers raise instead of returning nothing |
| Redistribution terms (X, Taostats) | Med | Low | Only aggregates, IDs and URLs are committed; review before the repository goes public |

## Key Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-10-01 | Variable set fixed by Philipp; all proposed redefinitions accepted | Lean set because N ≤ 128 |
| 2026-10-01 | Exclude variables that respond mechanically to price (market cap, pool depth, volume, volatility, past returns, net staking flow, root proportion, emission share, staked share of alpha) | A same-day cross-section would otherwise be partly tautological |
| 2026-10-01 | Discord dropped | Channel activity cannot be read without a bot in the server |
| 2026-10-01 | No Likert ratings; documentation and white paper measured by checklists and objective features | Reproducibility |
| 2026-10-01 | Timing: snapshot + lagged features + wave 2 after 30 days | Time order and a forward test |
| 2026-10-01 | X budget $75; podcasts: Novelty Search, Hash Rate, Ventura Labs, Revenue Search, TAO Pod, Bittensor Guru | |
| 2026-10-02 | T = block 9,184,186 (end of 30 Sep 2026 UTC) | Last block of the day; `collect/find_block.py` returns it |
| 2026-10-02 | Owner buying and basket buying kept but labelled `mechanical (flow)`; lagged versions built | They move the price in the same window by construction |
| 2026-10-02 | "Funds invested" = active basket trades; holdings only as description | Holdings are mostly passive accrual and index rules |
| 2026-10-02 | Dropped for lack of variance: leased subnet (0 of 128), collateral flag (1 of 128), subnets per owner key (always 1), basket trades in August (trading began 21 Sep), TAO Pod column (no title names a subnet) | |
| 2026-10-02 | Miner shares are pooled over the window, not averaged per day | Weighs each day by what was actually paid out |
| 2026-10-02 | Windows are defined in blocks counted back from T (30 days = 216,000 blocks) and sampled every 900 blocks | Keyless and exactly reproducible |
| 2026-10-02 | Historical chain state is read from OnFinality's public Bittensor endpoint; the Opentensor archive is the fallback and cross-check | Measured: the Opentensor archive sustains about 540 keys a minute, OnFinality answers 1,280 keys in about a second; both returned identical values at T |
| 2026-10-02 | Miner incentive, the wallet behind every paid UID, registration cost, hyperparameters, validator structure, locks and burned alpha all come from the chain, not from Taostats | Saves about 2,500 Taostats calls and gives eight samples a day |
| 2026-10-02 | **Burn is missing, not 0, where the chain's value is not a measurement**: before a subnet's first payout (first emission block plus one tempo) and at samples where no UID holds incentive. Incentive held before the first payout pays nobody. Replaces the first rule of the same day, which kept the chain's 0 and only flagged startup mode | The chain stores 0 by default in both cases. The flag at T cannot repair window means of subnets that started emissions inside the window (subnet 36: 0.39 with the default zeros, 0.55 without). Four subnets were in startup mode at T. The raw chain values of every sample stay in `data/chain/grid_wave1.csv`. At the 58,351 measured samples the chain value equals the owner share of incentive attributed here (95th percentile of the difference 0.0003, largest 0.024) |
| 2026-10-02 | Owner cut and dividend shares follow the same rule: the owner cut is counted from the first emission block, and dividend shares before the first payout are left out | Before, the owner cut of subnets that started inside the window was counted from registration (subnet 36: 38,879 alpha instead of 27,446), and startup subnets showed a dividend share of 0 |
| 2026-10-02 | A subnet without an `AlphaBurned` entry has burned nothing (0), as long as other subnets have entries at that block | The chain creates the entry at the first burn; four young subnets had a missing value instead of 0 |
| 2026-10-02 | E-mail mailbox names from on-chain identities are not republished (domain only) | Privacy |
| 2026-10-02 | **Y15 is measured by TAO actually injected** (`tao_emission_on_share_30d`: share of samples with `SubnetTaoInEmission` above zero). The emission flag is kept as a second column | The flag was switched on for nearly all subnets on 9 Sep 2026 (79 on before, 126 after) while only about 90 subnets receive TAO. The flag no longer says who is funded. Both columns are marked mechanical (gate) |
| 2026-10-02 | **Stake positions are valued as the runtime does**: old share map first, then the new one, with pool epochs (`snprice.chain.position_alpha`) | The first version read only the new map and valued about 10% of staked alpha (up to 48% in one subnet) at zero. Checked against Taostats stake history at block T to twelve digits |
| 2026-10-02 | Holder shares are taken over `TotalAlphaStaked` (all alpha staked on hotkeys), less the basket custody wallet | Exact partition of positions; within 1% of AlphaOut − burned − protocol-owned |
| 2026-10-02 | **Project start = the latest rename that came with another GitHub owner**, else registration. A rename with the same GitHub owner is a rebrand; a repository or site move alone is housekeeping | The first rule reset the clock on any identity edit: Chutes looked 245 days old because it moved GitHub organisation. Claims starts on 15 Jun 2026 as in the team vault |
| 2026-10-02 | UTC timestamps are converted without going through local time (`snprice.timeutil`) | The first version was one hour off for dates in daylight saving time |
| 2026-10-02 | The spending ledger is locked while a collector books | Two collectors running at once could overwrite each other's bookings |
| 2026-10-02 | Lagged window values are missing, not zero, for subnets registered after the window | NA is not zero |
| 2026-10-02 | Exploit 26: "presented" = a listed speaker's affiliation is the subnet, an alias or its team; moderators do not count. Four labels were resolved by hand with evidence (config/name_aliases.csv): Vidiao (agenda typo for Vidaio), Khala Research (subnet 112), Quantum Rings (subnets 48 and 63) | The summit agenda lists affiliations, not netuids |
| 2026-10-02 | Transcript matching reads subnet numbers written as words ("subnet forty-four") and treats ordinary-word names as mentions only with the number or next to the word "subnet" in the name's own capitalisation | Speech recognition spells numbers out; "the actual subnet" is not subnet 95 |
| 2026-10-02 | Podcasts: an episode counts when its **title** names the subnet; descriptions are not used. Sources: three audio feeds and three YouTube channels read without a key. Within a show, episodes on the same subnet less than 14 days apart count once | Descriptions carry sponsor lines and passing mentions; a stream and its edited re-upload are one appearance. No YouTube API key was needed |
| 2026-10-02 | Novelty Search = the whole Opentensor Foundation channel | Its episodes are streamed there and re-uploaded as edited videos, often without the show's name |
| 2026-10-02 | Website facts: where a site could not be read (bot check, a warning of the security software on the collecting computer, or a server error on the day) a "no" is recorded as missing | A "no" means nothing if the page was never shown |
| 2026-10-02 | A server error (HTTP 500 and up) is its own status, `server_error`, with `website_live` missing; `dead` is kept for no answer, paused hosting and pages that are gone | A server error is a failure of the day. Subnet 120 (Affine) answered 502 on three visits; counting it as dead put five false zeros on one of the largest subnets |
| 2026-10-02 | Mailbox names are removed from stored evidence quotes (`@domain` only) and quotes are compared with the pages on that basis | Same rule as for on-chain contact fields: e-mail addresses of persons are not republished |
| 2026-10-02 | `product_live`: a released model, dataset, design or open-source tool that anyone can download counts; invitation-only access does not | Clarification made in the third reading, where the two coders split (see config/coding_protocol.md) |
| 2026-10-02 | A white paper whose link is dead (HTTP 404) counts as not available; one that cannot be read (login gate, encrypted viewer) counts as available with missing features | A visitor cannot open the first, and can open the second |
| 2026-10-02 | White paper PDFs are read inside a headless browser with pdf.js; only the extracted text is saved | No files from subnet sites are downloaded to disk |
| 2026-10-02 | Categories: the 16 categories of the catalog of 20 Aug 2026; first coder is the catalog where the subnet kept its name, second coder reads the dossier; 8 groups fixed before prices were compared across categories | |
| 2026-10-02 | X handles: Taostats identity, contact field, GitHub owner profile, the only X profile linked on the subnet's home page, then guessed handles accepted only if the profile links the subnet's site or names it with its number | On-chain identity has no handle field; 95 of 114 named subnets now have a handle |
| 2026-10-02 | Commentator accounts are screened by a written rule from profile and count requests only; reading all original posts of all 14 existing candidates for 90 days would cost about $21 | Fits the $50 budget, so the 90-day window can be used |
| 2026-10-02 | Documentation checklist: rules corrected once after the first hand check (15 repositories), then left as they are. A second sample of 15 repositories, drawn afterwards, agrees on 90% of answers: all 15 on README, licence, contributing guide and docs site, 14 on the miner guide, 12 on the validator guide, 11 each on incentive description and hardware requirements | Tuning the rules on the second sample would leave no out-of-sample check. Ten of the twelve disagreements are a "no" of the rule where the reader said yes, mostly for information given in running text: the two weak items are conservative |

## Open Questions

- [ ] **Account list for Y19 and Y20** (`config/kol_accounts.csv`): which of the screened accounts to read. No post is read before this is approved.
- [ ] Monthly call allowance of the Taostats plan (wave 1 uses about 5,800 calls; the plan page lists 20,000 credits a month).
- [ ] Wave 2: scheduled run or manual trigger on or after 31 Oct 2026.
- [ ] Terms of Taostats and X on publishing derived data, before the repository goes public.
- [ ] Before the repository goes public: Christian Roessler's consent to naming his subnet catalog and to publishing the category table taken from it (`data/manual/catalog_categories_2026-08-20.csv`).
- [ ] Subnet 120 (Affine): the site answered HTTP 502 on three visits on 2 Oct 2026 (06:19 to 07:36 UTC). Visit again at the final build; if it answers, read it and code its five website facts.
