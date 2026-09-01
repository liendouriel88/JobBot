"""
Job Seeker Bot — Uriel's version
---------------------------------
Checks SerpApi's Google Jobs engine once a day for new postings across
a fixed list of saved searches, filters them (remote OR based in
Córdoba/Alta Gracia, and excludes US-residency-required / teaching /
scam-pattern listings), and sends a single Telegram digest message
listing anything new.

Designed to run on a schedule via GitHub Actions (see
.github/workflows/daily_check.yml).
"""

import os
import json
import hashlib
import html
import requests

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

SERPAPI_KEY = os.environ["SERPAPI_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

STATE_FILE = "seen_jobs.json"

# Local, in-person jobs only count if they're based in one of these cities.
# Remote jobs are accepted from anywhere, so they don't need a location match.
ALLOWED_LOCAL_CITIES = ["cordoba", "córdoba", "alta gracia"]

# --- Global exclusions, applied to every search regardless of category ---

# Teaching/language-instruction roles that occasionally slip into results
# for unrelated queries.
TEACHING_EXCLUDE_WORDS = [
    "german teacher", "teach german", "german language teacher",
    "language instructor", "language tutor", "esl teacher",
    "teaching german", "german tutor", "spanish teacher", "english teacher",
]

# Listings that say "remote" but actually require you to be located in
# (or a citizen/resident of) the US — not genuinely open to Argentina.
US_ONLY_EXCLUDE_WORDS = [
    "must be located in the united states", "must reside in the united states",
    "u.s. residents only", "us residents only", "must be a us citizen",
    "must be a u.s. citizen", "authorized to work in the united states",
    "based in the usa", "based in the us", "eligible to work in the united states",
    "us based only", "within the united states", "us time zones only",
    "must be based in the u.s", "candidates must be located in the us",
]

# Common phrasing patterns in scam/fake job listings.
SCAM_EXCLUDE_WORDS = [
    "wire transfer", "western union", "processing fee", "registration fee",
    "send us your bank details", "whatsapp only", "telegram to apply",
    "no interview required", "start immediately no experience",
    "pay upfront", "buy your own equipment", "cash app", "bitcoin payment",
    "crypto payment", "training fee", "purchase a starter kit",
    "reply with your whatsapp", "text hr at", "earn $$$ from home",
    "no experience needed unlimited earning",
]

GLOBAL_EXCLUDE_WORDS = (
    TEACHING_EXCLUDE_WORDS + US_ONLY_EXCLUDE_WORDS + SCAM_EXCLUDE_WORDS
)

# Companies to always skip, regardless of how good the listing looks.
# Matching is case-insensitive and matches partial names too.
BLOCKED_COMPANIES = []

SEARCHES = [
    {
        "name": "Care Coordinator",
        "query": "care coordinator remote",
        "exclude_words": [],
        "skill_keywords": [
            "care coordination", "patient scheduling", "referrals",
            "ehr", "eclinicalworks", "patient records", "intake",
            "bilingual", "spanish", "confidentiality", "hipaa",
        ],
    },
    {
        "name": "Intake Specialist",
        "query": "intake specialist remote healthcare",
        "exclude_words": [],
        "skill_keywords": [
            "intake", "patient intake", "scheduling", "ehr",
            "eclinicalworks", "medical forms", "documentation",
            "bilingual", "spanish", "confidentiality",
        ],
    },
    {
        "name": "Medical Receptionist",
        "query": "medical receptionist remote",
        "exclude_words": [],
        "skill_keywords": [
            "medical receptionist", "scheduling", "appointment coordination",
            "ehr", "front desk", "patient communication", "insurance",
            "billing", "bilingual", "spanish", "data entry",
        ],
    },
    {
        "name": "Dental Receptionist",
        "query": "dental receptionist remote",
        "exclude_words": [],
        "skill_keywords": [
            "dental receptionist", "scheduling", "appointment coordination",
            "front desk", "patient communication", "insurance verification",
            "billing", "bilingual", "spanish", "data entry",
        ],
    },
]


# ---------------------------------------------------------------------------
# STATE (which jobs we've already alerted on)
# ---------------------------------------------------------------------------

def load_seen_ids():
    if not os.path.exists(STATE_FILE):
        return set()
    with open(STATE_FILE, "r") as f:
        return set(json.load(f))


def save_seen_ids(seen_ids):
    with open(STATE_FILE, "w") as f:
        json.dump(sorted(seen_ids), f, indent=2)


def job_unique_id(job):
    """SerpApi usually gives a job_id, but fall back to a hash if missing."""
    if job.get("job_id"):
        return job["job_id"]
    raw = f"{job.get('title', '')}|{job.get('company_name', '')}|{job.get('location', '')}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# FILTERING
# ---------------------------------------------------------------------------

def is_remote(job):
    ext = job.get("detected_extensions", {}) or {}
    if ext.get("work_from_home"):
        return True
    text = f"{job.get('title', '')} {job.get('location', '')}".lower()
    return "remote" in text or "remoto" in text or "trabajo desde casa" in text


def is_local_match(job):
    location = (job.get("location") or "").lower()
    return any(city in location for city in ALLOWED_LOCAL_CITIES)


def contains_excluded_word(job, exclude_words):
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    all_excluded = list(exclude_words) + GLOBAL_EXCLUDE_WORDS
    return any(word in text for word in all_excluded)


def is_blocked_company(job):
    company = (job.get("company_name") or "").lower()
    return any(blocked in company for blocked in BLOCKED_COMPANIES)


def passes_filters(job, exclude_words):
    if is_blocked_company(job):
        return False
    if contains_excluded_word(job, exclude_words):
        return False
    return is_remote(job) or is_local_match(job)


def matching_skills(job, skill_keywords):
    """Return the subset of skill_keywords that appear in the job's
    title/description, so we can flag postings that line up with your
    resume."""
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    return [kw for kw in skill_keywords if kw in text]


# ---------------------------------------------------------------------------
# SERPAPI
# ---------------------------------------------------------------------------

def fetch_jobs(query):
    params = {
        "engine": "google_jobs",
        "q": query,
        "hl": "es",
        "api_key": SERPAPI_KEY,
    }
    resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("jobs_results", [])


# ---------------------------------------------------------------------------
# TELEGRAM
# ---------------------------------------------------------------------------

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # Telegram caps messages at 4096 chars. Split on line breaks (never
    # mid-line) so a chunk boundary can't fall inside a <b>...</b> pair.
    lines = text.split("\n")
    chunks = []
    current = ""
    for line in lines:
        candidate = current + ("\n" if current else "") + line
        if len(candidate) > 4000 and current:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)

    for chunk in chunks:
        resp = requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=30)
        if not resp.ok:
            print(f"[telegram error] status={resp.status_code} body={resp.text}")
        resp.raise_for_status()


