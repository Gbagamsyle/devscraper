import os, requests, json
from dotenv import load_dotenv

load_dotenv()
SERPER_KEY = os.getenv("SERPER_KEY")

QUERIES = [
    "frontend developer Nigeria",
    "web developer remote Nigeria",
    "React developer Lagos Abuja",
    "frontend developer remote Africa",
    "JavaScript developer Nigeria",
]

GLOBAL_QUERIES = [
    "frontend developer remote",
    "web developer remote Europe",
    "React developer remote USA",
]

def search_serper_jobs(query, num=20):
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
    resp = requests.post("https://google.serper.dev/search", headers=headers, json=payload)
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

def run_google_scraper(include_global=False):
    all_jobs = []
    queries = QUERIES + (GLOBAL_QUERIES if include_global else [])
    for q in queries:
        print(f"  Searching: {q}")
        try:
            jobs = search_serper_jobs(q)
            all_jobs.extend(jobs)
            print(f"    → {len(jobs)} results")
        except Exception as e:
            print(f"    ✗ Error: {e}")

    seen = set()
    unique = []
    for j in all_jobs:
        key = (str(j.get("title", "")).lower(), str(j.get("company", "")).lower())
        if key not in seen:
            seen.add(key)
            unique.append(j)
    return unique

if __name__ == "__main__":
    jobs = run_google_scraper(include_global=True)
    print(f"\nTotal unique jobs: {len(jobs)}")
    with open("google_jobs.json", "w") as f:
        json.dump(jobs, f, indent=2)