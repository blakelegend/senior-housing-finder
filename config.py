"""
Central configuration loader.

Reads from .env (via python-dotenv) and falls back to sensible defaults.
All other modules should import from here rather than reading os.environ directly.
"""
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

# Load .env from project root if present
PROJECT_ROOT = Path(__file__).parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class Config:
    # API credentials
    google_maps_api_key: str = os.getenv("GOOGLE_MAPS_API_KEY", "")
    hunter_io_api_key: str = os.getenv("HUNTER_IO_API_KEY", "")
    apollo_api_key: str = os.getenv("APOLLO_API_KEY", "")
    proxycurl_api_key: str = os.getenv("PROXYCURL_API_KEY", "")

    # Rate limiting (requests per second)
    default_rps: float = float(os.getenv("DEFAULT_RPS", "2.0"))
    google_places_rps: float = float(os.getenv("GOOGLE_PLACES_RPS", "10.0"))

    # Paths
    output_dir: Path = field(default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "./data/output")))
    cache_dir: Path = field(default_factory=lambda: Path(os.getenv("CACHE_DIR", "./data/cache")))

    # Database — defaults to SQLite. Set DATABASE_URL to a postgres:// URL
    # (Render and Heroku set this automatically when you attach a Postgres
    # addon) and the CRM module will use it instead.
    database_url: str = os.getenv("DATABASE_URL", "")

    # Targeting
    target_states: List[str] = field(default_factory=lambda: os.getenv("TARGET_STATES", "FL").split(","))
    min_beds: int = int(os.getenv("MIN_BEDS", "20"))
    max_beds: int = int(os.getenv("MAX_BEDS", "120"))
    min_age_years: int = int(os.getenv("MIN_AGE_YEARS", "5"))
    max_age_years: int = int(os.getenv("MAX_AGE_YEARS", "25"))

    # Proxy pool — split comma list, strip empties
    proxy_pool: List[str] = field(default_factory=lambda: [
        p.strip() for p in os.getenv("PROXY_POOL", "").split(",") if p.strip()
    ])

    # Headless browser
    headless: bool = os.getenv("HEADLESS", "true").lower() in ("1", "true", "yes")
    browser_timeout_ms: int = int(os.getenv("BROWSER_TIMEOUT_MS", "30000"))

    # CRM sync
    airtable_api_key: str = os.getenv("AIRTABLE_API_KEY", "")
    airtable_base_id: str = os.getenv("AIRTABLE_BASE_ID", "")
    airtable_table_leads: str = os.getenv("AIRTABLE_TABLE_LEADS", "Leads")
    airtable_table_activities: str = os.getenv("AIRTABLE_TABLE_ACTIVITIES", "Activities")
    notion_api_key: str = os.getenv("NOTION_API_KEY", "")
    notion_database_leads: str = os.getenv("NOTION_DATABASE_LEADS", "")

    # Sender identity for outreach templates
    sender_name: str = os.getenv("SENDER_NAME", "")
    sender_title: str = os.getenv("SENDER_TITLE", "Managing Partner")
    sender_firm: str = os.getenv("SENDER_FIRM", "Acme Senior Housing Partners")
    sender_email: str = os.getenv("SENDER_EMAIL", "")
    sender_phone: str = os.getenv("SENDER_PHONE", "")
    sender_calendar_link: str = os.getenv("SENDER_CALENDAR_LINK", "")

    # Property data
    regrid_api_key: str = os.getenv("REGRID_API_KEY", "")
    reportall_api_key: str = os.getenv("REPORTALL_API_KEY", "")
    attom_api_key: str = os.getenv("ATTOM_API_KEY", "")

    # Skip tracing
    endato_api_key: str = os.getenv("ENDATO_API_KEY", "")
    endato_api_name: str = os.getenv("ENDATO_API_NAME", "")
    batch_skip_tracing_api_key: str = os.getenv("BATCH_SKIP_TRACING_API_KEY", "")

    # Census
    census_api_key: str = os.getenv("CENSUS_API_KEY", "")

    # Direct mail
    lob_api_key: str = os.getenv("LOB_API_KEY", "")
    return_address: dict = field(default_factory=lambda: {
        "name": os.getenv("RETURN_ADDRESS_NAME", ""),
        "street": os.getenv("RETURN_ADDRESS_STREET", ""),
        "city": os.getenv("RETURN_ADDRESS_CITY", ""),
        "state": os.getenv("RETURN_ADDRESS_STATE", ""),
        "zip": os.getenv("RETURN_ADDRESS_ZIP", ""),
    })

    def __post_init__(self):
        # Ensure output paths exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)


CONFIG = Config()
