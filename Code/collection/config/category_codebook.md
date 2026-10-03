# Product categories

The sixteen categories are those of the Bittensor Subnet Catalog (Christian Roessler,
20 August 2026), which gives every subnet one primary category: the main commodity or
service the subnet is meant to produce. The one-line descriptions below were written for
this project so that a coder can apply the categories without the catalog.

| Category | The subnet mainly produces |
|---|---|
| Compute, Storage & Network Infrastructure | raw computing power, GPU rental, storage, bandwidth, confidential computing |
| AI Inference & Model Serving | answers from hosted AI models: inference endpoints, model routing, verified inference |
| AI Training & Model Improvement | trained or fine-tuned models, training runs, model competitions |
| AI Optimization & Compression | faster, smaller or cheaper models and pipelines: compression, quantisation, caching, context reduction |
| AI Agents & Automation | software agents that carry out tasks, agent marketplaces, coding agents |
| Data & Database Construction | datasets, labelled or structured data, scraped or extracted data, knowledge bases |
| Search & Knowledge Retrieval | search, retrieval and recommendation over existing information |
| Forecasting & Prediction | forecasts of events or quantities other than asset prices: weather, sports, elections, demand |
| Financial Markets & Investing | trading signals, price forecasts, portfolios, funds, investment products |
| DeFi & Crypto Infrastructure | blockchain services: liquidity, swaps, bridges, stablecoins, node and RPC services |
| Cybersecurity, Authenticity & Verification | security testing, fraud and deepfake detection, identity, proofs and audits |
| Scientific & Technical Problem Solving | solutions to scientific or engineering problems: optimisation, drug discovery, mathematics, chip design |
| Robotics & Physical AI | robot control, drones, data and models for machines acting in the physical world |
| Media & Voice AI | generated or processed media: images, video, 3D, speech, translation |
| Marketing, Sales & Commerce | advertising, lead generation, creator and commerce services |
| Miscellaneous | nothing identifiable: vacant, parked, for sale, or no description |

## Eight groups for analysis

With 128 subnets, sixteen categories leave some with three members. The dataset therefore
also carries `category8`, fixed on 2 October 2026 before any price was compared across
categories:

| `category8` | Categories |
|---|---|
| Compute & inference | Compute, Storage & Network Infrastructure; AI Inference & Model Serving |
| Training & optimisation | AI Training & Model Improvement; AI Optimization & Compression |
| Agents, data & search | AI Agents & Automation; Data & Database Construction; Search & Knowledge Retrieval |
| Finance & forecasting | Forecasting & Prediction; Financial Markets & Investing |
| DeFi & crypto infrastructure | DeFi & Crypto Infrastructure |
| Security & verification | Cybersecurity, Authenticity & Verification |
| Science & robotics | Scientific & Technical Problem Solving; Robotics & Physical AI |
| Media, marketing & other | Media & Voice AI; Marketing, Sales & Commerce; Miscellaneous |

## Coders

Coder A is the catalog itself (`data/manual/catalog_categories_2026-08-20.csv`), used for a
subnet only if the name in the catalog is still the subnet's name at T. Coder B, and coder A
for subnets that changed since the catalog, is an independent reading of the dossier under
`config/coding_protocol.md`. Disagreements are settled as described there.
