"""Shared utilities for job scrapers."""
import logging
import os
import time
from typing import List, Dict, Set, Tuple, Any, Callable
from functools import wraps
import requests

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
        "description": job.get("description", "")[:500],  # Limit description
        "source": source,
    }


def batch_items(items: List[Any], batch_size: int) -> List[List[Any]]:
    """Split list into batches."""
    return [items[i:i + batch_size] for i in range(0, len(items), batch_size)]
