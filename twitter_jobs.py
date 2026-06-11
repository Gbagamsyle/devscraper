"""Twitter/X Jobs scraper using API v2."""
import requests
from typing import List, Dict, Any
from config import TWITTER_BEARER, TIMEOUT
from utils import retry_with_backoff, deduplicate_jobs, logger


@retry_with_backoff()
def search_twitter_jobs(query: str, max_results: int = 100) -> List[Dict[str, Any]]:
    """Search for job posts on Twitter using API v2."""
    if not TWITTER_BEARER:
        logger.warning("TWITTER_BEARER not configured; skipping Twitter scraper")
        return []
    
    headers = {
        "Authorization": f"Bearer {TWITTER_BEARER}",
        "User-Agent": "job-scraper-bot/1.0"
    }
    
    url = "https://api.twitter.com/2/tweets/search/recent"
    
    # Search for job posts with common indicators
    search_query = f"{query} (hiring OR job OR apply OR vacancy) -is:retweet lang:en"
    
    params = {
        "query": search_query,
        "max_results": min(max_results, 100),
        "tweet.fields": "created_at,author_id,public_metrics",
        "expansions": "author_id",
        "user.fields": "username,verified",
    }
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        
        jobs = []
        for tweet in data.get("data", []):
            # Simple extraction from tweet text
            text = tweet.get("text", "")
            created_at = tweet.get("created_at", "")
            
            # Skip if very short
            if len(text) < 20:
                continue
            
            jobs.append({
                "title": text[:100],  # Use tweet start as title
                "company": "Twitter Post",
                "location": "Remote",
                "posted": created_at,
                "salary": "",
                "apply_link": f"https://twitter.com/i/web/status/{tweet.get('id', '')}",
                "description": text[:500],
                "source": "twitter",
            })
        
        logger.debug(f"Twitter: Found {len(jobs)} posts for query '{query}'")
        return jobs
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            logger.warning("Twitter API rate limited (429)")
        elif e.response.status_code == 401:
            logger.error("Invalid Twitter bearer token (401)")
        else:
            logger.error(f"Twitter API HTTP error {e.response.status_code}: {e}")
        return []
    except Exception as e:
        logger.error(f"Twitter scraper error: {e}")
        return []


def run_twitter_scraper(include_global: bool = True) -> List[Dict[str, Any]]:
    """Run Twitter Jobs scraper."""
    if not TWITTER_BEARER:
        logger.info("TWITTER_BEARER not set; skipping Twitter scraper")
        return []
    
    all_jobs = []
    
    queries = [
        "frontend developer",
        "React developer",
        "JavaScript developer",
        "web developer Nigeria",
    ]
    
    if include_global:
        queries.extend([
            "remote developer jobs",
            "hiring engineers",
        ])
    
    for q in queries:
        logger.info(f"Searching Twitter: {q}")
        try:
            jobs = search_twitter_jobs(q, max_results=50)
            all_jobs.extend(jobs)
            logger.info(f"  Found {len(jobs)} results")
        except Exception as e:
            logger.error(f"  Error: {e}")
            continue
    
    return deduplicate_jobs(all_jobs)