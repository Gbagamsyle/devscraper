import requests, json, feedparser, re

REMOTEOK_URL = "https://remoteok.com/api"
LINKEDIN_RSS = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

DEV_KEYWORDS = [
    "frontend", "front-end", "web developer", "react", "vue",
    "angular", "javascript", "typescript", "html", "css", "ui developer",
]

NIGERIA_KEYWORDS = ["nigeria", "lagos", "abuja", "remote africa", "pan-african"]

def fetch_remoteok():
    headers = {"User-Agent": "Mozilla/5.0 (job-scraper-personal)"}
    resp = requests.get(REMOTEOK_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    jobs = []
    for job in data[1:]:  # first item is metadata
        title = (job.get("position") or "").lower()
        tags = " ".join(job.get("tags") or []).lower()
        combined = title + " " + tags
        if any(k in combined for k in DEV_KEYWORDS):
            jobs.append({
                "title": job.get("position"),
                "company": job.get("company"),
                "location": "Remote",
                "posted": job.get("date"),
                "salary": job.get("salary"),
                "apply_link": job.get("url"),
                "tags": job.get("tags", []),
                "description": job.get("description", "")[:300],
                "source": "remoteok",
            })
    return jobs

def fetch_linkedin_rss(keywords="frontend developer", location="Nigeria"):
    # LinkedIn public job RSS (no auth needed for basic search)
    url = "https://www.linkedin.com/jobs/search/?keywords={}&location={}&f_WT=2&f_TPR=r604800".format(
        requests.utils.quote(keywords),
        requests.utils.quote(location)
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    # Use LinkedIn's guest API endpoint
    api_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    params = {
        "keywords": keywords,
        "location": location,
        "start": 0,
        "count": 25,
        "f_WT": 2,          # remote
    }
    try:
        resp = requests.get(api_url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        # Parse HTML response (LinkedIn returns HTML cards)
        from html.parser import HTMLParser
        jobs = []
        # Basic regex extraction from LinkedIn HTML cards
        titles = re.findall(r'class="base-search-card__title"[^>]*>\s*([^<]+)', resp.text)
        companies = re.findall(r'class="base-search-card__subtitle"[^>]*>\s*<[^>]+>\s*([^<]+)', resp.text)
        locations = re.findall(r'class="job-search-card__location"[^>]*>\s*([^<]+)', resp.text)
        links = re.findall(r'href="(https://www\.linkedin\.com/jobs/view/[^"]+)"', resp.text)
        for i in range(min(len(titles), len(companies))):
            jobs.append({
                "title": titles[i].strip() if i < len(titles) else "",
                "company": companies[i].strip() if i < len(companies) else "",
                "location": locations[i].strip() if i < len(locations) else location,
                "apply_link": links[i] if i < len(links) else "",
                "source": "linkedin",
            })
        return jobs
    except Exception as e:
        print(f"  LinkedIn error: {e}")
        return []

LI_SEARCHES = [
    ("frontend developer", "Nigeria"),
    ("web developer", "Lagos, Nigeria"),
    ("React developer", "Nigeria"),
    ("frontend developer", "Remote"),
    ("JavaScript developer", "Africa"),
]

def run_free_scraper():
    all_jobs = []
    print("  Fetching RemoteOK...")
    try:
        rok = fetch_remoteok()
        print(f"    → {len(rok)} dev jobs")
        all_jobs.extend(rok)
    except Exception as e:
        print(f"    ✗ RemoteOK error: {e}")

    for keywords, location in LI_SEARCHES:
        print(f"  LinkedIn: {keywords} / {location}")
        try:
            li = fetch_linkedin_rss(keywords, location)
            print(f"    → {len(li)} jobs")
            all_jobs.extend(li)
        except Exception as e:
            print(f"    ✗ {e}")
    return all_jobs

if __name__ == "__main__":
    jobs = run_free_scraper()
    print(f"\nTotal: {len(jobs)} jobs")
    with open("free_jobs.json", "w") as f:
        json.dump(jobs, f, indent=2)