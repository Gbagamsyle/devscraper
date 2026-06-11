"""Configuration for job scraper."""
import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
SERPER_KEY = os.getenv("SERPER_KEY", "")
TWITTER_BEARER = os.getenv("TWITTER_BEARER", "")

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

NIGERIA_BOOST_KEYWORDS = [
    "nigeria", "lagos", "abuja", "port harcourt", "kano",
    "ibadan", "remote africa", "african", "naira",
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
