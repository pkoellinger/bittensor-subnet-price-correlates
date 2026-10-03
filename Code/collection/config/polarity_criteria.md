# Labels for posts that name a subnet

Variables `kol_*` count original posts by the approved accounts (`config/kol_accounts.csv`)
that name a subnet. `collect/14_kol.py posts` finds the subnets by rule. Two coders then
read each post and give one label per post and subnet. They work independently and see
neither prices nor each other's answers.

The examples use an invented subnet, Acme (SN900).

## Labels

| Label | Give it when the post | Examples |
|---|---|---|
| `positive` | speaks well of the subnet: its product, team, progress or token; says it holds, buys or recommends it; calls it undervalued | "Acme keeps shipping, best team on the network"; "added to my SN900 bag" |
| `negative` | speaks badly of the subnet: product, team, conduct or token; says it sells or avoids it; warns about it; calls it overvalued | "SN900 has no users, the emissions carry it"; "sold my Acme today" |
| `neutral` | names the subnet without taking a side: news, numbers, lists, questions, announcements passed on, praise and criticism in balance | "SN900 moved to rank 3 by emissions"; "Acme and two other teams present tomorrow" |
| `not_about` | does not refer to the subnet at all: the matched word is used in its ordinary sense, or stands for something else | "the acme of this cycle" matched to Acme |

## Rules

1. Judge only what the post itself says about this subnet. A post that praises one subnet and
   attacks another gets `positive` for the first and `negative` for the second.
2. The stance must be the author's. A quoted or reported opinion of others is `neutral`
   unless the author adopts it.
3. A price going up or down is not a stance. "SN900 is up 20%" is `neutral`; "SN900 is up 20%
   and still cheap" is `positive`.
4. Irony counts as what it means. If the meaning is unclear, the label is `neutral`.
5. A list or ranking is `neutral` for every subnet on it, unless the post says the list is a
   recommendation ("my top picks", "subnets to avoid").
6. When in doubt between a direction and `neutral`, choose `neutral`.

## Output

One line per post and subnet: `{"post_id": "...", "netuid": 900, "label": "positive"}`,
collected in `data/manual/kol_polarity_wave<N>_coder_A.json` and `..._coder_B.json`. The files hold
post IDs and labels only. Post text is not stored in the repository.

## How the labels are used (`build/kol_polarity.py`, `snprice.kol.mention_decision`)

- A subnet found by number, handle or distinctive name counts unless both coders answer
  `not_about`. A subnet found only through an ordinary word used as a name counts only if
  neither coder answers `not_about`.
- A post counts as positive or negative only if both coders chose that direction.
  Everything else that counts is neutral.
- Agreement between the coders is reported as the share of equal labels and Cohen's kappa.
