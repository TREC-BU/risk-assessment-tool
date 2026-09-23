# Risk Assessment Tool

Builds the REC risk assessment PDF from the club's Google Sheet.

```
Google Sheet ──gspread──▶ validate (Pydantic) ──▶ build/risk.json ──typst──▶ PDF
                              ▲
risk-config.typ ──typst eval──┘   (scales, matrix, bands: defined once)
```

## Files

| File | Holds |
| --- | --- |
| `risk-config.typ` | The method: 1–5 scales, 5 × 5 acceptability matrix, bands, `acceptable-max`, mitigation types, `design_ref` prefixes, scope and limits text, cover text. |
| `template.typ` | Club documentation style, measured from `00 TEMPLATE.pdf`. |
| `risk-assessment.typ` | The document. Reads `build/risk.json`. |
| `src/risktool/` | Sheet reader, models, validator, CLI. |
| `examples/sample-sheet.json` | Made-up drop tower data in the sheet's layout, for offline builds. |

**Changing the method is a one-file edit.** If the REC ASTM Adaptation
Document prescribes different scales, bands or matrix cells, edit
`risk-config.typ` only. The validator and the PDF both read it.

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

You also need Typst 0.15+ on `PATH`. The fonts are Helvetica Neue and Arial,
which ship with macOS; Windows has Arial.

Share the sheet with the service account's email (Viewer is enough), then:

```sh
export RISK_SHEET_ID=<key from the sheet URL>
export GOOGLE_APPLICATION_CREDENTIALS=~/keys/rec-service-account.json
```

Never commit the key. `.gitignore` excludes the usual names.

## Use

```sh
.venv/bin/risktool build --mode pdr     # method, hazard list, initial scores
.venv/bin/risktool build --mode final   # everything; fails on any Unacceptable residual
.venv/bin/risktool check --mode final   # validate only
```

The PDF goes to `build/risk-assessment-<mode>.pdf`. Each fetch is cached in
`build/sheet-cache.json`. Use `--from build/sheet-cache.json` to rebuild
without the network, or `--from examples/sample-sheet.json` to try it out.

## Sheet layout

The tool reads the tabs **Hazards**, **Situations**, **Mitigations** and
**Risks**. It ignores the Definitions tab; `risk-config.typ` replaces it.
Each table is found by its header row (`hazard_id`, `situation_id`, …), so
title rows above it and column order don't matter. Column *names* do matter.
Rows that only have a pre-filled ID are skipped. The formula columns
`initial_risk` and `mitigated_risk` are ignored and recomputed.

- `mitigations`, `fat_ref` and `design_ref` are `;`-separated lists.
- `reduces` is `P`, `S` or `P;S`.
- `misuse` is 0/1.
- `design_ref` starts with a document prefix from the config, e.g. `MSD_94.1.1 …`.

## Validation

Errors stop the build. Each one names the tab, spreadsheet row and ID, e.g.
`Risks row 15 (RK_011): …`.

- IDs are unique and every reference resolves. Lists and scores (1–5) parse.
- An Unacceptable initial risk needs mitigations and residual `p1`/`s1`.
- Residual scores can't exceed the initial ones.
- S can only drop with a linked mitigation whose type may lower severity
  (Elimination, Design, Safeguarding) and whose `reduces` includes S.
  P can only drop with a linked mitigation that reduces P.
- A residual in a `justify: true` band (Justifiable) needs `p1_justification`
  or `s1_justification`. This includes unmitigated risks, whose initial band
  carries forward.
- **Final**: no residual may be worse than `acceptable-max`.

In **PDR** mode the mitigation and residual rules above are warnings, not
errors.

Warnings: a hazard or situation with no risks; a hazard assessed only against
rider situations; a risk mitigated only by Administrative measures; a
mitigation not linked to any risk; a row ignored for having scores but no
content; missing `p0`/`s0` justifications.

## Tests

```sh
.venv/bin/pytest
```
