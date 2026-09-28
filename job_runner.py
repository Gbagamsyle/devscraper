"""Main job scraper orchestrator with concurrent execution."""
import json
import csv
import os
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

from colorama import Fore, Style, init
from config import OUTPUT_DIR, MAX_WORKERS, ROLE_PROFILES, ROLE_SEARCH_LOCATIONS
from utils import logger, deduplicate_jobs, classify_nigeria_eligibility

init(autoreset=True)

# Import scrapers
from google_jobs import run_google_scraper
from twitter_jobs import run_twitter_scraper
from free_boards import run_free_scraper
from scrapers import run_alternative_scrapers


CONFIG = {
    "include_global": True,    # set False for Nigeria-only
    "sources": {
        "google": True,
        "twitter": True,       # needs TWITTER_BEARER in .env
        "free_boards": True,   # RemoteOK + LinkedIn, no key needed
        "alternative": False,  # Jobicy + Remotive (optional)
    },
    "output_dir": OUTPUT_DIR,
}


def tag_nigeria(job: Dict[str, Any]) -> Dict[str, Any]:
    """Treat Nigeria as relevant only when eligibility evidence says it is listed."""
    eligibility = classify_nigeria_eligibility(job)
    job.update(eligibility)
    job["nigeria_relevant"] = eligibility["eligibility"] == "listed"
    return job


def matches_role(job: Dict[str, Any], role: str) -> bool:
    """Require role evidence in the job title, tags, or description."""
    profile = ROLE_PROFILES.get(role)
    if not profile:
        return False
    tags = job.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    evidence = " ".join(
        str(value or "")
        for value in [job.get("title"), *tags, job.get("description")]
    ).casefold()
    return any(term.casefold() in evidence for term in profile["match_terms"])


def filter_jobs_for_role(jobs: List[Dict[str, Any]], role: str) -> List[Dict[str, Any]]:
    """Apply the final selected-role check to every scraper result."""
    return [job for job in jobs if matches_role(job, role)]


def sort_by_eligibility(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Order eligible-listed jobs first and explicitly restricted jobs last."""
    eligibility_order = {"listed": 0, "unclear": 1, "restricted": 2}
    return sorted(jobs, key=lambda job: eligibility_order.get(job.get("eligibility"), 1))


def build_google_queries(role: str) -> List[str]:
    """Build the deliberately capped three-query Google budget per role."""
    if role not in ROLE_PROFILES:
        raise ValueError(f"Unknown role: {role}")
    profile = ROLE_PROFILES[role]
    scopes = ROLE_SEARCH_LOCATIONS
    return [
        f"{term} jobs {scope}"
        for term, scope in zip(profile["queries"], scopes)
    ]


def save_results(jobs: List[Dict[str, Any]], output_dir: str, role: str = "frontend") -> tuple:
    """Save results to JSON and CSV files."""
    output_dir = os.path.join(output_dir, role)
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    json_path = f"{output_dir}/jobs_{ts}.json"
    csv_path = f"{output_dir}/jobs_{ts}.csv"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, default=str)

    fields = [
        "title", "company", "location", "posted", "salary",
        "apply_link", "source", "sources", "role", "nigeria_relevant",
        "eligibility", "eligibility_reason", "eligibility_evidence", "description"
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        csv_jobs = []
        for job in jobs:
            row = dict(job)
            row["sources"] = json.dumps(row.get("sources", []), ensure_ascii=False)
            csv_jobs.append(row)
        w.writerows(csv_jobs)

    logger.info(f"Results saved: {json_path} | {csv_path}")
    return json_path, csv_path


def run_scrapers_concurrent(cfg: Dict[str, Any], role: str = "frontend") -> List[Dict[str, Any]]:
    """Run all enabled scrapers concurrently."""
    all_jobs = []
    
    scrapers = []
    if cfg["sources"]["google"]:
        _queries = build_google_queries(role)
        scrapers.append(("Google Jobs", lambda: run_google_scraper(cfg["include_global"], queries=_queries)))
    if cfg["sources"]["twitter"]:
        scrapers.append(("Twitter/X", lambda: run_twitter_scraper(cfg["include_global"], role=role)))
    if cfg["sources"]["free_boards"]:
        scrapers.append(("Free Boards", lambda: run_free_scraper(role=role)))
    if cfg["sources"].get("alternative"):
        scrapers.append(("Alternative Sources", lambda: run_alternative_scrapers()))
    
    logger.info(f"Running {len(scrapers)} scrapers concurrently...")
    print(f"\n{Fore.CYAN}Running {len(scrapers)} job scrapers...{Style.RESET_ALL}")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(func): name for name, func in scrapers}
        
        for future in as_completed(futures):
            scraper_name = futures[future]
            try:
                jobs = future.result()
                all_jobs.extend(jobs)
                print(f"{Fore.GREEN}✓{Style.RESET_ALL} {scraper_name}: {len(jobs)} jobs")
                logger.info(f"{scraper_name}: {len(jobs)} jobs")
            except Exception as e:
                print(f"{Fore.RED}✗{Style.RESET_ALL} {scraper_name}: {e}")
                logger.error(f"{scraper_name} failed: {e}")
    
    return all_jobs


def main(role: str = "frontend"):
    """Main orchestrator."""
    if role not in ROLE_PROFILES:
        raise ValueError(f"Unknown role: {role}")
    logger.info("=" * 60)
    logger.info(f"Starting job scraper for role: {role}")
    
    cfg = CONFIG
    
    # Run all scrapers concurrently
    all_jobs = run_scrapers_concurrent(cfg, role=role)
    
    # Reject cross-category search contamination before users see saved jobs.
    logger.info(f"Processing {len(all_jobs)} jobs...")
    role_matched_jobs = filter_jobs_for_role(all_jobs, role)
    logger.info(f"Role validation ({role}): {len(all_jobs)} → {len(role_matched_jobs)} jobs")
    all_jobs = role_matched_jobs
    for job in all_jobs:
        tag_nigeria(job)
        job["role"] = role
    all_jobs = deduplicate_jobs(all_jobs)

    # Explicitly restricted listings must never be promoted by incidental text.
    all_jobs = sort_by_eligibility(all_jobs)
    
    listed_count = sum(1 for j in all_jobs if j.get("eligibility") == "listed")
    unclear_count = sum(1 for j in all_jobs if j.get("eligibility") == "unclear")
    restricted_count = sum(1 for j in all_jobs if j.get("eligibility") == "restricted")
    
    print(f"\n{Fore.YELLOW}Summary:{Style.RESET_ALL}")
    print(f"  Total unique jobs : {len(all_jobs)}")
    print(f"  Eligibility listed: {listed_count}")
    print(f"  Eligibility unclear: {unclear_count}")
    print(f"  Restricted        : {restricted_count}")
    
    # Save results
    json_path, csv_path = save_results(all_jobs, cfg["output_dir"], role=role)
    
    print(f"\n{Fore.GREEN}Saved:{Style.RESET_ALL}")
    print(f"  JSON → {json_path}")
    print(f"  CSV  → {csv_path}")
    
    logger.info(f"Complete: {len(all_jobs)} jobs ({listed_count} listed for Nigeria)")
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Refresh saved job listings.")
    parser.add_argument("--role", choices=ROLE_PROFILES, default="frontend", help="Role snapshot to refresh")
    parser.add_argument("--all-roles", action="store_true", help="Refresh every role snapshot in sequence")
    args = parser.parse_args()
    selected_roles = ROLE_PROFILES if args.all_roles else [args.role]
    for selected_role in selected_roles:
        main(role=selected_role)
