"""Free job board scrapers: RemoteOK and LinkedIn."""
import json
import requests
import re
from typing import List, Dict, Any
from config import LINKEDIN_SEARCHES, TIMEOUT, DEV_KEYWORDS
from utils import retry_with_backoff, deduplicate_jobs, filter_keywords, logger


@retry_with_backoff()
def fetch_remoteok() -> List[Dict[str, Any]]:
    """Fetch dev jobs from RemoteOK API."""
    remoteok_url = "https://remoteok.com/api"
    headers = {"User-Agent": "Mozilla/5.0 (job-scraper-personal)"}
    
    resp = requests.get(remoteok_url, headers=headers, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    
    jobs = []
    for job in data[1:]:  # First item is metadata
        title = (job.get("position") or "").lower()
        tags = " ".join(job.get("tags") or []).lower()
        combined = title + " " + tags
        
        if filter_keywords(combined, DEV_KEYWORDS):
            jobs.append({
                "title": job.get("position"),
                "company": job.get("company"),
                "location": "Remote",
                "posted": job.get("date"),
                "salary": job.get("salary"),
                "apply_link": job.get("url"),
                "tags": job.get("tags", []),
                "description": job.get("description", "")[:300],
                "source": "remoteok",
            })
    
    logger.info(f"RemoteOK: Found {len(jobs)} dev jobs")
    return jobs


@retry_with_backoff()
def fetch_linkedin_rss(keywords: str = "frontend developer", location: str = "Nigeria") -> List[Dict[str, Any]]:
    """Fetch jobs from LinkedIn using guest API."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    
    api_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    params = {
        "keywords": keywords,
        "location": location,
        "start": 0,
        "count": 25,
        "f_WT": 2,  # remote
    }
    
    try:
        resp = requests.get(api_url, params=params, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        
        jobs = []
        # Basic regex extraction from LinkedIn HTML cards
        titles = re.findall(r'class="base-search-card__title"[^>]*>\s*([^<]+)', resp.text)
        companies = re.findall(r'class="base-search-card__subtitle"[^>]*>\s*<[^>]+>\s*([^<]+)', resp.text)
        locations_list = re.findall(r'class="job-search-card__location"[^>]*>\s*([^<]+)', resp.text)
        links = re.findall(r'href="(https://www\.linkedin\.com/jobs/view/[^"]+)"', resp.text)
        
        for i in range(min(len(titles), len(companies))):
            jobs.append({
                "title": titles[i].strip() if i < len(titles) else "",
                "company": companies[i].strip() if i < len(companies) else "",
                "location": locations_list[i].strip() if i < len(locations_list) else location,
                "posted": "",
                "salary": "",
                "apply_link": links[i] if i < len(links) else "",
                "description": "",
                "source": "linkedin",
            })
        
        logger.debug(f"LinkedIn: Found {len(jobs)} results for '{keywords}' in {location}")
        return jobs
    except Exception as e:
        logger.error(f"LinkedIn error ({keywords}/{location}): {e}")
        return []


def run_free_scraper() -> List[Dict[str, Any]]:
    """Run RemoteOK and LinkedIn scrapers."""
    all_jobs = []
    
    logger.info("Running RemoteOK scraper...")
    try:
        rok = fetch_remoteok()
        all_jobs.extend(rok)
    except Exception as e:
        logger.error(f"RemoteOK scraper failed: {e}")
    
    logger.info("Running LinkedIn scraper...")
    for keywords, location in LINKEDIN_SEARCHES:
        logger.info(f"  Searching: {keywords} / {location}")
        try:
            li = fetch_linkedin_rss(keywords, location)
            all_jobs.extend(li)
        except Exception as e:
            logger.error(f"  Error: {e}")
    
    return deduplicate_jobs(all_jobs)


if __name__ == "__main__":
    jobs = run_free_scraper()
    print(f"\nTotal: {len(jobs)} jobs")
    with open("free_jobs.json", "w") as f:
        json.dump(jobs, f, indent=2)