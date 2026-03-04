"""
discovery.py — CrossRef API queries for recent journal papers.
"""

import re
import time
import logging
from datetime import date, timedelta

import requests

logger = logging.getLogger(__name__)

CROSSREF_BASE = "https://api.crossref.org/journals/{issn}/works"
KEEP_TYPES = {"journal-article"}
MAX_ROWS = 100
RETRY_DELAYS = [2, 4, 8]  # exponential backoff in seconds


def _strip_jats(text: str) -> str:
    """Remove JATS/XML tags from abstract text."""
    return re.sub(r"<[^>]+>", "", text).strip()


def _format_authors(authors: list) -> str:
    """Format CrossRef author list to 'Last, First; Last, First'."""
    parts = []
    for a in authors:
        family = a.get("family", "")
        given = a.get("given", "")
        if family and given:
            parts.append(f"{family}, {given}")
        elif family:
            parts.append(family)
        elif given:
            parts.append(given)
    return "; ".join(parts)


def _parse_date(date_parts: list) -> str:
    """Convert CrossRef date-parts list to YYYY-MM-DD string."""
    try:
        parts = date_parts[0]
        year = parts[0] if len(parts) > 0 else 1900
        month = parts[1] if len(parts) > 1 else 1
        day = parts[2] if len(parts) > 2 else 1
        return f"{year:04d}-{month:02d}-{day:02d}"
    except (IndexError, TypeError, ValueError):
        return ""


def _get_with_retry(url: str, params: dict, headers: dict) -> requests.Response | None:
    """GET request with exponential backoff on 429 or transient errors."""
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            logger.warning("Retrying in %ds (attempt %d)...", delay, attempt)
            time.sleep(delay)
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            if resp.status_code == 429:
                logger.warning("Rate limited by CrossRef (HTTP 429).")
                continue
            return resp
        except requests.RequestException as exc:
            logger.warning("Request error: %s", exc)
    return None


def fetch_journal_papers(issn: str, journal_name: str, start_date: date, end_date: date, polite_email: str) -> list[dict]:
    """
    Query CrossRef for all papers in a journal within the given date range.

    Returns a list of paper dicts.
    """
    headers = {
        "User-Agent": f"PaperDigest/1.0 (mailto:{polite_email})"
    }
    date_filter = f"from-pub-date:{start_date.isoformat()},until-pub-date:{end_date.isoformat()}"
    select_fields = "DOI,title,author,published,abstract,container-title,type"

    papers = []
    offset = 0

    while True:
        params = {
            "filter": date_filter,
            "rows": MAX_ROWS,
            "offset": offset,
            "select": select_fields,
        }
        url = CROSSREF_BASE.format(issn=issn)
        resp = _get_with_retry(url, params, headers)

        if resp is None:
            logger.warning("Failed to fetch %s (%s) after retries — skipping.", journal_name, issn)
            break

        if resp.status_code == 404:
            logger.warning("ISSN %s not found in CrossRef (404) — skipping.", issn)
            break

        if not resp.ok:
            logger.warning("CrossRef returned HTTP %d for %s — skipping.", resp.status_code, issn)
            break

        try:
            data = resp.json()
        except ValueError:
            logger.warning("Invalid JSON response for %s — skipping.", issn)
            break

        items = data.get("message", {}).get("items", [])
        if not items:
            break

        for item in items:
            if item.get("type") not in KEEP_TYPES:
                continue

            title_list = item.get("title") or []
            title = title_list[0] if title_list else ""

            abstract_raw = item.get("abstract", None)
            abstract = _strip_jats(abstract_raw) if abstract_raw else None

            container = item.get("container-title") or []
            jname = container[0] if container else journal_name

            pub_date = ""
            published = item.get("published") or item.get("published-print") or item.get("published-online") or {}
            date_parts = published.get("date-parts")
            if date_parts:
                pub_date = _parse_date(date_parts)

            papers.append({
                "doi": item.get("DOI", ""),
                "title": title,
                "authors": _format_authors(item.get("author") or []),
                "published_date": pub_date,
                "abstract": abstract,
                "journal_name": jname,
                "issn": issn,
            })

        # Paginate if there are more results
        total = data.get("message", {}).get("total-results", 0)
        offset += len(items)
        if offset >= total or len(items) < MAX_ROWS:
            break

    return papers


def discover_papers(journals: list[dict], days: int, polite_email: str) -> list[dict]:
    """
    Iterate over all journals and collect papers published in the last `days` days.

    journals: list of {'name': str, 'issn': str}
    Returns combined list of paper dicts.
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    all_papers = []
    total = len(journals)

    for idx, journal in enumerate(journals, start=1):
        name = journal.get("name", "Unknown")
        issn = journal.get("issn", "").strip()

        if not issn:
            logger.warning("[%d/%d] %s — missing ISSN, skipping.", idx, total, name)
            print(f"[{idx}/{total}] {name} — missing ISSN, skipping.")
            continue

        papers = fetch_journal_papers(issn, name, start_date, end_date, polite_email)
        count = len(papers)
        print(f"[{idx}/{total}] {name} ({issn}) — {count} paper{'s' if count != 1 else ''} found")
        all_papers.extend(papers)

        # Polite delay between journals (~0.1s) to stay well under 50 req/sec
        time.sleep(0.1)

    return all_papers
