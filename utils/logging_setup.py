"""
Centralized logging setup.

Why this exists: print() goes to stdout and gets lost on most hosts. We want:
- One configured root logger with consistent format
- File handler with rotation (10MB × 5 files = 50MB retention)
- Stdout handler so Heroku/Render/Railway log scrapers still see everything
- Log level controllable via LOG_LEVEL env var (default INFO; set DEBUG when troubleshooting)

Usage in any module:
    from senior_housing_finder.utils.logging_setup import get_logger
    log = get_logger(__name__)
    log.info("pipeline started")

Call `configure_logging()` once at the entry point (main_scraper, dashboard,
pipeline CLI). It's idempotent.
"""
import logging
import logging.handlers
import os
import sys
from pathlib import Path

from ..config import CONFIG


_CONFIGURED = False
_DEFAULT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s — %(message)s"


def configure_logging(
    level: str = None,
    log_file: Path = None,
    fmt: str = _DEFAULT_FORMAT,
) -> None:
    """Set up the root logger. Safe to call multiple times."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    log_file = log_file or (CONFIG.output_dir / "logs" / "pipeline.log")
    log_file.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level, logging.INFO))

    # Clear any pre-existing handlers (e.g., from Streamlit auto-config)
    for h in list(root.handlers):
        root.removeHandler(h)

    formatter = logging.Formatter(fmt)

    # Stdout — caught by every PaaS log shipper
    stdout = logging.StreamHandler(sys.stdout)
    stdout.setFormatter(formatter)
    root.addHandler(stdout)

    # Rotating file — survives across restarts; 10MB × 5 backups
    fileh = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fileh.setFormatter(formatter)
    root.addHandler(fileh)

    # Quiet down noisy third-party libs
    for noisy in ("urllib3", "requests", "playwright", "tenacity"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True
    root.info(f"logging configured (level={level}, file={log_file})")


def get_logger(name: str) -> logging.Logger:
    """Convenience: returns a child logger; auto-configures on first call."""
    if not _CONFIGURED:
        configure_logging()
    return logging.getLogger(name)
