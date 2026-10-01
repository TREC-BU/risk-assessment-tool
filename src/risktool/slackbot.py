"""Slack bot: `/risk` in one channel builds the PDF from the live sheet.

Each build posts a status message in the channel, edits it as the build
progresses, and replies in its thread with the PDF or the problems to fix.
Builds run one at a time on a single worker thread; later requests queue.

Runs over Socket Mode, so the server needs no public URL. Configuration comes
from the environment (or .env):

    SLACK_BOT_TOKEN      xoxb-…  (OAuth & Permissions → Bot User OAuth Token)
    SLACK_APP_TOKEN      xapp-…  (Basic Information → App-Level Token, connections:write)
    RISK_SLACK_CHANNEL   channel ID where /risk works, e.g. C0123456789
    RISK_SHEET_ID        Google Sheet key
    GOOGLE_APPLICATION_CREDENTIALS   service account key (optional; gspread default otherwise)
    RISK_DRIVE_FOLDER_ID Drive folder for the PDFs (optional; see drive.py)
    RISK_COMMIT_SHA, RISK_COMMIT_AUTHOR, RISK_COMMIT_MESSAGE
                         the deployed commit, set by scripts/deploy.sh (optional)
    RISK_REPO_URL        GitHub repo, for the commit link (optional)

Each successful build also replaces the PDF in Google Drive. After a
deploy, the bot posts the commit it now runs.
"""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import slack_format as fmt
from .cli import ROOT, load_dotenv
from .drive import Drive, DriveError
from .pipeline import BUILD, PDF_NAME, BuildResult, CompileError, build, typst_env
from .sheets import Grid, Sheet, SheetFormatError, connect, fetch

log = logging.getLogger("risktool.slack")

# The last commit announced. It lives in the container, so a restart of the same
# container stays quiet and a deploy (a new container) announces again.
ANNOUNCED = ROOT / BUILD / "announced-commit"

# The template's fonts. Without them Typst silently substitutes, so refuse to start.
REQUIRED_FONTS = ("Helvetica Neue", "Arial", "Raleway")


@dataclass
class Job:
    user: str
    ts: str  # the channel status message this build edits
    was_queued: bool


class BuildService:
    """Queues builds and reports each one back to the channel."""

    def __init__(self, client, channel: str, sheet_id: str,
                 fetch_sheet: Callable[[], Sheet],
                 run_build: Callable[[dict[str, Grid], Path], BuildResult],
                 publish: Callable[[Path], str] | None = None):
        self.client = client
        self.channel = channel
        self.sheet_id = sheet_id
        self.fetch_sheet = fetch_sheet
        self.run_build = run_build
        self.publish = publish  # uploads the PDF to Drive, returns its link
        self.jobs: queue.Queue[Job] = queue.Queue()
        self.lock = threading.Lock()
        self.waiting: list[Job] = []
        self.current: Job | None = None

    def submit(self, user: str) -> None:
        with self.lock:
            ahead = self.waiting[-1] if self.waiting else self.current
            text = fmt.queued(user, ahead.user) if ahead else fmt.started(user)
            ts = self.client.chat_postMessage(channel=self.channel, text=text)["ts"]
            job = Job(user, ts, was_queued=ahead is not None)
            self.waiting.append(job)
        self.jobs.put(job)

    def run_forever(self) -> None:
        while True:
            self.process(self.jobs.get())

    def run_pending(self) -> None:
        """Process everything queued, on this thread. For tests."""
        while not self.jobs.empty():
            self.process(self.jobs.get())

    def process(self, job: Job) -> None:
        with self.lock:
            self.waiting.remove(job)
            self.current = job
        try:
            self._build(job)
        finally:
            with self.lock:
                self.current = None

    def _status(self, job: Job, text: str) -> None:
        self.client.chat_update(channel=self.channel, ts=job.ts, text=text)

    def _reply(self, job: Job, text: str) -> None:
        self.client.chat_postMessage(channel=self.channel, thread_ts=job.ts, text=text,
                                     unfurl_links=False, unfurl_media=False)

    def _build(self, job: Job) -> None:
        try:
            if job.was_queued:
                self._status(job, fmt.started(job.user))
            sheet = self.fetch_sheet()
            with tempfile.TemporaryDirectory() as tmp:
                result = self.run_build(sheet.grids, Path(tmp) / PDF_NAME)
                drive = self._publish(job, result.pdf) if result.pdf else None
                text, overflow = fmt.result(result.report, self.sheet_id, sheet.gids, drive)
                if result.pdf:
                    self.client.files_upload_v2(
                        channel=self.channel, thread_ts=job.ts, file=str(result.pdf),
                        filename=PDF_NAME, title="Risk assessment",
                        initial_comment=text,
                    )
                    self._status(job, fmt.succeeded(job.user, len(result.report.warnings)))
                else:
                    self._reply(job, text)
                    self._status(job, fmt.invalid(job.user, len(result.report.errors)))
                if overflow:
                    self.client.files_upload_v2(
                        channel=self.channel, thread_ts=job.ts, content=overflow,
                        filename="problems.txt", title="All errors, warnings and info",
                    )
        except Exception as exc:
            log.exception("build for %s failed", job.user)
            try:
                self._reply(job, fmt.failure(describe(exc)))
                self._status(job, fmt.crashed(job.user))
            except Exception:
                log.exception("could not report the failure to Slack")

    def _publish(self, job: Job, pdf: Path) -> str | None:
        """Update the Drive copy. A failure is reported, but still posts the PDF."""
        if not self.publish:
            return None
        try:
            return fmt.published(self.publish(pdf))
        except Exception as exc:
            log.exception("publishing the PDF to Drive failed")
            return fmt.publish_failed(
                str(exc) if isinstance(exc, DriveError) else "something unexpected went wrong.")


