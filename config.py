"""Configuration for job scraper."""
import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
SERPER_KEY = os.getenv("SERPER_KEY", "")
TWITTER_BEARER = os.getenv("TWITTER_BEARER", "")
OWNER_TOKEN = os.getenv("OWNER_TOKEN", "")
APP_SECRET_KEY = os.getenv("APP_SECRET_KEY", "")

# One role is scraped per refresh; role-specific queries avoid multiplying every
# search across all roles and keep results isolated by role.
ROLE_PROFILES = {
    "frontend": {
        "label": "Frontend",
        "queries": ["frontend developer", "frontend engineer", "React developer"],
        "match_terms": ["frontend", "front-end", "react", "vue", "angular", "web developer"],
    },
    "backend": {
        "label": "Backend",
        "queries": ["backend developer", "backend engineer", "API developer"],
        "match_terms": ["backend", "back-end", "server-side", "api developer", "backend engineer"],
    },
    "full-stack": {
        "label": "Full-stack",
        "queries": ["full stack developer", "full-stack engineer", "full stack web developer"],
        "match_terms": ["full stack", "full-stack"],
    },
    "mobile": {
        "label": "Mobile",
        "queries": ["mobile app developer", "Android developer", "iOS developer"],
        "match_terms": ["mobile", "android", "ios", "react native", "flutter"],
    },
    "data": {
        "label": "Data",
        "queries": ["data engineer", "data analyst", "machine learning engineer"],
        "match_terms": ["data engineer", "data analyst", "data scientist", "machine learning", "ml engineer", "analytics engineer", "bi analyst"],
    },
    "product-design": {
        "label": "Product design",
        "queries": ["product designer", "UI UX designer", "UX designer"],
        "match_terms": ["product designer", "ux designer", "ui designer", "ui/ux", "ux/ui", "interaction designer"],
    },
}

ROLE_SEARCH_LOCATIONS = ["Nigeria", "Africa", "remote worldwide"]
LINKEDIN_SEARCH_LOCATIONS = ["Nigeria", "Remote"]

# Search queries
NIGERIA_QUERIES = [
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

# Countries to include in broader scraping (adds country-specific queries)
COUNTRIES = ["Nigeria", "Kenya", "Ghana" , "South Africa", "Egypt", "Remote", "Africa", "Lagos", "Abuja", "Port Harcourt", "Kano", "Ibadan", "United States", "United Kingdom", "Germany", "France", "India", "Philippines"]

# Base role queries used to generate country-specific searches
BASE_QUERIES = [
    "frontend developer",
    "web developer",
    "React developer",
    "JavaScript developer",
    "website", "UI developer",
    
]

LINKEDIN_SEARCHES = [
    ("frontend developer", "Nigeria"),
    ("web developer", "Lagos, Nigeria"),
    ("React developer", "Nigeria"),
    ("frontend developer", "Remote"),
    ("JavaScript developer", "Africa"),
]

DEV_KEYWORDS = [
    "frontend", "front-end", "web developer", "react", "vue",
    "angular", "javascript", "typescript", "html", "css", "ui developer",
]

# Output
OUTPUT_DIR = "./output"
LOG_DIR = "./logs"

# Scraper config
TIMEOUT = 15
RETRIES = 3
RETRY_BACKOFF = 1.5  # exponential backoff multiplier

# Concurrency
MAX_WORKERS = 4  # concurrent API calls
