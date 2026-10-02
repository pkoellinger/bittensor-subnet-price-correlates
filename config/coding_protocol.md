# Coding protocol for facts that no API reports

Six facts per subnet are read off the subnet's own public material: website pages, the
README of its main repository, and its on-chain description. Two coders work independently
from the same saved material. Coders never see prices, market data or each other's answers.

## Material

One dossier per subnet, built by `collect/12b_dossiers.py` from saved snapshots:

- on-chain name and description at T
- the text of the home page and of up to eight further pages of the same site
  (`collect/12_web.py`), as passages around fixed keywords
- the start of the README of the main repository, and passages around the same keywords
- links to documents found on those pages, and files in the repository that look like documents
- names of the owner's public repositories

A coder uses the dossier only. No web search, no outside knowledge. What the dossier does not
show is coded 0, with `searched` listing the pages that were available.

## Items

Every item is 0 or 1. A 1 needs evidence: the address of the page (or `README`, or
`onchain`) and a verbatim quote of at most 200 characters that appears on it.

| Item | Code 1 when | Code 0 when (examples) |
|---|---|---|
| `whitepaper_available` | The project offers a standalone document about its own design that it calls a white paper, litepaper, yellow paper or technical paper, or presents a research paper by its own team as the description of its method. | Only docs pages or a README. The Bittensor white paper. Papers by others cited as sources. Benchmark reports, pitch decks, audits, release plans. |
| `api_public` | The project documents an interface that people outside the subnet can call to use its output or product: API reference, API keys, SDK, an OpenAI-compatible endpoint. | An interface only for miners or validators to take part in the subnet. An API that is announced but not documented. Use of other projects' APIs. |
| `mcp_server` | The project offers an MCP (Model Context Protocol) server for its own product or data, with instructions or a repository. | MCP is the subject of the subnet's work without a server of its own being offered. MCP servers of other projects. |
| `team_named` | At least one founder or team member is named with first and last name. | Only pseudonyms or handles. Only a company name. Names of advisers, investors or partners. |
| `product_live` | Someone who is neither miner nor validator can use a product or service of the project today: sign up or log in to an app, get an API key, use a playground, download software, buy a service. | Waitlist, "coming soon", "request a demo". Only dashboards of subnet statistics, leaderboards or explorers. Only instructions for miners and validators. |

`category`: the one category of `config/category_codebook.md` that best describes what the
subnet produces, judged from its own description. Evidence: a quote that states the product.

## Output

One JSON object per subnet:

```json
{"netuid": 64,
 "whitepaper_available": {"value": 0, "url": null, "quote": null},
 "whitepaper_url": null,
 "api_public": {"value": 1, "url": "https://example.ai/docs", "quote": "Create an API key and call the endpoint"},
 "mcp_server": {"value": 0, "url": null, "quote": null},
 "team_named": {"value": 0, "url": null, "quote": null},
 "product_live": {"value": 1, "url": "https://example.ai", "quote": "Sign up"},
 "category": {"value": "AI Inference & Model Serving", "url": "onchain", "quote": "serverless AI compute"},
 "searched": ["https://example.ai", "https://example.ai/docs", "README"],
 "notes": ""}
```

`whitepaper_url` is the address of the document when `whitepaper_available` is 1.

A dossier without any material (no site, no README, no description) gets 0 on every item,
category `Miscellaneous`, and the note `no material`.

## White paper features

For each subnet with `whitepaper_available = 1` the document is read by
`collect/12e_whitepapers.py`. Two features follow from fixed rules:

- `wp_pages`: pages of the PDF. Missing when the document is a web page or a Markdown file.
- `wp_references`: the document has a heading "References" or "Bibliography".

Two features are coded by two independent coders from an excerpt (the first 1,500 characters
and the lines that look like formulas, each with its neighbouring lines):

| Item | Code 1 when | Code 0 when (examples) |
|---|---|---|
| `wp_named_authors` | The document names at least one person as its author, with first and last name. | Only a company, team or subnet name ("Minos Team", "BitMind", "Subnet Contributors"). "Anonymous". No byline. |
| `wp_formal_mechanism` | The document states how something in the subnet is computed as a formula with variables: a score, a reward, a selection or acceptance rule, a verification check, or the core method that miners run. | Only settings ("temperature = 0.9", "max_length = 14336"), code assignments, table rows, or prose. |

Output per subnet: `{"netuid": 3, "wp_named_authors": {"value": 1, "quote": "..."}, "wp_formal_mechanism": {"value": 1, "quote": "..."}}`,
where the quote is copied from the excerpt. Disagreements are settled by a third reading of
the full text.

A white paper that cannot be read (login gate, encrypted viewer) keeps `whitepaper_available = 1`
and has missing features. A white paper whose link is dead (HTTP 404) counts as not available.

## After coding

1. `build/verify_evidence.py` checks every quote against the saved page. A quote that is not
   found turns the answer into "unverified", which counts as a disagreement.
2. Where the two coders agree, that value stands.
3. Where they disagree, a third reading with both answers and the evidence decides. If the
   evidence does not settle it, the value is missing.
4. Agreement between the two coders is reported per item (share agreeing and Cohen's kappa).
5. Where the site could not be read (a bot check, or a warning shown by the security software
   on the collecting computer), a "no" is recorded as missing. A "yes" backed by the README stands.

## Clarifications made in the third reading (wave 1)

The coders split on one point of interpretation, and the third reading settled it as follows.
The rule applies to later waves as written here.

- `product_live`: a released model, dataset, design or open-source tool that anyone can
  download counts as a product an outsider can use (the protocol's "download software").
  Applied to subnets 3, 52, 74, 81 and 108.
- `product_live`: access by invitation only, or through a request form, counts as a waitlist.
  Applied to subnets 54 and 126.
- `whitepaper_available`: a document that the project itself offers as its white paper counts
  even if its content is a benchmark report (subnet 18); a white paper that is cited but not
  offered does not (subnet 99).

All third readings with their reasons are in `data/manual/web_coding_third_reading.csv`.

## Result of wave 1

| Item | Coders agree | Cohen's kappa | Yes (final) |
|---|---|---|---|
| `whitepaper_available` | 98% | 0.96 | 35 |
| `api_public` | 98% | 0.96 | 34 |
| `mcp_server` | 100% | 1.00 | 11 |
| `team_named` | 100% | 1.00 | 18 |
| `product_live` | 92% | 0.84 | 58 |
| `category` (16 categories) | 86% | 0.85 | |

Every one of the quotes given for a "yes" was found on the page it cites. Two subnets (89, 103)
have missing values because their sites could not be read.
