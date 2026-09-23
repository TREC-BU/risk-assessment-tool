"""risktool — build the risk assessment PDF from the Google Sheet.

    risktool build --mode pdr|final     fetch, validate, render the PDF
    risktool check --mode pdr|final     fetch and validate only

The sheet is read from Google Sheets with a service account. Every fetch is
cached in build/sheet-cache.json; pass --from that file (or any file of the
same shape) to rebuild without network access.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from .config import load_config
from .sheets import fetch, load_grids, save_grids
from .validate import validate

ROOT = Path.cwd()
CONFIG = "risk-config.typ"
DOCUMENT = "risk-assessment.typ"
BUILD = "build"


def _args(argv):
    parser = argparse.ArgumentParser(prog="risktool", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help in (("build", "validate and render the PDF"), ("check", "validate only")):
        p = sub.add_parser(name, help=help)
        p.add_argument("--mode", choices=("pdr", "final"), required=True)
        p.add_argument("--sheet", default=os.environ.get("RISK_SHEET_ID"),
                       help="Google Sheet key (default: $RISK_SHEET_ID)")
        p.add_argument("--credentials", default=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
                       help="service account JSON (default: $GOOGLE_APPLICATION_CREDENTIALS, "
                            "then gspread's ~/.config/gspread/service_account.json)")
        p.add_argument("--from", dest="source", type=Path,
                       help="read tabs from a cached JSON file instead of Google Sheets")
        p.add_argument("--root", type=Path, default=ROOT,
                       help="project directory holding the .typ files (default: cwd)")
        if name == "build":
            p.add_argument("-o", "--output", type=Path,
                           help="PDF path (default: build/risk-assessment-<mode>.pdf)")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _args(argv)
    root: Path = args.root.resolve()
    build = root / BUILD

    config = load_config(root / CONFIG)

    if args.source:
        grids = load_grids(args.source)
    else:
        if not args.sheet:
            sys.exit("risktool: no sheet given; pass --sheet or set RISK_SHEET_ID")
        grids = fetch(args.sheet, args.credentials)
        save_grids(grids, build / "sheet-cache.json")

    report = validate(grids, config, args.mode)
    for w in report.warnings:
        print(f"warning: {w}", file=sys.stderr)
    for e in report.errors:
        print(f"error: {e}", file=sys.stderr)
    print(f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)", file=sys.stderr)
    if not report.ok:
        return 1
    if args.command == "check":
        return 0

    build.mkdir(exist_ok=True)
    data = {**report.data, "date": date.today().isoformat()}
    (build / "risk.json").write_text(json.dumps(data, indent=1, ensure_ascii=False))

    output = (args.output or build / f"risk-assessment-{args.mode}.pdf").resolve()
    result = subprocess.run(
        ["typst", "compile", "--root", str(root), str(root / DOCUMENT), str(output)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return result.returncode
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
