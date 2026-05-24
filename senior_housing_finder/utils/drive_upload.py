"""
Google Drive uploader.

Pushes scraper outputs to a shared Drive folder using OAuth user credentials
(not a service account — service accounts cannot own files in personal Drive
folders, causing 403 storageQuotaExceeded on writes).

Auth env vars (all three required):
  GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN  — long-lived refresh token from one-time browser flow
  GOOGLE_DRIVE_OAUTH_CLIENT_ID      — OAuth 2.0 client ID (Desktop app)
  GOOGLE_DRIVE_OAUTH_CLIENT_SECRET  — OAuth 2.0 client secret

Destination env var:
  GOOGLE_DRIVE_FOLDER_ID  — target folder; must be owned by or shared with the
                            Google account that authorized the refresh token

Skips silently if any required env var is missing or libs aren't installed —
never crashes the pipeline.
"""
import logging
import os
import sys
from pathlib import Path
from typing import Iterable, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("drive_upload")


def _drive():
    refresh_token = os.getenv("GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN", "").strip()
    client_id = os.getenv("GOOGLE_DRIVE_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_DRIVE_OAUTH_CLIENT_SECRET", "").strip()
    if not (refresh_token and client_id and client_secret):
        log.info(
            "OAuth env vars missing (need GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN, "
            "GOOGLE_DRIVE_OAUTH_CLIENT_ID, GOOGLE_DRIVE_OAUTH_CLIENT_SECRET) "
            "— skipping upload"
        )
        return None
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as e:
        log.warning(f"Google libs import failed ({e!r}) — skipping upload")
        return None
    try:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception:
        log.exception("failed to build Drive service")
        return None


def _upload_one(drive, path: Path, folder_id: str) -> Optional[str]:
    try:
        from googleapiclient.http import MediaFileUpload
        media = MediaFileUpload(str(path), resumable=True)
        result = drive.files().create(
            body={"name": path.name, "parents": [folder_id]},
            media_body=media,
            fields="id",
        ).execute()
        return result.get("id")
    except Exception:
        log.exception(f"upload failed: {path}")
        return None


def upload_outputs(output_dir: Optional[Path] = None,
                   patterns: Iterable[str] = ("*.xlsx", "*.csv", "*.md", "*.html", "*.sqlite")) -> int:
    output_dir = Path(output_dir) if output_dir else Path("data/output")
    if not output_dir.exists():
        log.warning(f"no output dir: {output_dir}")
        return 0
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()
    if not folder_id:
        log.info("no GOOGLE_DRIVE_FOLDER_ID — skipping upload")
        return 0
    drive = _drive()
    if drive is None:
        return 0
    n = 0
    for pattern in patterns:
        for file in output_dir.rglob(pattern):
            if _upload_one(drive, file, folder_id):
                log.info(f"uploaded {file.name}")
                n += 1
    return n


if __name__ == "__main__":
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    print(f"Drive upload: {upload_outputs(out_dir)} files")
