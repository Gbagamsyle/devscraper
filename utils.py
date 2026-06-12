"""Shared utilities for job scrapers."""
import logging
import os
import time
from typing import List, Dict, Set, Tuple, Any, Callable
from functools import wraps
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import json

from config import LOG_DIR, RETRIES, RETRY_BACKOFF


def setup_logging():
    """Initialize logging to file and console."""
    os.makedirs(LOG_DIR, exist_ok=True)
    
    logger = logging.getLogger("job_scraper")
    logger.setLevel(logging.DEBUG)
    
    # File handler
    fh = logging.FileHandler(f"{LOG_DIR}/scraper.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    
    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    
    # Formatter
    fmt = logging.Formatter(
        "%(asctime)s [%(name)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger


logger = setup_logging()


def retry_with_backoff(max_retries: int = RETRIES, backoff: float = RETRY_BACKOFF):
    """Decorator for retrying failed API calls with exponential backoff."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (requests.RequestException, Exception) as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        wait_time = backoff ** attempt
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries} failed for {func.__name__}: {e}. "
                            f"Retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(f"All {max_retries} attempts failed for {func.__name__}: {e}")
            raise last_error
        return wrapper
    return decorator


def deduplicate_jobs(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate jobs by (title, company) tuple."""
    seen: Set[Tuple[str, str]] = set()
    unique: List[Dict[str, Any]] = []
    
    for job in jobs:
        key = (
            str(job.get("title", "")).lower().strip(),
            str(job.get("company", "")).lower().strip(),
        )
        if key not in seen and key != ("", ""):
            seen.add(key)
            unique.append(job)
    
    logger.debug(f"Deduplication: {len(jobs)} → {len(unique)} jobs")
    return unique


def filter_keywords(text: str, keywords: List[str]) -> bool:
    """Check if any keyword is in the text."""
    return any(k.lower() in text.lower() for k in keywords)


def extract_job_data(job: Dict[str, Any], source: str) -> Dict[str, Any]:
    """Normalize job data format."""
    return {
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "posted": job.get("posted", ""),
        "salary": job.get("salary", ""),
        "apply_link": job.get("apply_link", ""),
        "description": job.get("description", ""),
        "source": source,
        "raw": job,
    }


def batch_items(items: List[Any], batch_size: int) -> List[List[Any]]:
    """Split list into batches."""
    return [items[i:i + batch_size] for i in range(0, len(items), batch_size)]


@retry_with_backoff()
def fetch_page_details(url: str, timeout: int = 10) -> Dict[str, Any]:
    """Fetch a page and try to extract company name and an apply link.

    Returns a dict: {"company": Optional[str], "apply_link": Optional[str], "url": url}
    Uses simple heuristics: meta tags, structured JSON-LD, and link text/href patterns.
    """
    result = {"company": None, "apply_link": None, "url": url}
    if not url:
        return result

    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        text = resp.text
    except Exception as e:
        logger.debug(f"fetch_page_details: failed to fetch {url}: {e}")
        return result

    try:
        soup = BeautifulSoup(text, "html.parser")

        # Try JSON-LD structured data
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string or "{}")
                if isinstance(data, dict):
                    # Organization or JobPosting
                    if data.get('@type') in ('Organization', 'Company') and not result['company']:
                        result['company'] = data.get('name')
                    if data.get('@type') == 'JobPosting' and not result['apply_link']:
                        appl = data.get('applicationContact') or data.get('url') or data.get('hiringOrganization')
                        if isinstance(appl, str):
                            result['apply_link'] = appl
            except Exception:
                continue

        # Meta tags
        if not result['company']:
            og_site = soup.find('meta', property='og:site_name')
            if og_site and og_site.get('content'):
                result['company'] = og_site['content']
        if not result['company']:
            author = soup.find('meta', attrs={'name': 'author'})
            if author and author.get('content'):
                result['company'] = author['content']

        # Heuristics: find elements that look like company names
        if not result['company']:
            possible = soup.select("[class*='company'], [class*='employer'], [class*='org']")
            if possible:
                text = possible[0].get_text(strip=True)
                if text:
                    result['company'] = text

        # Find candidate apply links/buttons
        if not result['apply_link']:
            candidates = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                txt = a.get_text(" ", strip=True).lower()
                href_l = href.lower()
                if any(k in txt for k in ('apply', 'apply now', 'apply here', 'submit', 'apply on', 'careers')):
                    candidates.append(urljoin(url, href))
                elif any(k in href_l for k in ('/apply', '/careers', '/jobs', 'linkedin.com/jobs', 'workable', '/positions')):
                    candidates.append(urljoin(url, href))
            if candidates:
                result['apply_link'] = candidates[0]

        # Fallback: use canonical or the original URL
        if not result['apply_link']:
            canon = soup.find('link', rel='canonical')
            if canon and canon.get('href'):
                result['apply_link'] = urljoin(url, canon['href'])
        if not result['company']:
            # derive company from domain
            try:
                parsed = urlparse(url)
                domain = parsed.netloc.split(':')[0]
                result['company'] = domain
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"fetch_page_details: parse failed for {url}: {e}")

    return result
