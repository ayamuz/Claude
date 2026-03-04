"""
enrichment.py — Abstract enrichment via OpenAlex (primary) and PubMed (fallback).

Resolution order:
  1. CrossRef (already populated in discovery step)
  2. OpenAlex  — batch lookup by DOI, reconstruct from inverted index
  3. PubMed    — esearch DOI → PMID, then efetch XML
  4. Leave abstract as None
"""

import logging
import time
import xml.etree.ElementTree as ET

import requests

logger = logging.getLogger(__name__)

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

OPENALEX_BATCH = 50
PUBMED_BATCH = 200
RETRY_DELAYS = [1, 2, 4]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _get(url: str, params: dict, headers: dict | None = None, source: str = "") -> requests.Response | None:
    """GET with exponential backoff. Returns None on proxy block or exhausted retries."""
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            logger.warning("Retrying %s in %ds (attempt %d)...", source, delay, attempt)
            time.sleep(delay)
        try:
            resp = requests.get(url, params=params, headers=headers or {}, timeout=30)
            if resp.status_code == 429:
                wait = 1
                logger.warning("%s rate-limited (429), waiting %ds...", source, wait)
                time.sleep(wait)
                continue
            if resp.ok:
                return resp
            logger.warning("%s returned HTTP %d.", source, resp.status_code)
        except requests.exceptions.ProxyError as exc:
            logger.error("%s blocked by network proxy: %s", source, exc)
            return None  # No point retrying a proxy block
        except requests.RequestException as exc:
            logger.warning("%s request error: %s", source, exc)
    return None


# ---------------------------------------------------------------------------
# OpenAlex
# ---------------------------------------------------------------------------

def _reconstruct_abstract(inverted_index: dict) -> str | None:
    """Convert OpenAlex inverted-index abstract to plain text."""
    if not inverted_index:
        return None
    word_positions = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort(key=lambda x: x[0])
    return " ".join(word for _, word in word_positions)


def fetch_abstracts_openalex(papers: list[dict], polite_email: str) -> int:
    """
    Query OpenAlex in batches of 50 DOIs for papers missing abstracts.

    Updates paper dicts in-place. Returns count of abstracts retrieved.
    """
    missing = [p for p in papers if not p.get("abstract") and p.get("doi")]
    if not missing:
        return 0

    headers = {"User-Agent": f"PaperDigest/1.0 (mailto:{polite_email})"}
    doi_to_paper = {p["doi"]: p for p in missing}
    retrieved = 0

    for i in range(0, len(missing), OPENALEX_BATCH):
        batch = missing[i: i + OPENALEX_BATCH]
        doi_filter = "|".join(f"https://doi.org/{p['doi']}" for p in batch)
        params = {
            "filter": f"doi:{doi_filter}",
            "select": "doi,abstract_inverted_index",
            "per_page": OPENALEX_BATCH,
            "mailto": polite_email,
        }
        resp = _get(OPENALEX_WORKS_URL, params, headers, source="OpenAlex")
        if resp is None:
            continue

        try:
            results = resp.json().get("results", [])
        except ValueError:
            logger.warning("OpenAlex returned invalid JSON.")
            continue

        for work in results:
            # OpenAlex returns the full DOI URL; normalise to bare DOI
            raw_doi = work.get("doi") or ""
            doi = raw_doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
            inverted = work.get("abstract_inverted_index")
            if not inverted:
                continue
            abstract = _reconstruct_abstract(inverted)
            if abstract and doi in doi_to_paper:
                doi_to_paper[doi]["abstract"] = abstract
                retrieved += 1

        time.sleep(0.01)  # polite pool allows 100 req/sec; stay well under

    return retrieved


# ---------------------------------------------------------------------------
# PubMed
# ---------------------------------------------------------------------------

def _doi_to_pmid(doi: str, api_key: str, polite_email: str) -> str | None:
    """Look up a PubMed ID for a given DOI via esearch."""
    params = {
        "db": "pubmed",
        "term": f"{doi}[doi]",
        "retmode": "json",
        "tool": "PaperDigest",
        "email": polite_email,
    }
    if api_key:
        params["api_key"] = api_key
    resp = _get(ESEARCH_URL, params, source="PubMed esearch")
    if resp is None:
        return None
    try:
        ids = resp.json().get("esearchresult", {}).get("idlist", [])
        return ids[0] if ids else None
    except (ValueError, KeyError, IndexError):
        return None


