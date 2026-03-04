# Paper Digest

A CLI tool that scans scientific journals for recently published papers, fetches abstracts, evaluates each paper's science journalism potential using Claude AI, and outputs a scored Excel spreadsheet.

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API keys

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

Edit `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
PUBMED_API_KEY=your_pubmed_api_key_here
POLITE_EMAIL=you@example.com
```

- **ANTHROPIC_API_KEY** — Required. Get one at [console.anthropic.com](https://console.anthropic.com).
- **PUBMED_API_KEY** — Recommended. Raises rate limit to 10 req/sec. Get one at [NCBI](https://www.ncbi.nlm.nih.gov/account/).
- **POLITE_EMAIL** — Recommended. Lets CrossRef identify your requests for the polite pool (faster).

### 3. Edit your journal list

Edit `journals.csv` to add or remove journals. Format:

```csv
name,issn
Nature,0028-0836
Science,0036-8075
```

The tool ships with 20 starter journals. Add up to ~100 rows.

## Usage

```bash
# Basic: look back 4 days (default)
python digest.py

# Look back 7 days
python digest.py --days 7

# Custom output filename
python digest.py --days 4 --output my_digest.xlsx

# Gray-style papers scoring below 15
python digest.py --min-score 15
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--days N` | `4` | Look back N days from today |
| `--min-score N` | `0` | Papers below this score get gray styling in the spreadsheet |
| `--output FILE` | `digest_YYYY-MM-DD.xlsx` | Output filename |
| `--journals FILE` | `journals.csv` | Path to journal list CSV |

## Output

An `.xlsx` spreadsheet sorted by score (highest first) with columns:

| Column | Description |
|--------|-------------|
| Rank | By total score |
| Journal | Journal name |
| Title | Paper title |
| Authors | Formatted author list |
| DOI | Clickable hyperlink |
| Published | Publication date |
| Abstract | Full abstract |
| US Relevance | Score 1–5 |
| Local Relevance | Score 1–5 (Chicago/IL/Midwest focus) |
| Policy Score | Score 1–5 |
| Accessibility | Score 1–5 |
| Surprise Score | Score 1–5 |
| Current Events | Score 1–5 |
| Total Score | Sum 6–30 |
| Boosts | Applied boost flags |
| Deprioritize | Applied deprioritization flags |
| Story Hook | 1–2 sentence pitch angle |

Score columns use a red→yellow→green color scale. Papers below `--min-score` are styled in gray.

## Pipeline

```
journals.csv
     │
     ▼
[discovery.py]    CrossRef API → papers published in last N days
     │
     ▼
[enrichment.py]   PubMed API  → fill in missing abstracts
     │
     ▼
[evaluation.py]   Claude Haiku → score each paper on 6 editorial criteria
     │
     ▼
[output.py]       openpyxl    → formatted .xlsx spreadsheet
```

## Cost Estimate

Running on ~100 journals for 4 days typically finds 500–1000 papers.

- ~85–100 Claude Haiku batches × ~2K tokens each ≈ 170–200K tokens
- Approximate cost: **$0.50–$2.00 per run** at current Haiku pricing

## Project Structure

```
paper-digest/
├── digest.py          # CLI entry point
├── journals.csv       # Editable journal list
├── .env               # API keys (not committed)
├── .env.example       # Key template
├── requirements.txt   # Python dependencies
├── README.md
└── modules/
    ├── discovery.py   # CrossRef API queries
    ├── enrichment.py  # PubMed abstract fallback
    ├── evaluation.py  # Claude API scoring
    └── output.py      # Excel generation
```
