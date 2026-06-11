import requests, json

def fetch_jobicy():
    url = "https://jobicy.com/api/v2/remote-jobs"
    params = {
        "count": 50,
        "industry": "engineering",
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    jobs = []
    for job in data.get("jobs", []):
        title = (job.get("jobTitle") or "").lower()
        tags = " ".join(job.get("jobIndustry") or []).lower()
        if any(k in title + tags for k in ["front", "react", "vue", "javascript", "typescript", "web dev", "ui "]):
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
    return jobs

def fetch_remotive():
    url = "https://remotive.com/api/remote-jobs"
    params = {"category": "software-dev", "limit": 50}
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    jobs = []
    for job in data.get("jobs", []):
        title = (job.get("title") or "").lower()
        if any(k in title for k in ["front", "react", "vue", "javascript", "typescript", "web dev", "ui "]):
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
    return jobs

def run_twitter_scraper(include_global=False):
    all_jobs = []

    print("  Fetching Jobicy...")
    try:
        jobs = fetch_jobicy()
        print(f"    → {len(jobs)} jobs")
        all_jobs.extend(jobs)
    except Exception as e:
        print(f"    ✗ Jobicy error: {e}")

    print("  Fetching Remotive...")
    try:
        jobs = fetch_remotive()
        print(f"    → {len(jobs)} jobs")
        all_jobs.extend(jobs)
    except Exception as e:
        print(f"    ✗ Remotive error: {e}")

    return all_jobs