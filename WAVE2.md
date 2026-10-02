# Runbook: a follow-up wave

How to collect wave 2 (and any later wave) so that it joins wave 1 into a panel. Written for
whoever runs it, person or agent, without knowledge of how wave 1 was built. Read `README.md`
and the decisions log in `PLAN.md` first.

## What a follow-up wave is

- **Snapshot block:** the snapshot block of the wave before plus 216,000 blocks (30 days of
  blocks). Wave 2: block 9,400,186, expected between 00:00 and 02:00 UTC on 31 Oct 2026. The
  windows of the waves then join without a gap: the lagged window of wave 2 is the feature
  window of wave 1, and `build/build_panel.py` checks that the values agree.
- **Same pipeline, same rules, same coder briefs.** Nothing is redefined between waves. If a
  step fails because the world changed (an API, a page layout), fix the cause, record it in
  the decisions log of `PLAN.md`, and say so in the report.
- **Outcome added to wave 1:** price change to wave 2, and what happened to subnets that lost
  their netuid in between.

## Limits that hold without exception

| Limit | Value |
|---|---|
| Taostats | at most 15 calls a minute; never two collectors at once (the key allows 20 a minute and 20,000 a month and is shared with daily tasks and teammates); the ledger stops at 10,000 per wave |
| X | 25 USD for a follow-up wave, enforced by the ledger; posts are read only for accounts with `approved = yes` in `config/kol_accounts.csv`; the list is the project owner's and is not changed |
| Secrets | keys come from the environment or `.env`; never print, paste or commit them |
| Repository | stays private; commits and pushes to `main` are fine; nothing in `data/raw` or `data/intermediate` is committed; post text and page text never enter the repository |
| Websites | addresses are validated before the browser sees them; warnings of security software and bot checks are not bypassed; documents are read in the sandboxed browser, not downloaded |
| No invented values | a step that cannot get its data leaves the value missing and says why |

## Steps

Run from the repository root. Python: `C:\dev\tools\python\Python312\python.exe` on the
collecting laptop (`/c/dev/tools/python/Python312/python.exe` in Git Bash); R:
`C:\Program Files\R\R-4.6.1\bin\Rscript.exe`. Long steps belong in the background; every
answer is saved, so a step that was interrupted continues where it stopped.

1. `python -m unittest discover -s tests` must pass.
2. `python collect/make_wave_config.py 2` writes `config/snapshot_wave2.json` (it refuses
   while the snapshot block does not exist).
3. `python collect/run_all.py --config snapshot_wave2.json` runs the steps in order and stops
   where a person has to act. After each stop, do what it asks and continue with the command
   it prints. The stops, in order:
   - **Website facts.** `python build/coding_material.py web prepare <folder>` (set
     `SNPRICE_SNAPSHOT=snapshot_wave2.json` for every single command of this wave), start the
     two coders per batch with the brief in `config/coder_briefs.md`, then `web merge`, then
     the run continues with `build/verify_evidence.py`. Items left open get a third reading
     (see the brief file).
   - **White papers.** Same pattern with `whitepaper prepare` and `whitepaper merge`.
   - **Account approval.** Nothing to do if `config/kol_accounts.csv` carries approved
     accounts; continue.
   - **Post labels.** `kol prepare`, two coders, `kol merge`. Only the days since wave 1 are
     read from X; earlier posts and their labels are reused.
   - **Which project a number stands for.** `attribution prepare`, two readers (brief 4 in
     `config/coder_briefs.md`, rule in `config/kol_attribution.md`), `attribution merge`.
     Only pairs matched by the subnet's number alone are read, and only those not read in
     wave 1. `build/kol_polarity.py` stops until every such pair has both readings.
4. `python build/build_dataset.py`, `python build/validate.py --final`,
   `Rscript build/build_rds.R data/final/subnets_wave2_<date>.csv codebook.csv`.
5. `python build/build_panel.py`, then
   `Rscript build/build_rds.R data/final/subnets_panel.csv data/final/subnets_panel_codebook.csv`.
6. `python build/check_sources.py` (the settings check needs Taostats' daily record at the
   snapshot block; if Taostats keeps its record a block earlier or later, say so and move on).
7. Commit, push, and add a line per decision to `PLAN.md`.

## Things that need judgment

- **Subnets that changed since wave 1.** After step `00_snapshot`, compare
  `data/chain/roster_wave2.csv` with `roster_wave1.csv`. For every netuid whose `subnet_uid` or
  name changed, review its row in `config/name_aliases.csv`: the rule (`plain` for a
  distinctive name, `context` for a name that needs a Bittensor term nearby, `strict` for an
  ordinary word, `placeholder` for blank, parked or for-sale identities), the aliases, and the
  team aliases. Write the reason in the note column. Rules are explained at the top of
  `snprice/textmatch.py`.
- **Podcast titles with ordinary-word names.** `15_podcasts` lists weak matches. Decide each
  from the title alone and add it to `data/manual/podcast_weak_matches.csv` with `counts` yes or no.
- **White papers that are not linked plainly.** `12e_whitepapers` reports documents it could
  not find or read. A document address found by hand goes into `config/whitepaper_documents.csv`.
- **Sites that fail.** A server error (HTTP 500 and up) is visited once more later the same
  day. If it still fails it stays `server_error` and its facts stay missing.
- **X credits.** The X API is prepaid. HTTP 402 "credits depleted" means the balance is used
  up: the X steps stop without loss, everything else continues, and the report tells the
  project owner. Wave 1 ran into this on 2 Oct 2026.
- **Screening counts more posts than reading delivers.** X's count includes posts it no longer
  delivers (deleted or withheld); in wave 1 the gap was up to 7% for one account, and reading
  single days again brought nothing back. `14_kol.py posts` records both numbers per account
  and stops only if fewer than 80% of the counted posts are delivered. If that happens, look
  at where the gap lies (which days) before deciding anything.
- **X answers "too many requests" or "service unavailable".** The client waits and asks again
  by itself (up to four times, nothing is charged for failed attempts). If it still stops,
  run the step again later: it continues from the saved answers.

## Known traps

- The chain stores defaults that look like measurements (a burn of 0 before the first payout,
  no `AlphaBurned` entry before the first burn). New chain variables need the same care.
- Owner keys change often. Anything "by the owner" follows the owner of the day.
- Taostats answers with HTTP 429 when two processes share the key. One collector at a time.
- Files with apostrophes or backslashes are written with an editor, not with shell here-documents.
- The security software on the collecting laptop replaces some sites with a warning page
  (subnets 89 and 103 in wave 1). Those sites count as unread.

## Report at the end

State what was collected and what was not, the Taostats calls and X dollars used (from
`data/raw/wave2/ledger.json`), the agreement between coders, the number of subnets evicted
since wave 1, every difference that `build_panel.py` listed, and every decision that was made.
