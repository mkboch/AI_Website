# WANG-AXIS AI News

AI news and research aggregation website for WANG-AXIS Lab.

## Website architecture

The entire site uses:

- GitHub Pages
- GitHub Actions
- HTML
- CSS
- JavaScript
- Python
- JSON
- RSS feeds

No lab server is required.

No GPU is required.

No database server is required.

No paid API is required.

## Automatic updates

The GitHub Actions workflow runs daily.

The Python script retrieves public RSS metadata, removes duplicate stories, classifies articles, and updates:

data/news.json

The same workflow then deploys the updated website to GitHub Pages.

## Sources

The initial source list includes:

- MIT News Artificial Intelligence
- Nature Machine Learning
- arXiv Artificial Intelligence
- arXiv Computer Vision
- arXiv Computation and Language

Sources can be changed inside:

scripts/update_news.py

## Manual WANG-AXIS news

Manual stories can also be added to data/news.json.

Use:

"manual": true

Manual stories are preserved when the automatic updater runs.

## Repository

https://github.com/mkboch/AI_Website

## Website

https://mkboch.github.io/AI_Website/