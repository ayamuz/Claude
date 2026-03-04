#!/usr/bin/env python3
"""
digest.py — CLI entry point for the Scientific Paper Digest Pipeline.

Usage:
    python digest.py --days 4
    python digest.py --days 7 --min-score 15 --output my_digest.xlsx
"""

import argparse
import csv
import logging
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from modules.discovery import discover_papers
from modules.enrichment import enrich_abstracts
from modules.evaluation import evaluate_papers
from modules.output import write_spreadsheet

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def load_journals(path: str) -> list[dict]:
    """Read journals.csv and return list of {'name': ..., 'issn': ...} dicts."""
    journals = []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("name", "").strip()
                issn = row.get("issn", "").strip()
                if name or issn:
                    journals.append({"name": name, "issn": issn})
    except FileNotFoundError:
        print(f"ERROR: journals.csv not found at '{path}'.")
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: Failed to read journals.csv: {exc}")
        sys.exit(1)
    return journals


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scientific Paper Digest — fetch, score, and rank recent journal papers.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--days",
        type=int,
        default=4,
        help="Look back N days from today.",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=0,
        dest="min_score",
        help="Papers below this total score get gray styling in the spreadsheet.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output filename (default: digest_YYYY-MM-DD.xlsx).",
    )
    parser.add_argument(
        "--journals",
        type=str,
        default="journals.csv",
        help="Path to journals CSV file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Load environment variables
    load_dotenv()

    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
    pubmed_api_key = os.getenv("PUBMED_API_KEY", "")
    polite_email = os.getenv("POLITE_EMAIL", "user@example.com")

    if not anthropic_api_key:
        print("ERROR: ANTHROPIC_API_KEY is not set. Add it to your .env file.")
        sys.exit(1)

    if not pubmed_api_key:
        print("WARNING: PUBMED_API_KEY is not set. PubMed enrichment will be limited to 3 req/sec.")

    # Determine output filename
    output_path = args.output or f"digest_{date.today().isoformat()}.xlsx"

    # -----------------------------------------------------------------------
    # Step 1: Load journals
    # -----------------------------------------------------------------------
    journals = load_journals(args.journals)
    if not journals:
        print("ERROR: No journals found in journals.csv.")
        sys.exit(1)

    print(f"Loading {len(journals)} journal{'s' if len(journals) != 1 else ''} from {args.journals}...")

    # -----------------------------------------------------------------------
    # Step 2: Discover papers via CrossRef
    # -----------------------------------------------------------------------
    papers = discover_papers(journals, days=args.days, polite_email=polite_email)

    if not papers:
        print("No papers found in the specified date range. Exiting.")
        sys.exit(0)

    papers_with_abstracts = sum(1 for p in papers if p.get("abstract"))
    print(
        f"\nDiscovery complete: {len(papers)} paper{'s' if len(papers) != 1 else ''} "
        f"found across {len(journals)} journals."
    )

    # -----------------------------------------------------------------------
    # Step 3: Enrich missing abstracts via PubMed
    # -----------------------------------------------------------------------
    papers = enrich_abstracts(papers, pubmed_api_key=pubmed_api_key, polite_email=polite_email)

    with_abstracts = sum(1 for p in papers if p.get("abstract"))

    # -----------------------------------------------------------------------
    # Step 4: Evaluate with Claude
    # -----------------------------------------------------------------------
    papers, failed_count = evaluate_papers(papers, anthropic_api_key=anthropic_api_key)

    evaluated_count = len(papers) - failed_count

    # -----------------------------------------------------------------------
    # Step 5: Write spreadsheet
    # -----------------------------------------------------------------------
    print(f"Writing {output_path}...")
    write_spreadsheet(papers, output_path=output_path, min_score=args.min_score)

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    top_score = max(
        (p.get("total_score") or 0 for p in papers if not p.get("_eval_failed")),
        default=0,
    )

    print(f"Done. {len(papers)} papers scored. Top score: {top_score}/30.")
    print(
        f"\nSummary: {len(papers)} papers found, {with_abstracts} with abstracts, "
        f"{evaluated_count} successfully evaluated, {failed_count} evaluation failures."
    )


if __name__ == "__main__":
    main()
