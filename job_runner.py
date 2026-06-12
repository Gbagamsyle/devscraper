"""Main job scraper orchestrator with concurrent execution."""
import json
import csv
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

from colorama import Fore, Style, init
from config import OUTPUT_DIR, NIGERIA_BOOST_KEYWORDS, MAX_WORKERS, COUNTRIES, BASE_QUERIES, GLOBAL_QUERIES
from utils import logger, deduplicate_jobs

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
    """Tag job as Nigeria-relevant based on keywords."""
    text = " ".join([
        str(job.get("title") or ""),
        str(job.get("location") or ""),
        str(job.get("description") or ""),
    ]).lower()
    job["nigeria_relevant"] = any(k in text for k in NIGERIA_BOOST_KEYWORDS)
    return job


def save_results(jobs: List[Dict[str, Any]], output_dir: str) -> tuple:
    """Save results to JSON and CSV files."""
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")

    json_path = f"{output_dir}/jobs_{ts}.json"
    csv_path = f"{output_dir}/jobs_{ts}.csv"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, default=str)

    fields = [
        "title", "company", "location", "posted", "salary",
        "apply_link", "source", "nigeria_relevant", "description"
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(jobs)

    logger.info(f"Results saved: {json_path} | {csv_path}")
    return json_path, csv_path


def run_scrapers_concurrent(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Run all enabled scrapers concurrently."""
    all_jobs = []
    
    scrapers = []
    if cfg["sources"]["google"]:
        # Build country-specific queries from BASE_QUERIES + COUNTRIES
        queries = []
        for country in COUNTRIES:
            for base in BASE_QUERIES:
                queries.append(f"{base} {country}")
        # include global queries optionally
        if cfg.get("include_global"):
            queries.extend(GLOBAL_QUERIES)
        # Capture queries in a local variable for the lambda
        _queries = list(queries)
        scrapers.append(("Google Jobs", lambda: run_google_scraper(cfg["include_global"], queries=_queries)))
    if cfg["sources"]["twitter"]:
        scrapers.append(("Twitter/X", lambda: run_twitter_scraper(cfg["include_global"])))
    if cfg["sources"]["free_boards"]:
        scrapers.append(("Free Boards", lambda: run_free_scraper()))
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


def main():
    """Main orchestrator."""
    logger.info("=" * 60)
    logger.info("Starting job scraper...")
    
    cfg = CONFIG
    
    # Run all scrapers concurrently
    all_jobs = run_scrapers_concurrent(cfg)
    
    # Post-process: tag & deduplicate
    logger.info(f"Processing {len(all_jobs)} jobs...")
    all_jobs = [tag_nigeria(j) for j in all_jobs]
    all_jobs = deduplicate_jobs(all_jobs)
    
    # Sort: Nigeria-relevant first
    all_jobs.sort(key=lambda x: (not x.get("nigeria_relevant", False)))
    
    ng_count = sum(1 for j in all_jobs if j.get("nigeria_relevant"))
    
    print(f"\n{Fore.YELLOW}Summary:{Style.RESET_ALL}")
    print(f"  Total unique jobs : {len(all_jobs)}")
    print(f"  Nigeria-relevant  : {ng_count}")
    print(f"  Global/remote     : {len(all_jobs) - ng_count}")
    
    # Save results
    json_path, csv_path = save_results(all_jobs, cfg["output_dir"])
    
    print(f"\n{Fore.GREEN}Saved:{Style.RESET_ALL}")
    print(f"  JSON → {json_path}")
    print(f"  CSV  → {csv_path}")
    
    logger.info(f"Complete: {len(all_jobs)} jobs ({ng_count} Nigeria-relevant)")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
