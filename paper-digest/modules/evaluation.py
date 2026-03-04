"""
evaluation.py — Claude API scoring of papers for science journalism potential.
"""

import json
import logging
import time

import anthropic

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5"
BATCH_SIZE = 10
RETRY_DELAYS = [2, 4, 8]

SYSTEM_PROMPT = """\
You are a science journalism editor evaluating scientific papers for story potential. For each paper, you receive the title, journal, authors, and abstract.

Score each paper on the following 6 criteria, each on a scale of 1-5:

1. US AUDIENCE RELEVANCE — Is this about something in North America, globally significant, or with a clear angle relevant to US readers, policy, or ecosystems? Papers focused exclusively on regions with no US parallel or policy connection score low.

2. LOCAL/REGIONAL RELEVANCE — Does it involve Chicago, Illinois, the Great Lakes, the Midwest, or have implications especially resonant locally? Most papers will score 1-2 here unless they have a clear local angle.

3. POLICY OR CONSERVATION IMPLICATIONS — Does it inform a current debate, support or challenge existing policy, or have clear management implications?

4. ACCESSIBILITY TO GENERAL AUDIENCE — Can the core finding be explained in plain language without losing significance? Does it connect to things people already care about?

5. SURPRISING OR COUNTERINTUITIVE FINDINGS — Does the result challenge conventional wisdom, reveal something unexpected, or overturn an assumption?

6. RELEVANCE TO CURRENT POLITICS OR EVENTS — Does it connect to live policy debates (ESA rollbacks, NEPA changes, data center water use, agricultural runoff, climate legislation, etc.)?

After scoring, apply these modifiers:

AUTOMATIC BOOSTS (note which apply):
- Chicago or Illinois study site
- Great Lakes or Upper Midwest focus
- North American species, ecosystem, or policy context
- Globally significant finding with clear US implications (e.g., migratory species, climate tipping points, internationally traded commodities)
- Involves a charismatic or well-known species
- Directly contradicts a politically held position with data
- Has a clear "so what" for everyday people

DEPRIORITIZE FLAGS (note which apply):
- Focused on regions or species with no meaningful US parallel, policy connection, or global significance
- Purely methodological with no clear applied finding
- Highly technical with no accessible hook
- Replication of well-established findings

For each paper, respond with a JSON object. Do NOT include any text outside the JSON array.

Respond ONLY with a JSON array of objects, one per paper, in the same order as the input. Each object must have:
{
  "paper_index": <integer, 0-based index matching input order>,
  "us_relevance": <1-5>,
  "local_relevance": <1-5>,
  "policy_implications": <1-5>,
  "accessibility": <1-5>,
  "surprise_factor": <1-5>,
  "current_events": <1-5>,
  "total_score": <sum of above, 6-30>,
  "boost_flags": [<list of strings, or empty>],
  "deprioritize_flags": [<list of strings, or empty>],
  "story_hook": "<1-2 sentence pitch angle for this paper as a news story>"
}\
"""


def _build_user_message(batch: list[dict], batch_offset: int) -> str:
    """Format a batch of papers into the user message for Claude."""
    lines = [f"Evaluate these {len(batch)} papers:", ""]
    for local_idx, paper in enumerate(batch):
        global_idx = batch_offset + local_idx
        abstract = paper.get("abstract") or "No abstract available."
        lines += [
            f"--- PAPER {local_idx}",
            f"Title: {paper.get('title', 'Unknown')}",
            f"Journal: {paper.get('journal_name', 'Unknown')}",
            f"Authors: {paper.get('authors', 'Unknown')}",
            f"Abstract: {abstract}",
            "",
        ]
    return "\n".join(lines)


def _parse_response(raw: str) -> list[dict] | None:
    """
    Extract and parse the JSON array from Claude's response text.
    Returns None if parsing fails.
    """
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop first and last fence lines
        text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Try to find a JSON array anywhere in the response
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start: end + 1])
        except json.JSONDecodeError:
            pass

    return None


def _evaluate_batch(client: anthropic.Anthropic, batch: list[dict], batch_offset: int, batch_num: int, total_batches: int) -> list[dict]:
    """
    Send one batch to Claude and return evaluation results.
    Retries up to 3 times on failure.
    """
    user_msg = _build_user_message(batch, batch_offset)

    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            logger.warning("Retrying batch %d in %ds (attempt %d)...", batch_num, delay, attempt)
            time.sleep(delay)

        print(f"  batch {batch_num}/{total_batches}", end="\r", flush=True)

        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw = response.content[0].text
            parsed = _parse_response(raw)

            if parsed is not None:
                return parsed

            logger.warning("Failed to parse JSON from batch %d (attempt %d). Raw response:\n%s", batch_num, attempt + 1, raw[:500])

        except anthropic.APIError as exc:
            logger.warning("Claude API error on batch %d: %s", batch_num, exc)

    # Permanent failure — mark all papers in batch as failed
    logger.error("Batch %d permanently failed after all retries.", batch_num)
    return []


def evaluate_papers(papers: list[dict], anthropic_api_key: str) -> list[dict]:
    """
    Score all papers using Claude Haiku.

    Adds evaluation fields to each paper dict in-place.
    Returns the updated list.
    """
    client = anthropic.Anthropic(api_key=anthropic_api_key)
    total = len(papers)
    total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

    print(f"Evaluating papers with Claude (Haiku)...")

    failed_count = 0

    for batch_num, start in enumerate(range(0, total, BATCH_SIZE), start=1):
        batch = papers[start: start + BATCH_SIZE]
        results = _evaluate_batch(client, batch, start, batch_num, total_batches)

        if not results:
            # Mark all papers in this batch as failed
            for paper in batch:
                paper.update({
                    "us_relevance": None,
                    "local_relevance": None,
                    "policy_implications": None,
                    "accessibility": None,
                    "surprise_factor": None,
                    "current_events": None,
                    "total_score": None,
                    "boost_flags": [],
                    "deprioritize_flags": [],
                    "story_hook": "evaluation failed",
                    "_eval_failed": True,
                })
            failed_count += len(batch)
            continue

        # Map results back to papers by paper_index (0-based within batch)
        result_map = {r.get("paper_index", i): r for i, r in enumerate(results)}

        for local_idx, paper in enumerate(batch):
            result = result_map.get(local_idx)
            if result is None:
                paper.update({
                    "us_relevance": None,
                    "local_relevance": None,
                    "policy_implications": None,
                    "accessibility": None,
                    "surprise_factor": None,
                    "current_events": None,
                    "total_score": None,
                    "boost_flags": [],
                    "deprioritize_flags": [],
                    "story_hook": "evaluation failed",
                    "_eval_failed": True,
                })
                failed_count += 1
            else:
                paper.update({
                    "us_relevance": result.get("us_relevance"),
                    "local_relevance": result.get("local_relevance"),
                    "policy_implications": result.get("policy_implications"),
                    "accessibility": result.get("accessibility"),
                    "surprise_factor": result.get("surprise_factor"),
                    "current_events": result.get("current_events"),
                    "total_score": result.get("total_score"),
                    "boost_flags": result.get("boost_flags", []),
                    "deprioritize_flags": result.get("deprioritize_flags", []),
                    "story_hook": result.get("story_hook", ""),
                    "_eval_failed": False,
                })

    print(f"\nEvaluation complete.")
    return papers, failed_count
