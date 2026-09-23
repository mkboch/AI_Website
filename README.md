# WANG-AXIS AI Research Intelligence

A continuously refreshed, source-transparent AI research intelligence website for the WANG-AXIS Lab.

## Architecture

The site remains intentionally lightweight:

- GitHub Pages for hosting
- GitHub Actions for scheduled collection and deployment
- Python for source ingestion, classification, deduplication, ranking, balancing, and archiving
- HTML/CSS/JavaScript for the static front end
- JSON for the current feed, source-health metadata, and monthly archive
- no lab server
- no GPU
- no database server
- no paid API

## Refresh schedule

The workflow runs:

- on every push to `main`
- every 6 hours at minute 23 UTC
- on manual workflow dispatch

GitHub executes the refresh even when local computers and lab servers are off.

## Source model

Sources are configured in `config/sources.json` and grouped by source class and content type. The initial registry spans roughly 30 channels, including:

### Frontier and research labs

- OpenAI
- Anthropic
- Google DeepMind
- Google Research
- Google AI
- Microsoft Research
- NVIDIA Developer Blog
- Apple Machine Learning Research
- Allen Institute for AI
- Berkeley AI Research
- Stanford AI Lab
- Mistral AI
- Meta AI
- Mila
- Vector Institute
- EleutherAI
- Hugging Face
- AWS Machine Learning Blog

### Scientific and biomedical sources

- Nature Machine Intelligence
- Journal of Machine Learning Research
- PubMed medical-AI query

### Government and regulatory sources

- NIH News Releases
- NIST artificial-intelligence news and updates
- FDA MedWatch, restricted by the medical-AI relevance gate

### Research preprints

Balanced arXiv feeds for:

- Artificial Intelligence
- Machine Learning
- Computation and Language
- Computer Vision
- Robotics
- Image and Video Processing

### Selected technology news

- MIT News Artificial Intelligence
- MIT Technology Review AI
- TechCrunch AI

A failed or empty source is recorded in source-health metadata rather than silently treated as successful content.

## What changed from v1

### 1. Source balancing

Per-source caps and an overall preprint cap prevent any single arXiv feed or publisher from dominating the current page.

### 2. Publication/source-type labels

Items are visibly distinguished as official updates, research, journals, biomedical literature, government/regulatory material, engineering posts, news, or preprints.

### 3. Better classification

Topic selection is score-based rather than first-keyword-match. The tracked topic set includes:

- Medical Imaging
- Medical AI
- Trustworthy AI
- Foundation Models
- AI Agents
- AI4Education
- AI for Science
- Computer Vision
- Robotics & Embodied AI
- AI Systems & Hardware
- AI Policy & Governance

### 4. Relevance ranking without false claims

`priority_score` combines:

- WANG-AXIS topic relevance
- source tier
- content-type signal
- recency
- event/release/research signals

It is an editorial relevance heuristic for this website. It is **not** a scientific-quality score, citation metric, peer-review verdict, clinical-validity assessment, or endorsement.

### 5. Stronger deduplication

The pipeline normalizes URLs, arXiv versions, DOI/PMID/arXiv identifiers, exact titles, and high-similarity title variants. When duplicate coverage is detected, alternate source links can be retained as related links.

### 6. Failure-safe history

The current feed is rebuilt from new collection plus recent preserved data. A source outage therefore does not erase previously collected signals.

### 7. Persistent archive

Selected signals are accumulated in monthly files under:

`data/archive/YYYY-MM.json`

The archive index is:

`data/archive/index.json`

### 8. Source health

Every refresh writes:

`data/source_health.json`

The website shows configured, healthy, empty, and failed sources.

### 9. Conflict-safe GitHub updates

The workflow uses concurrency cancellation plus fetch/rebase/retry logic before pushing refreshed data, which reduces the non-fast-forward failure seen during the original double-trigger setup.

## Manual WANG-AXIS curation

Manual items live in:

`data/manual.json`

The updater also migrates any legacy `manual: true` records it finds in the current `data/news.json`.

## Files

- `config/sources.json` source registry
- `scripts/update_news.py` collection and ranking pipeline
- `data/news.json` current balanced feed
- `data/source_health.json` source status
- `data/archive/` persistent monthly archive
- `data/manual.json` lab-curated items
- `.github/workflows/ai-news.yml` refresh and Pages deployment

## Repository

https://github.com/mkboch/AI_Website

## Website

https://mkboch.github.io/AI_Website/
