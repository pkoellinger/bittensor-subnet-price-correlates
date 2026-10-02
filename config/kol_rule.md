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
| Focus | At least half of its original posts contain a Bittensor term | two count requests |
| Activity | At least 30 original posts | count request |
| Reach | At least 2,000 followers at collection time | profile lookup |

Bittensor terms: `bittensor`, `tao`, `dtao`, `subnet`, `subnets`, `opentensor` (X matches
whole words and ignores case; `$TAO` and `#bittensor` match too).

The Independent test cannot see that a person works for a subnet team. Such cases are
noted by hand in `config/kol_accounts.csv` and the project owner decides.

## Approval

`collect/14_kol.py candidates` writes the screening table. The project owner copies the
accounts to keep into `config/kol_accounts.csv` with `approved = yes` and the approval
date. The X client refuses to read posts of any account that is not on that list.
