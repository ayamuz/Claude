"""
enrichment.py — PubMed abstract fallback for papers without CrossRef abstracts.
"""

import logging
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
BATCH_SIZE = 200
RETRY_DELAYS = [2, 4, 8]


def _get_with_retry(url: str, params: dict) -> requests.Response | None:
    """GET with exponential backoff."""
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            logger.warning("Retrying PubMed request in %ds (attempt %d)...", delay, attempt)
            time.sleep(delay)
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.ok:
                return resp
            logger.warning("PubMed returned HTTP %d.", resp.status_code)
        except requests.RequestException as exc:
            logger.warning("PubMed request error: %s", exc)
    return None


def _doi_to_pmid(doi: str, api_key: str, polite_email: str) -> str | None:
    """Look up a PubMed ID for a given DOI via esearch."""
    params = {
        "db": "pubmed",
        "term": f"{doi}[doi]",
        "retmode": "json",
        "api_key": api_key,
        "tool": "PaperDigest",
        "email": polite_email,
    }
    resp = _get_with_retry(ESEARCH_URL, params)
    if resp is None:
        return None
    try:
        data = resp.json()
        ids = data.get("esearchresult", {}).get("idlist", [])
        return ids[0] if ids else None
    except (ValueError, KeyError, IndexError):
        return None


def _fetch_abstracts_batch(pmids: list[str], api_key: str, polite_email: str) -> dict[str, str]:
    """
    Fetch abstracts for a batch of PubMed IDs via efetch.

    Returns dict mapping PMID -> abstract text.
    """
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "rettype": "abstract",
        "retmode": "xml",
        "api_key": api_key,
        "tool": "PaperDigest",
        "email": polite_email,
    }
    resp = _get_with_retry(EFETCH_URL, params)
    if resp is None:
        return {}

    abstracts = {}
    try:
        root = ET.fromstring(resp.content)
        for article in root.findall(".//PubmedArticle"):
            # Extract PMID
            pmid_el = article.find(".//MedlineCitation/PMID")
            if pmid_el is None:
                continue
            pmid = pmid_el.text

            # Extract abstract — may have multiple AbstractText elements (structured abstracts)
            abstract_els = article.findall(".//Abstract/AbstractText")
            if not abstract_els:
                continue

            parts = []
            for el in abstract_els:
                label = el.get("Label")
                text = "".join(el.itertext()).strip()
                if label and text:
                    parts.append(f"{label}: {text}")
                elif text:
                    parts.append(text)

            if parts:
                abstracts[pmid] = " ".join(parts)
    except ET.ParseError as exc:
        logger.warning("Failed to parse PubMed XML response: %s", exc)

    return abstracts


def enrich_abstracts(papers: list[dict], pubmed_api_key: str, polite_email: str) -> list[dict]:
    """
    For papers missing abstracts, attempt to fetch them from PubMed.

    Modifies paper dicts in-place. Returns the updated list.
    """
    missing = [p for p in papers if not p.get("abstract")]
    if not missing:
        logger.info("All papers already have abstracts — skipping PubMed enrichment.")
        return papers

    print(f"Fetching missing abstracts from PubMed ({len(missing)} papers)...")

    # Step 1: Look up PMIDs for each missing DOI
    doi_to_pmid: dict[str, str] = {}
    for idx, paper in enumerate(missing):
        doi = paper.get("doi", "")
        if not doi:
            continue
        pmid = _doi_to_pmid(doi, pubmed_api_key, polite_email)
        if pmid:
            doi_to_pmid[doi] = pmid
        time.sleep(0.1)  # respect 10 req/sec

    if not doi_to_pmid:
        print("No PMIDs found for missing abstracts.")
        return papers

    # Build reverse map: PMID -> paper index in `papers`
    pmid_to_paper: dict[str, dict] = {}
    for paper in papers:
        doi = paper.get("doi", "")
        pmid = doi_to_pmid.get(doi)
        if pmid:
            pmid_to_paper[pmid] = paper

    # Step 2: Batch-fetch abstracts
    pmids = list(pmid_to_paper.keys())
    retrieved = 0

    for i in range(0, len(pmids), BATCH_SIZE):
        batch = pmids[i: i + BATCH_SIZE]
        abstracts = _fetch_abstracts_batch(batch, pubmed_api_key, polite_email)
        for pmid, abstract in abstracts.items():
            if pmid in pmid_to_paper:
                pmid_to_paper[pmid]["abstract"] = abstract
                retrieved += 1
        time.sleep(0.1)

    print(f"{retrieved} abstract{'s' if retrieved != 1 else ''} retrieved.")
    return papers
