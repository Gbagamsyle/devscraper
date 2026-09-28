"""Shared utilities for job scrapers."""
import logging
import os
import re
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


def _normalized_text(value: Any) -> str:
    """Normalize text for conservative identity comparisons."""
    normalized = re.sub(r"[^\w]+", " ", str(value or "").casefold(), flags=re.UNICODE)
    return " ".join(normalized.split())


def _source_entries(job: Dict[str, Any]) -> List[Dict[str, str]]:
    """Read both the new source list and legacy single-source records."""
    entries = []
    for source in job.get("sources", []) or []:
        if isinstance(source, dict) and source.get("name"):
            entries.append({"name": str(source["name"]), "url": str(source.get("url") or "")})
        elif source:
            entries.append({"name": str(source), "url": ""})
    if not entries:
        source_names = job.get("source", "")
        if isinstance(source_names, list):
            names = source_names
        else:
            names = str(source_names).split(",")
        entries.extend(
            {"name": name.strip(), "url": str(job.get("apply_link") or "")}
            for name in names if name.strip()
        )
    return entries


def deduplicate_jobs(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge equivalent listings while preserving location variants and sources."""
    merged: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for index, original in enumerate(jobs):
        job = dict(original)
        title = _normalized_text(job.get("title"))
        company = _normalized_text(job.get("company"))
        location = _normalized_text(job.get("location"))
        if not title and not company:
            continue

        # Missing locations are only merged with other missing locations; do
        # not let an unlocated result erase a known location variant.
        link_identity = ""
        if not title or not company:
            parsed_link = urlparse(str(job.get("apply_link") or ""))
            if parsed_link.netloc:
                link_identity = f"{parsed_link.netloc.casefold()}{parsed_link.path.rstrip('/').casefold()}"
            else:
                link_identity = f"unidentified-{index}"
        key = (title, company, location, link_identity)
        existing = merged.get(key)
        if existing is None:
            sources = _source_entries(job)
            job["sources"] = _unique_sources(sources)
            job["source"] = ", ".join(dict.fromkeys(item["name"] for item in job["sources"]))
            merged[key] = job
            continue

        existing["sources"] = _unique_sources(existing.get("sources", []) + _source_entries(job))
        existing["source"] = ", ".join(dict.fromkeys(item["name"] for item in existing["sources"]))
        for field in ("posted", "salary", "description", "apply_link"):
            if not existing.get(field) and job.get(field):
                existing[field] = job[field]

    unique = list(merged.values())
    logger.debug(f"Deduplication: {len(jobs)} → {len(unique)} jobs")
    return unique


def _unique_sources(sources: List[Dict[str, str]]) -> List[Dict[str, str]]:
    result = []
    seen: Set[Tuple[str, str]] = set()
    for source in sources:
        entry = {"name": str(source.get("name") or ""), "url": str(source.get("url") or "")}
        key = (entry["name"].casefold(), entry["url"].casefold())
        if entry["name"] and key not in seen:
            seen.add(key)
            result.append(entry)
    return result


def classify_nigeria_eligibility(job: Dict[str, Any]) -> Dict[str, str]:
    """Classify Nigeria eligibility from listing evidence, never from 'Remote' alone."""
    location = str(job.get("location") or "").strip()
    description = str(job.get("description") or "")
    evidence_text = f"{location}. {description}".strip(" .")
    text = evidence_text.casefold()

    exclusion_patterns = (
        "not available in nigeria", "no nigeria applicants", "excluding nigeria",
        "cannot hire in nigeria", "can't hire in nigeria", "not eligible in nigeria",
        "nigeria is not supported", "must not be based in nigeria",
    )
    for phrase in exclusion_patterns:
        if phrase in text:
            return {
                "eligibility": "restricted",
                "eligibility_reason": f"The listing explicitly says: {phrase}.",
                "eligibility_evidence": phrase,
            }

    restricted_scope_patterns = (
        "us only", "u.s. only", "united states only", "must be based in the us",
        "must be located in the us", "only hiring in the us", "remote - us",
        "remote — us", "remote – us", "remote us", "remote (us)", "remote usa",
        "remote united states", "europe only", "uk only",
    )
    location_scope = _normalized_text(location)
    limited_regions = (
        "united states", "usa", "u s", "us", "united kingdom", "uk", "canada",
        "europe", "australia", "new zealand", "latin america", "latam",
    )
    scoped_region = next((region for region in limited_regions if f" {region} " in f" {location_scope} "), None)
    is_region_scoped_remote = location_scope.startswith("remote ") and scoped_region
    if is_region_scoped_remote:
        return {
            "eligibility": "restricted",
            "eligibility_reason": f"The remote location is scoped to {scoped_region}; Nigeria is not included in that stated region.",
            "eligibility_evidence": location,
        }
    for phrase in restricted_scope_patterns:
        if phrase in text:
            return {
                "eligibility": "restricted",
                "eligibility_reason": f"The listing limits eligibility to a different region ({phrase}).",
                "eligibility_evidence": phrase,
            }

    listed_location_patterns = (
        "nigeria", "nigerian", "lagos", "abuja", "port harcourt", "kano", "ibadan",
        "africa", "worldwide", "anywhere", "global",
    )
    listed_description_patterns = (
        "open to applicants in nigeria", "applicants based in nigeria",
        "candidates in nigeria", "we hire in nigeria", "eligible to work in nigeria",
        "based anywhere in africa", "africa wide", "remote worldwide",
        "work from anywhere", "anywhere in the world", "all countries welcome",
        "international candidates welcome",
    )
    location_evidence = next(
        (term for term in listed_location_patterns if term in location.casefold()), None
    )
    description_evidence = next(
        (phrase for phrase in listed_description_patterns if phrase in description.casefold()), None
    )
    evidence = location_evidence or description_evidence
    if evidence:
        return {
            "eligibility": "listed",
            "eligibility_reason": f"The listing names an eligible region or scope ({evidence}).",
            "eligibility_evidence": evidence,
        }

    if location:
        if "remote" in location.casefold():
            return {
                "eligibility": "unclear",
                "eligibility_reason": "Remote status alone does not establish whether applicants in Nigeria are eligible.",
                "eligibility_evidence": location,
            }
        return {
            "eligibility": "unclear",
            "eligibility_reason": "The listed location does not establish whether applicants in Nigeria are eligible.",
            "eligibility_evidence": location,
        }
    return {
        "eligibility": "unclear",
        "eligibility_reason": "No location or country eligibility is stated; remote status alone is not enough.",
        "eligibility_evidence": "",
    }


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
