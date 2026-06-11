"""Additional job scrapers for alternative sources."""
import requests
from typing import List, Dict, Any
from config import TIMEOUT, DEV_KEYWORDS
from utils import retry_with_backoff, deduplicate_jobs, filter_keywords, logger


@retry_with_backoff()
def fetch_jobicy() -> List[Dict[str, Any]]:
    """Fetch jobs from Jobicy API."""
    url = "https://jobicy.com/api/v2/remote-jobs"
    params = {
        "count": 50,
        "industry": "engineering",
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    
    resp = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    
    jobs = []
    for job in data.get("jobs", []):
        title = (job.get("jobTitle") or "").lower()
        tags = " ".join(job.get("jobIndustry") or []).lower()
        
        if filter_keywords(title + tags, DEV_KEYWORDS):
            jobs.append({
                "title": job.get("jobTitle"),
                "company": job.get("companyName"),
                "location": "Remote — " + (job.get("jobGeo") or "Worldwide"),
                "posted": job.get("pubDate"),
                "salary": job.get("annualSalaryMin"),
                "remote": True,
                "apply_link": job.get("url"),
                "description": (job.get("jobDescription") or "")[:300],
                "source": "jobicy",
            })
    
    logger.info(f"Jobicy: Found {len(jobs)} dev jobs")
    return jobs


@retry_with_backoff()
def fetch_remotive() -> List[Dict[str, Any]]:
    """Fetch jobs from Remotive API."""
    url = "https://remotive.com/api/remote-jobs"
    params = {"category": "software-dev", "limit": 50}
    headers = {"User-Agent": "Mozilla/5.0"}
    
    resp = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    
    jobs = []
    for job in data.get("jobs", []):
        title = (job.get("title") or "").lower()
        
        if filter_keywords(title, DEV_KEYWORDS):
            jobs.append({
                "title": job.get("title"),
                "company": job.get("company_name"),
                "location": "Remote — " + (job.get("candidate_required_location") or "Worldwide"),
                "posted": job.get("publication_date"),
                "salary": job.get("salary"),
                "remote": True,
                "apply_link": job.get("url"),
                "description": (job.get("description") or "")[:300],
                "source": "remotive",
            })
    
    logger.info(f"Remotive: Found {len(jobs)} dev jobs")
    return jobs


def run_alternative_scrapers() -> List[Dict[str, Any]]:
    """Run all alternative scrapers concurrently."""
    all_jobs = []
    
    for scraper_name, scraper_func in [("Jobicy", fetch_jobicy), ("Remotive", fetch_remotive)]:
        try:
            logger.info(f"Running {scraper_name} scraper...")
            jobs = scraper_func()
            all_jobs.extend(jobs)
        except Exception as e:
            logger.error(f"  Error: {e}")
            continue
    
    return deduplicate_jobs(all_jobs)