def _fetch_abstracts_batch(pmids: list[str], api_key: str, polite_email: str) -> dict[str, str]:
    """Fetch abstracts for a batch of PMIDs via efetch. Returns PMID -> abstract text."""
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "rettype": "abstract",
        "retmode": "xml",
        "tool": "PaperDigest",
        "email": polite_email,
    }
    if api_key:
        params["api_key"] = api_key
    resp = _get(EFETCH_URL, params, source="PubMed efetch")
    if resp is None:
        return {}

    abstracts = {}
    try:
        root = ET.fromstring(resp.content)
        for article in root.findall(".//PubmedArticle"):
            pmid_el = article.find(".//MedlineCitation/PMID")
            if pmid_el is None:
                continue
            pmid = pmid_el.text
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
        logger.warning("Failed to parse PubMed XML: %s", exc)

    return abstracts


def fetch_abstracts_pubmed(papers: list[dict], pubmed_api_key: str, polite_email: str) -> int:
    """
    Query PubMed for papers still missing abstracts after OpenAlex.

    Updates paper dicts in-place. Returns count of abstracts retrieved.
    """
    missing = [p for p in papers if not p.get("abstract") and p.get("doi")]
    if not missing:
        return 0

    # Probe connectivity before iterating all DOIs
    probe = {
        "db": "pubmed", "term": "test", "retmode": "json",
        "retmax": "0", "tool": "PaperDigest", "email": polite_email,
    }
    if pubmed_api_key:
        probe["api_key"] = pubmed_api_key
    if _get(ESEARCH_URL, probe, source="PubMed probe") is None:
        logger.warning("PubMed unreachable — skipping PubMed enrichment.")
        return 0

    # Step 1: resolve DOIs → PMIDs
    doi_to_pmid: dict[str, str] = {}
    for paper in missing:
        doi = paper["doi"]
        pmid = _doi_to_pmid(doi, pubmed_api_key, polite_email)
        if pmid:
            doi_to_pmid[doi] = pmid
        time.sleep(0.1)

    if not doi_to_pmid:
        return 0

    pmid_to_paper = {
        doi_to_pmid[p["doi"]]: p
        for p in missing
        if p["doi"] in doi_to_pmid
    }

    # Step 2: batch-fetch abstracts
    pmids = list(pmid_to_paper.keys())
    retrieved = 0
    for i in range(0, len(pmids), PUBMED_BATCH):
        batch = pmids[i: i + PUBMED_BATCH]
        abstracts = _fetch_abstracts_batch(batch, pubmed_api_key, polite_email)
        for pmid, abstract in abstracts.items():
            if pmid in pmid_to_paper:
                pmid_to_paper[pmid]["abstract"] = abstract
                retrieved += 1
        time.sleep(0.1)

    return retrieved


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def enrich_abstracts(papers: list[dict], pubmed_api_key: str, polite_email: str) -> list[dict]:
    """
    Enrich missing abstracts using OpenAlex then PubMed as fallback.

    Modifies paper dicts in-place. Returns the updated list.
    """
    missing_before = sum(1 for p in papers if not p.get("abstract"))
    if missing_before == 0:
        return papers

    print("Enriching abstracts...")

    openalex_count = fetch_abstracts_openalex(papers, polite_email)
    remaining_after_openalex = sum(1 for p in papers if not p.get("abstract"))
    print(f"  OpenAlex: {openalex_count} abstract{'s' if openalex_count != 1 else ''} retrieved "
          f"({remaining_after_openalex} remaining)")

    pubmed_count = fetch_abstracts_pubmed(papers, pubmed_api_key, polite_email)
    missing_after = sum(1 for p in papers if not p.get("abstract"))
    print(f"  PubMed: {pubmed_count} abstract{'s' if pubmed_count != 1 else ''} retrieved "
          f"({missing_after} remaining)")
    print(f"  Still missing: {missing_after} papers without abstracts")

    return papers
