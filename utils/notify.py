"""
Failure notifications — email + optional Slack webhook.

Wraps the entry point so any uncaught exception fires an alert with the
traceback, hostname, and run mode. Without configuration, this is a no-op.

Env vars (all optional):
  ALERT_EMAIL_TO              — comma-separated recipient list
  ALERT_EMAIL_FROM            — sender address (also From: header)
  SMTP_HOST                   — e.g. smtp.gmail.com, smtp.sendgrid.net
  SMTP_PORT                   — default 587
  SMTP_USERNAME / SMTP_PASSWORD
  SMTP_USE_TLS                — "1" / "0" (default 1)
  SLACK_WEBHOOK_URL           — optional, mirrors errors to a Slack channel

Tip: For Gmail, generate an "App Password" rather than using your real password.
For SendGrid, SMTP_USERNAME is the literal string "apikey" and the password
is the SendGrid API key.
"""
import os
import platform
import socket
import smtplib
import traceback
from email.message import EmailMessage
from typing import Callable

from .logging_setup import get_logger

log = get_logger(__name__)


def _email_alert(subject: str, body: str) -> bool:
    to_csv = os.getenv("ALERT_EMAIL_TO", "").strip()
    sender = os.getenv("ALERT_EMAIL_FROM", "").strip()
    host = os.getenv("SMTP_HOST", "").strip()
    if not (to_csv and sender and host):
        return False

    port = int(os.getenv("SMTP_PORT", "587"))
    use_tls = os.getenv("SMTP_USE_TLS", "1") in ("1", "true", "yes")
    user = os.getenv("SMTP_USERNAME")
    pw = os.getenv("SMTP_PASSWORD")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_csv
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=30) as s:
            if use_tls:
                s.starttls()
            if user and pw:
                s.login(user, pw)
            s.send_message(msg)
        log.info(f"alert email sent to {to_csv}")
        return True
    except Exception as e:
        log.error(f"alert email failed: {e}")
        return False


def _slack_alert(subject: str, body: str) -> bool:
    url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not url:
        return False
    try:
        import requests
        resp = requests.post(
            url,
            json={"text": f"*{subject}*\n```{body[:3000]}```"},
            timeout=15,
        )
        resp.raise_for_status()
        log.info("alert posted to slack")
        return True
    except Exception as e:
        log.error(f"slack webhook failed: {e}")
        return False


def alert(subject: str, body: str) -> None:
    """Send to whichever channels are configured."""
    sent_any = _email_alert(subject, body) or _slack_alert(subject, body)
    if not sent_any:
        log.debug("no alert channels configured — alert dropped")


def with_failure_alert(fn: Callable, run_label: str = "pipeline") -> int:
    """
    Wrap an entry-point function. Returns its int return code or 1 on exception.
    Fires an alert with full traceback on any unhandled error.
    """
    try:
        return int(fn() or 0)
    except KeyboardInterrupt:
        log.warning("interrupted by user")
        return 130
    except Exception:
        tb = traceback.format_exc()
        log.error(f"{run_label} crashed:\n{tb}")
        alert(
            subject=f"[ALERT] {run_label} failed on {socket.gethostname()}",
            body=(
                f"Host: {socket.gethostname()}\n"
                f"Platform: {platform.platform()}\n"
                f"Run mode: {os.getenv('RUN_MODE', 'full')}\n\n"
                f"Traceback:\n{tb}"
            ),
        )
        return 1
