"""risktool — build the risk assessment PDF from the Google Sheet.

    risktool build --mode pdr|final     fetch, validate, render the PDF
    risktool check --mode pdr|final     fetch and validate only

The sheet is read from Google Sheets with a service account. Settings such as
RISK_SHEET_ID can go in a .env file in the current directory; real
environment variables take precedence. Every fetch is
cached in build/sheet-cache.json; pass --from that file (or any file of the
same shape) to rebuild without network access.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .pipeline import BUILD, CompileError, build
from .sheets import SheetFormatError, fetch, load_grids, save_grids

ROOT = Path.cwd()


def load_dotenv(path: Path) -> None:
    """Set KEY=VALUE lines from a .env file without overriding the environment."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def _args(argv):
    parser = argparse.ArgumentParser(prog="risktool", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help in (("build", "validate and render the PDF"), ("check", "validate only")):
        p = sub.add_parser(name, help=help)
        p.add_argument("--mode", choices=("pdr", "final"), required=True)
        p.add_argument("--sheet", default=os.environ.get("RISK_SHEET_ID"),
                       help="Google Sheet key (default: $RISK_SHEET_ID, also read from .env)")
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
    load_dotenv(ROOT / ".env")
    args = _args(argv)
    root: Path = args.root.resolve()

    if args.source:
        grids = load_grids(args.source)
    else:
        if not args.sheet:
            sys.exit("risktool: no sheet given; pass --sheet or set RISK_SHEET_ID")
        try:
            grids = fetch(args.sheet, args.credentials).grids
        except FileNotFoundError as exc:
            sys.exit(f"risktool: service account key not found: {exc.filename}\n"
                     "Put the key there, or set GOOGLE_APPLICATION_CREDENTIALS (in .env is fine).")
        except SheetFormatError as exc:
            sys.exit(f"risktool: {exc}")
        save_grids(grids, root / BUILD / "sheet-cache.json")

    try:
        result = build(grids, args.mode, root, getattr(args, "output", None),
                       render=args.command == "build")
    except CompileError as exc:
        print(exc, file=sys.stderr)
        return 1
    report = result.report
    for w in report.warnings:
        print(f"warning: {w}", file=sys.stderr)
    for e in report.errors:
        print(f"error: {e}", file=sys.stderr)
    print(f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)", file=sys.stderr)
    if not report.ok:
        return 1
    if result.pdf:
        print(f"wrote {result.pdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
