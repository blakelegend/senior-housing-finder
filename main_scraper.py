"""
Scheduled scraper entry point.

This is what your scheduler (Heroku Scheduler, GitHub Actions cron,
Render Cron Job, Railway scheduled task, AWS EventBridge) executes
on a regular cadence. All configuration is via environment variables —
no CLI args required.

Recommended cadence:
  - Full universe rebuild: weekly (Sundays)
  - Sequence runner:       daily  (Mon-Fri 7am local)

Environment knobs (all optional — read from .env / platform config vars):

  RUN_MODE                  "full" (collect+enrich+rank, default) | "sequence"
  TARGET_STATES             "FL,TX,CA,NY,GA"
  TARGET_LOCATIONS          "Tampa, FL;Austin, TX"
  ENRICH                    "1" / "0"            default 1
  SKIP_TRACE                "1" / "0"            default 0 (requires CONFIRM_PERMISSIBLE)
  USE_SCRAPER               "1" / "0"            default 0 (Google Maps UI — ToS risk)
  ANALYST_TOP_N             default 50
  INDEPENDENT_ONLY          "1" / "0"            default 1
  SYNC_AIRTABLE             "1" / "0"            default 0
  SYNC_NOTION               "1" / "0"            default 0
  FORCE_REBUILD             "1" / "0"            default 0 (ignore incremental staleness)
  MAX_AGE_HOURS             default 168 (1 wk)   how stale before full re-run is needed

Failures fire alerts via:
  - email (set SMTP_* and ALERT_EMAIL_*)
  - Slack webhook (SLACK_WEBHOOK_URL)
  See utils/notify.py for the env-var contract.
"""
import os
import sys
from datetime import datetime

from senior_housing_finder.utils.logging_setup import configure_logging, get_logger
from senior_housing_finder.utils.notify import with_failure_alert
from senior_housing_finder.utils.incremental import is_stale, mark_run, last_run

configure_logging()
log = get_logger("main_scraper")


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "y")


def _states() -> list[str]:
    raw = os.getenv("TARGET_STATES", "")
    return [s.strip().upper() for s in raw.split(",") if s.strip()] or None


def _locations() -> list[str]:
    raw = os.getenv("TARGET_LOCATIONS", "")
    return [s.strip() for s in raw.split(";") if s.strip()] or None


def _run_full_pipeline() -> int:
    # Incremental gate: skip if the last full run finished recently
    max_age = float(os.getenv("MAX_AGE_HOURS", "168"))
    if not _flag("FORCE_REBUILD") and not is_stale("full_pipeline", max_age_hours=max_age):
        prev = last_run("full_pipeline")
        log.info(f"full pipeline still fresh (last run {prev['last_run_iso']}); skipping")
        return 0

    from senior_housing_finder.pipeline import run as run_pipeline

    log.info(f"{datetime.utcnow().isoformat()} starting full pipeline")
    out = run_pipeline(
        states=_states(),
        locations=_locations(),
        enrich=_flag("ENRICH", default=True),
        top=int(os.getenv("TOP_N", "200")),
        skip_google=_flag("SKIP_GOOGLE", default=False),
        use_scraper=_flag("USE_SCRAPER", default=False),
        independent_only=_flag("INDEPENDENT_ONLY", default=True),
        enrich_tired_signals=_flag("ENRICH_TIRED_SIGNALS", default=True),
        enrich_tax=_flag("ENRICH_TAX", default=True),
        enrich_skip_trace=_flag("SKIP_TRACE", default=False),
        cluster_eps_km=float(os.getenv("CLUSTER_EPS_KM", "25.0")),
        enrich_market_demand=_flag("ENRICH_MARKET_DEMAND", default=True),
        generate_analyst_report=_flag("GENERATE_ANALYST_REPORT", default=True),
        analyst_report_top_n=int(os.getenv("ANALYST_TOP_N", "50")),
    )
    log.info(f"pipeline output: {out}")
    mark_run("full_pipeline", status="ok", detail=str(out))
    return 0


def _run_sequence_only() -> int:
    """Just advance pending sequence touches — cheap to run daily."""
    from senior_housing_finder.workers.sequence_runner import run_once

    log.info(f"{datetime.utcnow().isoformat()} advancing sequences")
    summary = run_once(batch_size=int(os.getenv("BATCH_SIZE", "200")))
    log.info(f"sequence summary: {summary}")
    mark_run("sequence_runner", row_count=summary.get("emails", 0) + summary.get("linkedin", 0) + summary.get("calls", 0), detail=str(summary))
    return 0


def _sync_remote_crm() -> None:
    """Push to Airtable / Notion after a full run."""
    if _flag("SYNC_AIRTABLE"):
        try:
            from senior_housing_finder.crm import LeadPipeline, AirtableSync
            n = AirtableSync().push_leads(LeadPipeline().list_leads(limit=2000))
            log.info(f"pushed {n} leads to Airtable")
        except Exception as e:
            log.exception(f"airtable sync failed: {e}")

    if _flag("SYNC_NOTION"):
        try:
            from senior_housing_finder.crm import LeadPipeline, NotionSync
            n = NotionSync().push_leads(LeadPipeline().list_leads(limit=2000))
            log.info(f"pushed {n} leads to Notion")
        except Exception as e:
            log.exception(f"notion sync failed: {e}")


def _entry() -> int:
    mode = os.getenv("RUN_MODE", "full").lower()
    if mode == "sequence":
        return _run_sequence_only()
    rc = _run_full_pipeline()
    _sync_remote_crm()
    return rc


def main() -> int:
    return with_failure_alert(_entry, run_label=f"scraper-{os.getenv('RUN_MODE', 'full')}")


if __name__ == "__main__":
    sys.exit(main())
