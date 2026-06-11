import json, csv, os, sys
from datetime import datetime
from colorama import Fore, Style, init

init(autoreset=True)

# Import your scrapers
from google_jobs import run_google_scraper
from twitter_jobs import run_twitter_scraper
from free_boards import run_free_scraper

CONFIG = {
    "include_global": True,    # set False for Nigeria-only
    "sources": {
        "google": True,
        "twitter": True,       # needs TWITTER_BEARER in .env
        "free_boards": True,   # RemoteOK + LinkedIn, no key needed
    },
    "output_dir": "./output",
}

NIGERIA_BOOST_KEYWORDS = [
    "nigeria", "lagos", "abuja", "port harcourt", "kano",
    "ibadan", "remote africa", "african", "naira",
]

def tag_nigeria(job):
    text = " ".join([
        str(job.get("title") or ""),
        str(job.get("location") or ""),
        str(job.get("description") or ""),
    ]).lower()
    job["nigeria_relevant"] = any(k in text for k in NIGERIA_BOOST_KEYWORDS)
    return job

def deduplicate(jobs):
    seen, out = set(), []
    for j in jobs:
        key = (
            str(j.get("title", "")).lower().strip(),
            str(j.get("company", "")).lower().strip(),
        )
        if key not in seen and key != ("", ""):
            seen.add(key)
            out.append(j)
    return out

def save_results(jobs, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")

    json_path = f"{output_dir}/jobs_{ts}.json"
    csv_path  = f"{output_dir}/jobs_{ts}.csv"

    with open(json_path, "w") as f:
        json.dump(jobs, f, indent=2, default=str)

    fields = ["title","company","location","posted","salary",
              "apply_link","source","nigeria_relevant","description"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(jobs)

    print(f"\n{Fore.GREEN}Saved:{Style.RESET_ALL}")
    print(f"  JSON → {json_path}")
    print(f"  CSV  → {csv_path}")
    return json_path, csv_path

def main():
    all_jobs = []
    cfg = CONFIG

    if cfg["sources"]["google"]:
        print(f"\n{Fore.CYAN}[1/3] Google Jobs (SerpAPI){Style.RESET_ALL}")
        jobs = run_google_scraper(include_global=cfg["include_global"])
        print(f"  Google total: {len(jobs)}")
        all_jobs.extend(jobs)

    if cfg["sources"]["twitter"]:
        print(f"\n{Fore.CYAN}[2/3] Twitter / X{Style.RESET_ALL}")
        jobs = run_twitter_scraper(include_global=cfg["include_global"])
        print(f"  Twitter total: {len(jobs)}")
        all_jobs.extend(jobs)

    if cfg["sources"]["free_boards"]:
        print(f"\n{Fore.CYAN}[3/3] Free Boards (RemoteOK + LinkedIn){Style.RESET_ALL}")
        jobs = run_free_scraper()
        print(f"  Free boards total: {len(jobs)}")
        all_jobs.extend(jobs)

    # Tag & deduplicate
    all_jobs = [tag_nigeria(j) for j in all_jobs]
    all_jobs = deduplicate(all_jobs)

    # Sort: Nigeria-relevant first
    all_jobs.sort(key=lambda x: (not x.get("nigeria_relevant", False)))

    ng_count = sum(1 for j in all_jobs if j.get("nigeria_relevant"))
    print(f"\n{Fore.YELLOW}Summary:{Style.RESET_ALL}")
    print(f"  Total unique jobs : {len(all_jobs)}")
    print(f"  Nigeria-relevant  : {ng_count}")
    print(f"  Global/remote     : {len(all_jobs) - ng_count}")

    save_results(all_jobs, cfg["output_dir"])

if __name__ == "__main__":
    main()