# Which X accounts count as independent Bittensor commentators

Variables Y19 and Y20 count posts by influential Bittensor accounts that are not run by a
subnet. The list is fixed by rule and then approved by the project owner before any post
is read.

## Candidates

1. The accounts named in the project brief (`source = seed`).
2. The hosts of the six podcasts in `config/podcasts.json` (`source = podcast_host`).

Candidates are listed in `config/kol_candidates.csv`.

## Screening (profile and count requests only, no post is read)

An account passes when all of the following hold. Counts refer to the 90 days before the
snapshot time T and to original posts (reposts and replies excluded).

| Test | Rule | Measured by |
|---|---|---|
| Exists | The handle resolves to a public account | profile lookup |
| Independent | The handle is not the account of a subnet in `data/evidence/links_wave<N>.csv` | links table |
| Commentator | The account belongs to a person or a pseudonym, not to an institution or a show whose episodes the podcast columns already count | by hand, noted in `config/kol_accounts.csv` |
| Volume | At least 30 original posts that contain a Bittensor term | count request |
| Reach | At least 2,000 followers at collection time | profile lookup |

Bittensor terms: `bittensor`, `tao`, `dtao`, `subnet`, `subnets`, `opentensor` (X matches
whole words and ignores case; `$TAO` and `#bittensor` match too).

The Independent test cannot see that a person works for a subnet team or invests in one.
Such cases are noted by hand in `config/kol_accounts.csv` and the project owner decides.

## Change of the rule on 2 October 2026

The rule as first written had a Focus test in place of the Volume test: at least half of
the account's original posts had to contain a Bittensor term, and the account needed at
least 30 original posts of any kind. Screening showed what that test does. It measures how
exclusively an account writes about Bittensor, not how much it writes about it or how many
people read it: it excluded three of the accounts named in the brief and the two largest
audiences among the candidates, while only posts that name a subnet are ever counted. The
project owner chose the Volume test on 2 October 2026, before any post was read and
without reference to prices. The Commentator test was added at the same time; it excludes
the Opentensor Foundation account, which passed the first rule.

`data/evidence/kol_candidates_wave1.csv` shows every candidate's result under the first rule
(`rule_focus`, `rule_activity`, `passes_first_rule`) and under the rule in force
(`rule_volume`, `passes_rule`), so that both lists can be compared:

| | First rule | Rule in force |
|---|---|---|
| Accounts | TaoOutsider, TAOTemplar, gordonfrayne, KeithSingery, ShizzyUnchained, opentensor | TaoOutsider, TAOTemplar, gordonfrayne, KeithSingery, ShizzyUnchained, tylerdurdeth, JesusMartinez, markjeffrey, SiamKidd |
| Original posts in 90 days | 1,291 | 3,552 |

## Approval

`collect/14_kol.py candidates` writes the screening table. The project owner approves the
accounts in `config/kol_accounts.csv` (`approved = yes` and the date). The X client refuses
to read posts of any account that is not on that list.
