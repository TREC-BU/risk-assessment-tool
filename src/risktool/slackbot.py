"""Slack bot: `/risk pdr|final` in one channel builds the PDF from the live sheet.

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
from .pipeline import BuildResult, CompileError, build
from .sheets import Grid, Sheet, SheetFormatError, fetch
from .validate import Mode

log = logging.getLogger("risktool.slack")

# The template's fonts. Without them Typst silently substitutes, so refuse to start.
REQUIRED_FONTS = ("Helvetica Neue", "Arial")


@dataclass
class Job:
    mode: Mode
    user: str
    ts: str  # the channel status message this build edits
    was_queued: bool


class BuildService:
    """Queues builds and reports each one back to the channel."""

    def __init__(self, client, channel: str, sheet_id: str,
                 fetch_sheet: Callable[[], Sheet],
                 run_build: Callable[[dict[str, Grid], Mode, Path], BuildResult]):
        self.client = client
        self.channel = channel
        self.sheet_id = sheet_id
        self.fetch_sheet = fetch_sheet
        self.run_build = run_build
        self.jobs: queue.Queue[Job] = queue.Queue()
        self.lock = threading.Lock()
        self.waiting: list[Job] = []
        self.current: Job | None = None

    def submit(self, mode: Mode, user: str) -> None:
        with self.lock:
            ahead = self.waiting[-1] if self.waiting else self.current
            text = fmt.queued(mode, user, ahead.user) if ahead else fmt.started(mode, user)
            ts = self.client.chat_postMessage(channel=self.channel, text=text)["ts"]
            job = Job(mode, user, ts, was_queued=ahead is not None)
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
                self._status(job, fmt.started(job.mode, job.user))
            sheet = self.fetch_sheet()
            with tempfile.TemporaryDirectory() as tmp:
                name = f"risk-assessment-{job.mode}.pdf"
                result = self.run_build(sheet.grids, job.mode, Path(tmp) / name)
                text, overflow = fmt.result(result.report, self.sheet_id, sheet.gids)
                if result.pdf:
                    self.client.files_upload_v2(
                        channel=self.channel, thread_ts=job.ts, file=str(result.pdf),
                        filename=name, title=f"Risk assessment ({fmt.MODE_NAMES[job.mode]})",
                        initial_comment=text,
                    )
                    self._status(job, fmt.succeeded(job.mode, job.user))
                else:
                    self._reply(job, text)
                    self._status(job, fmt.invalid(job.mode, job.user, len(result.report.errors)))
                if overflow:
                    self.client.files_upload_v2(
                        channel=self.channel, thread_ts=job.ts, content=overflow,
                        filename="problems.txt", title="All problems and warnings",
                    )
        except Exception as exc:
            log.exception("%s build for %s failed", job.mode, job.user)
            try:
                self._reply(job, fmt.failure(describe(exc)))
                self._status(job, fmt.crashed(job.mode, job.user))
            except Exception:
                log.exception("could not report the failure to Slack")


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
        if arg not in ("pdr", "final"):
            prefix = "" if arg in ("", "help") else f"I don't know `/risk {fmt.escape(arg)}`.\n\n"
            ack(response_type="ephemeral", text=prefix + fmt.HELP)
            return
        if command["channel_id"] != channel:
            ack(response_type="ephemeral", text=f"`/risk` only works in <#{channel}>.")
            return
        ack()
        try:
            service.submit(arg, command["user_id"])
        except SlackApiError as exc:
            if exc.response.get("error") in ("not_in_channel", "channel_not_found"):
                respond(response_type="ephemeral",
                        text="I'm not in this channel yet. Add me with `/invite @Risk Bot`, then try again.")
            else:
                raise


def missing_fonts() -> list[str]:
    listed = subprocess.run(["typst", "fonts"], capture_output=True, text=True).stdout
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
    credentials = env.get("GOOGLE_APPLICATION_CREDENTIALS")

    app = App(token=env["SLACK_BOT_TOKEN"])
    service = BuildService(
        app.client, channel, sheet_id,
        fetch_sheet=lambda: fetch(sheet_id, credentials),
        run_build=lambda grids, mode, out: build(grids, mode, ROOT, out),
    )
    threading.Thread(target=service.run_forever, name="builder", daemon=True).start()
    register(app, service, channel)
    log.info("listening for /risk in %s", channel)
    SocketModeHandler(app, env["SLACK_APP_TOKEN"]).start()


if __name__ == "__main__":
    main()
