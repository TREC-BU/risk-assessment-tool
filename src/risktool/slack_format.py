"""Slack message text for the bot. Pure functions, so wording is easy to test."""

from __future__ import annotations

import re

from .validate import Issue, Report

# Longer issue lists are cut here; the full list is attached as a text file.
MAX_LINES = 15

HELP = """*Risk assessment builder*
• `/risk` builds the risk assessment from the Google Sheet as it is right now.
Anything worth fixing is listed with a link to its row. Only errors, such as an ID that doesn't exist, stop the build; warnings (like an Unacceptable risk) and info don't."""


def escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def mention(user_id: str) -> str:
    return f"<@{user_id}>"


def row_link(issue: Issue, sheet_id: str, gids: dict[str, int]) -> str:
    """Issue location, linked to its row in the sheet when we know where that is."""
    label = escape(issue.where)
    if issue.tab not in gids:
        return f"*{label}*"
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid={gids[issue.tab]}"
    if issue.row is not None:
        url += f"&range=A{issue.row}"
    return f"*<{url}|{label}>*"


def _bullets(issues: list[Issue], sheet_id: str, gids: dict[str, int]) -> list[str]:
    return [f"• {row_link(i, sheet_id, gids)}: {escape(i.message)}" for i in issues]


# ---- Top-level status message (edited as the build progresses) ------------

def _count(n: int, noun: str) -> str:
    return f"1 {noun}" if n == 1 else f"{n} {noun}s"


def queued(user: str, behind: str) -> str:
    return f":hourglass: {mention(user)}'s build is queued behind {mention(behind)}'s build…"


def started(user: str) -> str:
    return f":hourglass_flowing_sand: {mention(user)} started a build…"


def succeeded(user: str, warnings: int) -> str:
    note = f" ({_count(warnings, 'warning')})" if warnings else ""
    return f":white_check_mark: Build by {mention(user)}: PDF in thread{note}."


def invalid(user: str, count: int) -> str:
    return f":x: Build by {mention(user)}: {_count(count, 'error')} to fix in the sheet. Details in thread."


def crashed(user: str) -> str:
    return f":warning: Build by {mention(user)} couldn't run. Details in thread."


# ---- Thread reply ----------------------------------------------------------

def result(report: Report, sheet_id: str, gids: dict[str, int],
           drive: str | None = None) -> tuple[str, str | None]:
    """Thread text for a finished build, plus the full plain-text list if it was cut.

    `drive` is a line about the Google Drive copy, shown under "Here's the PDF."
    """
    lines: list[str] = []
    if report.errors:
        lines.append("Fix these in the sheet, then run `/risk` again:")
        lines += _bullets(report.errors, sheet_id, gids)
    else:
        lines.append("Here's the PDF.")
        if drive:
            lines.append(drive)
    if report.warnings:
        lines.append("")
        lines.append(f":warning: *{_count(len(report.warnings), 'warning')}* "
                     "(the method isn't satisfied yet, but they don't stop the build):")
        lines += _bullets(report.warnings, sheet_id, gids)
    if report.info:
        lines.append("")
        lines.append(f":information_source: *{len(report.info)} info* (worth a look):")
        lines += _bullets(report.info, sheet_id, gids)

    if len(lines) <= MAX_LINES + 1:
        return "\n".join(lines), None
    shown = lines[:MAX_LINES]
    shown.append(f"_…and {len(lines) - MAX_LINES} more lines. The full list is attached._")
    full = ([f"error: {i}" for i in report.errors] + [f"warning: {i}" for i in report.warnings]
            + [f"info: {i}" for i in report.info])
    return "\n".join(shown), "\n".join(full) + "\n"


def published(link: str) -> str:
    return f":file_folder: <{link}|The copy in Google Drive> is updated."


def publish_failed(reason: str) -> str:
    return f":warning: Couldn't update the copy in Google Drive: {escape(reason)}"


def deployed(sha: str, author: str, message: str, repo_url: str | None) -> str:
    """Announcement that the bot now runs commit `sha`."""
    ref = f"<{repo_url}/commit/{sha}|{sha[:7]}>" if repo_url else f"`{sha[:7]}`"
    by = f" by {escape(author)}" if author else ""
    subject, _, body = message.strip().partition("\n")
    # Drop a closing paragraph of git trailers ("Co-Authored-By: …").
    paragraphs = body.strip().split("\n\n")
    if all(re.match(r"[\w-]+: ", line) for line in paragraphs[-1].splitlines()):
        paragraphs.pop()
    body = "\n\n".join(paragraphs)
    lines = [f":rocket: Updated to {ref}{by}: *{escape(subject) or 'no message'}*"]
    lines += [f">{' ' + escape(line) if line.strip() else ''}" for line in body.strip().splitlines()]
    return "\n".join(lines)


def failure(reason: str) -> str:
    return (f":warning: The build couldn't run: {escape(reason)}\n"
            "Try again in a minute. If it keeps happening, tell whoever runs the bot; "
            "the details are in the server log.")