def get_employment_type(job):
    """SerpApi returns this as 'schedule_type' inside detected_extensions,
    e.g. 'Full-time', 'Part-time', 'Contractor', 'Internship'. Not every
    listing has it filled in."""
    ext = job.get("detected_extensions", {}) or {}
    return ext.get("schedule_type", "Type not listed")


def format_job(job, matched_skills=None):
    title = html.escape(job.get("title") or "Untitled")
    company = html.escape(job.get("company_name") or "")
    location = html.escape(job.get("location") or "")
    employment_type = html.escape(get_employment_type(job))
    link = None
    for opt in job.get("apply_options", []) or []:
        if opt.get("link"):
            link = opt["link"]
            break
    link = link or job.get("share_link", "")

    star = "⭐ " if matched_skills else ""
    subtitle = " — ".join(part for part in [company, location] if part)
    line = f"• {star}<b>{title}</b> [{employment_type}]"
    if subtitle:
        line += f"\n  {subtitle}"
    if matched_skills:
        line += f"\n  Matches: {', '.join(matched_skills)}"
    if link:
        line += f"\n  {link}"
    return line


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    seen_ids = load_seen_ids()
    new_seen_ids = set(seen_ids)
    digest_sections = []
    total_new = 0

    for search in SEARCHES:
        try:
            jobs = fetch_jobs(search["query"])
        except requests.RequestException as e:
            print(f"[warn] search failed for '{search['name']}': {e}")
            continue

        new_jobs = []  # list of (job, matched_skills) tuples
        for job in jobs:
            uid = job_unique_id(job)
            if uid in seen_ids:
                continue
            if not passes_filters(job, search["exclude_words"]):
                continue
            matched = matching_skills(job, search.get("skill_keywords", []))
            new_jobs.append((job, matched))
            new_seen_ids.add(uid)

        if new_jobs:
            # Starred (skill-matched) jobs first, most matches at the top.
            new_jobs.sort(key=lambda pair: len(pair[1]), reverse=True)

            total_new += len(new_jobs)
            section = f"<b>{search['name']}</b> ({len(new_jobs)} new)\n"
            section += "\n\n".join(format_job(j, m) for j, m in new_jobs)
            digest_sections.append(section)

    if digest_sections:
        message = f"💼 <b>Job Digest — {total_new} new posting(s)</b>\n\n"
        message += "\n\n---\n\n".join(digest_sections)
        send_telegram_message(message)
        print(f"Sent digest with {total_new} new job(s).")
    else:
        print("No new jobs today.")

    save_seen_ids(new_seen_ids)


if __name__ == "__main__":
    main()