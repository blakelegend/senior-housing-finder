"""
Google Drive uploader.

Pushes scraper outputs to a shared Drive folder using a service account.
Auth via GOOGLE_DRIVE_CREDENTIALS_JSON (full JSON contents) + GOOGLE_DRIVE_FOLDER_ID.
Skips silently if either is missing — never crashes the pipeline.
"""
import json
import logging
import os
import sys
from pathlib import Path
from typing import Iterable, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("drive_upload")


def _drive():
    creds_json = os.getenv("GOOGLE_DRIVE_CREDENTIALS_JSON", "").strip()
    if not creds_json:
        log.info("no GOOGLE_DRIVE_CREDENTIALS_JSON — skipping upload")
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        log.warning("google-api-python-client not installed — skipping upload")
        return None
    try:
        creds = service_account.Credentials.from_service_account_info(
            json.loads(creds_json),
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
