# Bittensor subnet price correlates

A dataset with one row per Bittensor subnet, built for regressions with the subnet's alpha token price as dependent variable.

**Status: wave 1 collection in progress.** Snapshot: end of 30 Sep 2026 UTC (block 9,184,186). The dataset, codebook and full replication notes will be added here when wave 1 is complete. See [PLAN.md](PLAN.md) for the design, the decisions taken and the open points.

## Layout

```
snprice/    shared library (chain reads, API clients, measures)
collect/    one script per variable block
build/      merge, validation, R export
config/     snapshot definition, coding rules
data/       final dataset, chain tables, evidence (see data/README.md)
tests/      python -m unittest discover -s tests
```

## Principles

- On-chain quantities are read from the public archive node at a pinned block and can be reproduced without an API key.
- No invented data: every value comes from a script reading an API response or from a coding table with evidence. Missing values stay missing.
- Variables that respond mechanically to the token price are excluded.

Authors: Philipp Koellinger and collaborators. Philipp Koellinger is a founder of Claims (subnet 111); that subnet is collected through the same public-only pipeline as every other subnet.