def describe(exc: Exception) -> str:
    """A plain-language reason for a build that couldn't run."""
    import gspread
    import requests

    if isinstance(exc, FileNotFoundError):
        return "the server's Google key file is missing."
    if isinstance(exc, SheetFormatError):
        return f"{exc}."
    if isinstance(exc, gspread.exceptions.SpreadsheetNotFound):
        return "the bot can't open the Google Sheet. Is it shared with the bot's service account?"
    if isinstance(exc, gspread.exceptions.APIError):
        return "Google Sheets returned an error."
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return "couldn't reach Google Sheets."
    if isinstance(exc, CompileError):
        return "the PDF compiler failed."
    return "something unexpected went wrong."


def register(app, service: BuildService, channel: str) -> None:
    from slack_sdk.errors import SlackApiError

    @app.command("/risk")
    def risk(ack, command, respond):
        arg = command.get("text", "").strip().lower()
        if arg:
            prefix = "" if arg == "help" else f"I don't know `/risk {fmt.escape(arg)}`.\n\n"
            ack(response_type="ephemeral", text=prefix + fmt.HELP)
            return
        if command["channel_id"] != channel:
            ack(response_type="ephemeral", text=f"`/risk` only works in <#{channel}>.")
            return
        ack()
        try:
            service.submit(command["user_id"])
        except SlackApiError as exc:
            if exc.response.get("error") in ("not_in_channel", "channel_not_found"):
                respond(response_type="ephemeral",
                        text="I'm not in this channel yet. Add me with `/invite @Risk Bot`, then try again.")
            else:
                raise


def announce_version(client, channel: str, env, marker: Path = ANNOUNCED) -> None:
    """Post the deployed commit, once. Does nothing outside a scripts/deploy.sh deploy."""
    sha = env.get("RISK_COMMIT_SHA")
    if not sha:
        return
    if marker.is_file() and marker.read_text().strip() == sha:
        return
    text = fmt.deployed(sha, env.get("RISK_COMMIT_AUTHOR", ""), env.get("RISK_COMMIT_MESSAGE", ""),
                        env.get("RISK_REPO_URL"))
    try:
        client.chat_postMessage(channel=channel, text=text, unfurl_links=False, unfurl_media=False)
    except Exception:
        log.exception("could not announce commit %s", sha)
        return
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(sha)


def missing_fonts() -> list[str]:
    listed = subprocess.run(["typst", "fonts"], capture_output=True, text=True,
                            env=typst_env(ROOT)).stdout
    names = {line.strip() for line in listed.splitlines()}
    return [f for f in REQUIRED_FONTS if f not in names]


def main() -> None:
    load_dotenv(ROOT / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    names = ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "RISK_SLACK_CHANNEL", "RISK_SHEET_ID")
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        sys.exit(f"risktool-slack: set {', '.join(missing)} (see docs/slack-bot.md)")
    fonts = missing_fonts()
    if fonts:
        sys.exit(f"risktool-slack: Typst can't find {', '.join(fonts)}. "
                 "Copy the font files into fonts/ (see docs/slack-bot.md).")

    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    env = os.environ
    channel, sheet_id = env["RISK_SLACK_CHANNEL"], env["RISK_SHEET_ID"]
    try:
        google = connect(env.get("GOOGLE_APPLICATION_CREDENTIALS"))
    except FileNotFoundError as exc:
        sys.exit(f"risktool-slack: Google key not found: {exc.filename}")
    drive = Drive(google.http_client.session)

    def publish(pdf: Path) -> str:
        folder = env.get("RISK_DRIVE_FOLDER_ID") or drive.find_folder(sheet_id)
        return drive.publish(pdf, folder)

    app = App(token=env["SLACK_BOT_TOKEN"])
    service = BuildService(
        app.client, channel, sheet_id,
        fetch_sheet=lambda: fetch(google, sheet_id),
        run_build=lambda grids, out: build(grids, ROOT, out),
        publish=publish,
    )
    threading.Thread(target=service.run_forever, name="builder", daemon=True).start()
    register(app, service, channel)
    announce_version(app.client, channel, env)
    log.info("listening for /risk in %s", channel)
    SocketModeHandler(app, env["SLACK_APP_TOKEN"]).start()


if __name__ == "__main__":
    main()
