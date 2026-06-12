"""Google Jobs scraper using Serper API."""
import json
import requests
from typing import List, Dict, Any
from config import SERPER_KEY, NIGERIA_QUERIES, GLOBAL_QUERIES, TIMEOUT
from utils import retry_with_backoff, deduplicate_jobs, logger


@retry_with_backoff()
def search_serper_jobs(query: str, num: int = 20) -> List[Dict[str, Any]]:
    """Search for jobs using Serper API."""
    if not SERPER_KEY:
        logger.warning("SERPER_KEY not set; skipping Google Jobs scraper")
        return []
    
    headers = {
        "X-API-KEY": SERPER_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "q": query,
        "num": num,
        "gl": "ng",
        "hl": "en",
    }
    
    resp = requests.post(
        "https://google.serper.dev/search",
        headers=headers,
        json=payload,
        timeout=TIMEOUT
    )
    resp.raise_for_status()
    data = resp.json()

    jobs = []
    for job in data.get("jobs", []) + data.get("organic", []):
        # Prefer structured fields but fall back to common alternatives
        company = job.get("companyName") or job.get("displayedLink") or job.get("source")
        apply_link = job.get("applyLink") or job.get("link") or job.get("url")
        description = job.get("description", "") or job.get("snippet", "")

        # If key fields are missing, try following the result link to extract them
        candidate_url = apply_link or job.get("link") or job.get("url")
        if (not company or not apply_link) and candidate_url:
            try:
                from utils import fetch_page_details
                details = fetch_page_details(candidate_url)
                if not company and details.get('company'):
                    company = details.get('company')
                if not apply_link and details.get('apply_link'):
                    apply_link = details.get('apply_link')
            except Exception as e:
                logger.debug(f"Error following result link {candidate_url}: {e}")

        if not company:
            logger.debug(f"Serper result missing company for title='{job.get('title')}'")
        if not apply_link:
            logger.debug(f"Serper result missing apply link for title='{job.get('title')}'")

        jobs.append({
            "title": job.get("title"),
            "company": company,
            "location": job.get("location"),
            "posted": job.get("datePosted"),
            "salary": job.get("salary"),
            "remote": job.get("workFromHome", False),
            "apply_link": apply_link,
            "description": (description or "")[:300],
            "source": "serper",
        })
    return jobs


def run_google_scraper(include_global: bool = False, queries: List[str] = None) -> List[Dict[str, Any]]:
    """Run Google Jobs scraper.

    If `queries` is provided, those queries will be used. Otherwise fall back to
    the default Nigeria + optional global queries.
    """
    all_jobs = []
    if queries is None:
        queries = NIGERIA_QUERIES + (GLOBAL_QUERIES if include_global else [])

    for q in queries:
        logger.info(f"Searching Google Jobs: {q}")
        try:
            jobs = search_serper_jobs(q)
            all_jobs.extend(jobs)
            logger.info(f"  Found {len(jobs)} results")
        except Exception as e:
            logger.error(f"  Error searching '{q}': {e}")
            continue

    return deduplicate_jobs(all_jobs)

if __name__ == "__main__":
    jobs = run_google_scraper(include_global=True)
    print(f"\nTotal unique jobs: {len(jobs)}")
    with open("google_jobs.json", "w") as f:
        json.dump(jobs, f, indent=2)