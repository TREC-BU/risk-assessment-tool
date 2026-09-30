"""Publish a built PDF to the Drive folder next to the Google Sheet.

Each mode has one file in the folder, e.g. "Risk assessment (Final).pdf", and
every build replaces its contents. The link stays the same and Drive keeps
the earlier versions.

The service account has no Drive storage of its own, so in a My Drive folder
it can only replace files a person created. In a Shared Drive it can create
them too.

The folder is the one named FOLDER_NAME in the same folder as the sheet, or
RISK_DRIVE_FOLDER_ID if that is set.
"""

from __future__ import annotations

import json
from pathlib import Path

from .validate import Mode

FOLDER_NAME = "Risk assessment PDFs"
MODE_NAMES = {"pdr": "PDR", "final": "Final"}

API = "https://www.googleapis.com/drive/v3/files"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
FOLDER_TYPE = "application/vnd.google-apps.folder"
ALL_DRIVES = {"supportsAllDrives": "true"}


class DriveError(Exception):
    """Drive refused the upload. The message is written for the team."""


class NoQuotaError(DriveError):
    """The service account tried to create a file where it has no storage."""


def file_name(mode: Mode) -> str:
    return f"Risk assessment ({MODE_NAMES[mode]}).pdf"


class Drive:
    def __init__(self, session):
        """`session` is an authorized requests session, e.g. gspread's."""
        self.session = session

    def _call(self, method: str, url: str, params=None, **kw) -> dict:
        resp = self.session.request(method, url, params={**ALL_DRIVES, **(params or {})}, **kw)
        if resp.ok:
            return resp.json()
        try:
            error = resp.json()["error"]
            reason = error["errors"][0]["reason"]
        except (ValueError, KeyError, IndexError):
            error, reason = {}, ""
        if reason == "storageQuotaExceeded" or "storage quota" in error.get("message", ""):
            raise NoQuotaError("the bot can't create new files in a My Drive folder.")
        raise DriveError(f"Google Drive returned an error ({resp.status_code}"
                         + (f" {reason}" if reason else "") + ").")

    def _list(self, query: str) -> list[dict]:
        return self._call("GET", API, params={
            "q": query, "fields": "files(id,parents,webViewLink)",
            "corpora": "allDrives", "includeItemsFromAllDrives": "true",
        })["files"]

    def find_folder(self, sheet_id: str) -> str:
        """The FOLDER_NAME folder beside the sheet; any single one the bot can see otherwise."""
        parents = set(self._call("GET", f"{API}/{sheet_id}",
                                 params={"fields": "parents"}).get("parents", []))
        found = self._list(f"name = '{FOLDER_NAME}' and mimeType = '{FOLDER_TYPE}' and trashed = false")
        nearby = [f for f in found if parents & set(f.get("parents", []))]
        matches = nearby or found
        if not matches:
            raise DriveError(f"there's no '{FOLDER_NAME}' folder shared with the bot.")
        if len(matches) > 1:
            raise DriveError(f"the bot can see {len(matches)} '{FOLDER_NAME}' folders; "
                             "set RISK_DRIVE_FOLDER_ID to pick one.")
        return matches[0]["id"]

    def publish(self, pdf: Path, mode: Mode, folder: str) -> str:
        """Replace (or create) this mode's PDF in `folder`. Returns its link."""
        name = file_name(mode)
        data = pdf.read_bytes()
        existing = self._list(f"name = '{name}' and '{folder}' in parents and trashed = false")
        if existing:
            return self._call(
                "PATCH", f"{UPLOAD}/{existing[0]['id']}",
                params={"uploadType": "media", "fields": "webViewLink"},
                headers={"Content-Type": "application/pdf"}, data=data,
            )["webViewLink"]

        boundary = "risktool-boundary"
        meta = json.dumps({"name": name, "parents": [folder], "mimeType": "application/pdf"})
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
                f"--{boundary}\r\nContent-Type: application/pdf\r\n\r\n").encode()
        body += data + f"\r\n--{boundary}--\r\n".encode()
        try:
            return self._call(
                "POST", UPLOAD, params={"uploadType": "multipart", "fields": "webViewLink"},
                headers={"Content-Type": f"multipart/related; boundary={boundary}"}, data=body,
            )["webViewLink"]
        except NoQuotaError:
            raise DriveError(f"the bot can't create files in a My Drive folder. "
                             f"Upload any PDF named '{name}' to the folder once "
                             "and the bot will replace it on each build.") from None
