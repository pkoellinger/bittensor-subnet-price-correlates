# Data folders of the pipeline

| Folder | Content | In git |
|---|---|---|
| `chain/` | Small tables read from the public archive node at pinned blocks. Reproducible without any API key | yes |
| `evidence/` | Why a coded value is what it is: episode URLs, talk mapping, post IDs with labels and readings, link sources, snapshot hashes | yes |
| `manual/` | Answers of the two coders and the two readers per wave, with evidence URL and quote per website fact; third readings with reasons | yes |

The dataset itself (one CSV and one `.rds` per wave) and `codebook.csv` live in the project's
`Input/` folder. The API response caches (Taostats, GitHub, X, web pages), the call ledger and
the per-block tables with wallet-level rows live in `Temp/collection-cache/` (`raw/` and
`intermediate/`), which is not synced: they contain wallet-level rows and third-party API
responses, and the scripts in `collect/` regenerate them. Post text from X is never committed;
only post IDs are. `Temp/collection-cache/` must be kept until the follow-up wave has run: the
wave reuses the saved posts and chain reads instead of fetching them again.
