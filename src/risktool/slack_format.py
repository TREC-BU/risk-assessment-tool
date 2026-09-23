"""Slack message text for the bot. Pure functions, so wording is easy to test."""

from __future__ import annotations

from .validate import Issue, Mode, Report

MODE_NAMES = {"pdr": "PDR", "final": "Final"}

# Longer issue lists are cut here; the full list is attached as a text file.
MAX_LINES = 15

HELP = """*Risk assessment builder*
• `/risk pdr` builds the Preliminary Design Review document: method, hazards and initial risk scores.
• `/risk final` builds the complete document. It won't build while any risk is still Unacceptable.
Each build reads the Google Sheet as it is right now. If something needs fixing, the bot lists it with a link to the row."""


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

def queued(mode: Mode, user: str, behind: str) -> str:
    return f":hourglass: {mention(user)}'s *{MODE_NAMES[mode]}* build is queued behind {mention(behind)}'s build…"


def started(mode: Mode, user: str) -> str:
    return f":hourglass_flowing_sand: {mention(user)} started a *{MODE_NAMES[mode]}* build…"


def succeeded(mode: Mode, user: str) -> str:
    return f":white_check_mark: *{MODE_NAMES[mode]}* build by {mention(user)}: PDF in thread."


def invalid(mode: Mode, user: str, count: int) -> str:
    problems = "1 problem" if count == 1 else f"{count} problems"
    return f":x: *{MODE_NAMES[mode]}* build by {mention(user)}: {problems} to fix in the sheet. Details in thread."


def crashed(mode: Mode, user: str) -> str:
    return f":warning: *{MODE_NAMES[mode]}* build by {mention(user)} couldn't run. Details in thread."


# ---- Thread reply ----------------------------------------------------------

def result(report: Report, sheet_id: str, gids: dict[str, int]) -> tuple[str, str | None]:
    """Thread text for a finished build, plus the full plain-text list if it was cut."""
    lines: list[str] = []
    if report.errors:
        lines.append(f"Fix these in the sheet, then run `/risk {report.mode}` again:")
        lines += _bullets(report.errors, sheet_id, gids)
    else:
        lines.append("Here's the PDF.")
    if report.warnings:
        n = len(report.warnings)
        lines.append("")
        lines.append(f":warning: *{n} warning{'s' if n != 1 else ''}* (worth checking, but they don't stop the build):")
        lines += _bullets(report.warnings, sheet_id, gids)

    if len(lines) <= MAX_LINES + 1:
        return "\n".join(lines), None
    shown = lines[:MAX_LINES]
    shown.append(f"_…and {len(lines) - MAX_LINES} more lines. The full list is attached._")
    full = [f"error: {i}" for i in report.errors] + [f"warning: {i}" for i in report.warnings]
    return "\n".join(shown), "\n".join(full) + "\n"


def failure(reason: str) -> str:
    return (f":warning: The build couldn't run: {escape(reason)}\n"
            "Try again in a minute. If it keeps happening, tell whoever runs the bot; "
            "the details are in the server log.")
