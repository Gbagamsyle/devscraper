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
        jobs.append({
            "title": job.get("title"),
            "company": job.get("companyName"),
            "location": job.get("location"),
            "posted": job.get("datePosted"),
            "salary": job.get("salary"),
            "remote": job.get("workFromHome", False),
            "apply_link": job.get("applyLink"),
            "description": job.get("description", "")[:300],
            "source": "serper",
        })
    return jobs


def run_google_scraper(include_global: bool = False) -> List[Dict[str, Any]]:
    """Run Google Jobs scraper."""
    all_jobs = []
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