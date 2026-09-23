"""Validate the sheet and compile the PDF. Shared by the CLI and the Slack bot."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .config import load_config
from .sheets import Grid
from .validate import Mode, Report, validate

CONFIG = "risk-config.typ"
DOCUMENT = "risk-assessment.typ"
BUILD = "build"
FONTS = "fonts"  # git-ignored; fonts we may not commit (see README)


class CompileError(Exception):
    """Typst failed to compile the document."""


@dataclass
class BuildResult:
    report: Report
    pdf: Path | None  # None when validation failed or no PDF was asked for


def typst_env(root: Path) -> dict[str, str]:
    """Environment for typst: the project's fonts/ folder plus any TYPST_FONT_PATHS.

    Passing --font-path would replace TYPST_FONT_PATHS instead of adding to
    it, so both go in the variable.
    """
    paths = [str(root / FONTS)]
    if os.environ.get("TYPST_FONT_PATHS"):
        paths.append(os.environ["TYPST_FONT_PATHS"])
    return {**os.environ, "TYPST_FONT_PATHS": os.pathsep.join(paths)}


def default_output(root: Path, mode: Mode) -> Path:
    return root / BUILD / f"risk-assessment-{mode}.pdf"


def build(grids: dict[str, Grid], mode: Mode, root: Path, output: Path | None = None,
          render: bool = True) -> BuildResult:
    """Validate `grids`; if they pass and `render` is set, compile the PDF."""
    report = validate(grids, load_config(root / CONFIG), mode)
    if not report.ok or not render:
        return BuildResult(report, None)

    (root / BUILD).mkdir(exist_ok=True)
    data = {**report.data, "date": date.today().isoformat()}
    (root / BUILD / "risk.json").write_text(json.dumps(data, indent=1, ensure_ascii=False))

    output = (output or default_output(root, mode)).resolve()
    result = subprocess.run(
        ["typst", "compile", "--root", str(root), str(root / DOCUMENT), str(output)],
        capture_output=True, text=True, env=typst_env(root),
    )
    if result.returncode != 0:
        raise CompileError(result.stderr)
    return BuildResult(report, output)
