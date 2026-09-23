"""Parse the four tabs, enforce the method rules and build the render data.

Every problem is reported against the tab and spreadsheet row it came from.
Errors stop the build; warnings are printed but don't.

PDR builds render only the method, hazards and initial scores, so rules about
mitigations and residual risk are downgraded to warnings there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ValidationError

from .config import MethodConfig
from .models import COMPUTED_FIELDS, CONTENT_FIELDS, MODELS, Hazard, Mitigation, Risk, Situation
from .sheets import KEY_HEADER, TABS, Grid, Row, SheetFormatError, parse_tab

Mode = Literal["pdr", "final"]

# Persons value that marks a rider situation (for the rider-only warning).
RIDER = "rider"


@dataclass
class Report:
    mode: Mode
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    data: dict | None = None

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")

    def residual(self, where: str, msg: str) -> None:
        """A mitigation/residual rule: an error for Final, a warning for PDR."""
        (self.error if self.mode == "final" else self.warn)(where, msg)


def _fmt_pydantic(exc: ValidationError) -> str:
    parts = []
    for e in exc.errors():
        loc = ".".join(str(p) for p in e["loc"]) or "row"
        msg = e["msg"].removeprefix("Value error, ")
        if e["type"] == "missing" or (e["type"] == "string_too_short" and not e["input"]):
            msg = "is required"
        parts.append(f"{loc} {msg}")
    return "; ".join(parts)


def _load_tab(tab: str, grid: Grid, report: Report) -> list[tuple[Row, BaseModel]]:
    model = MODELS[tab]
    try:
        rows = parse_tab(tab, grid)
    except SheetFormatError as exc:
        report.error(tab, str(exc).removeprefix(f"{tab}: "))
        return []

    if rows:
        present = set(rows[0].values)
        missing = [
            name for name, f in model.model_fields.items()
            if f.is_required() and name not in present
        ]
        if missing:
            report.error(tab, f"missing column(s) {', '.join(missing)}")
            return []

    out = []
    seen: dict[str, int] = {}
    key = KEY_HEADER[tab]
    for row in rows:
        if not any(row.get(f) for f in CONTENT_FIELDS[tab]):
            stray = [
                k for k, v in row.values.items()
                if v and k != key and k not in COMPUTED_FIELDS
                and not (k == "misuse" and v in ("0", "FALSE"))
            ]
            if stray:
                report.warn(row.where(), f"ignored: row has {', '.join(stray)} "
                            f"but no {' / '.join(CONTENT_FIELDS[tab])}")
            continue
        try:
            item = model.model_validate(
                {k: v for k, v in row.values.items() if k in model.model_fields}
            )
        except ValidationError as exc:
            report.error(row.where(), _fmt_pydantic(exc))
            continue
        ident = getattr(item, key)
        if ident in seen:
            report.error(row.where(), f"duplicate {key} (first used on row {seen[ident]})")
            continue
        seen[ident] = row.number
        out.append((row, item))
    return out


def validate(grids: dict[str, Grid], config: MethodConfig, mode: Mode) -> Report:
    report = Report(mode)
    loaded = {tab: _load_tab(tab, grids.get(tab, []), report) for tab in TABS}

    hazards: dict[str, Hazard] = {h.hazard_id: h for _, h in loaded["Hazards"]}
    situations: dict[str, Situation] = {s.situation_id: s for _, s in loaded["Situations"]}
    mitigations: dict[str, Mitigation] = {m.mitigation_id: m for _, m in loaded["Mitigations"]}

    for row, m in loaded["Mitigations"]:
        _check_mitigation(row, m, config, report)

    risks_out = []
    for row, r in loaded["Risks"]:
        risks_out.append(_check_risk(row, r, hazards, situations, mitigations, config, report))

    _coverage_warnings(loaded, situations, report)

    if report.ok:
        report.data = {
            "mode": mode,
            "hazards": [h.model_dump() for h in hazards.values()],
            "situations": [s.model_dump() for s in situations.values()],
            "mitigations": [
                {**m.model_dump(),
                 "risks": [r["risk_id"] for r in risks_out if m.mitigation_id in r["mitigations"]]}
                for m in mitigations.values()
            ],
            "risks": risks_out,
        }
    return report


def _check_mitigation(row: Row, m: Mitigation, config: MethodConfig, report: Report) -> None:
    mtype = config.mitigation_type(m.type)
    if mtype is None:
        names = ", ".join(t.name for t in config.mitigation_types)
        report.error(row.where(), f"type '{m.type}' is not one of {names}")
    else:
        m.type = mtype.name  # normalise capitalisation

    for ref in m.design_ref:
        prefix = ref.split("_", 1)[0]
        if prefix not in config.document_prefixes:
            known = ", ".join(config.document_prefixes) or "none configured"
            report.error(row.where(), f"design_ref '{ref}' has unknown document prefix "
                         f"'{prefix}' (known: {known})")


def _scores(config: MethodConfig, p: int, s: int) -> dict:
    return {"p": p, "s": s, "score": p * s, "band": config.band(s, p)}


def _check_risk(row, r: Risk, hazards, situations, mitigations, config: MethodConfig,
                report: Report) -> dict:
    where = row.where()
    if r.hazard_id not in hazards:
        report.error(where, f"hazard_id '{r.hazard_id}' is not on the Hazards tab")
    if r.situation_id not in situations:
        report.error(where, f"situation_id '{r.situation_id}' is not on the Situations tab")
    linked = []
    for mid in r.mitigations:
        if mid in mitigations:
            linked.append(mitigations[mid])
        else:
            report.error(where, f"mitigation '{mid}' is not on the Mitigations tab")

    if not r.p0_justification:
        report.warn(where, "p0 has no justification")
    if not r.s0_justification:
        report.warn(where, "s0 has no justification")

    initial = _scores(config, r.p0, r.s0)
    has_residual = r.p1 is not None or r.s1 is not None
    if has_residual and (r.p1 is None or r.s1 is None):
        report.error(where, "give both p1 and s1, or neither")
        has_residual = False

    p1 = r.p1 if has_residual else r.p0
    s1 = r.s1 if has_residual else r.s0
    residual = _scores(config, p1, s1)
    top = config.bands[-1].code

    if initial["band"] == top:
        if not r.mitigations:
            report.residual(where, f"initial risk is {config.band_name(top)} "
                            f"(P{r.p0} S{r.s0}) but no mitigations are linked")
        if not has_residual:
            report.residual(where, f"initial risk is {config.band_name(top)} "
                            "but residual scores p1/s1 are missing")
    elif r.mitigations and not has_residual and report.mode == "final":
        report.warn(where, "mitigations are linked but residual scores p1/s1 are blank; "
                    "residual taken as equal to initial")

    if has_residual:
        if r.p1 > r.p0 or r.s1 > r.s0:
            report.residual(where, f"residual (P{r.p1} S{r.s1}) is higher than initial "
                            f"(P{r.p0} S{r.s0})")
        if r.s1 < r.s0 and not any(
            "S" in m.reduces and (t := config.mitigation_type(m.type)) and t.lowers_severity
            for m in linked
        ):
            allowed = "/".join(t.name for t in config.mitigation_types if t.lowers_severity)
            report.residual(where, f"S drops {r.s0} → {r.s1} without a linked {allowed} "
                            "mitigation that reduces S")
        if r.p1 < r.p0 and not any("P" in m.reduces for m in linked):
            report.residual(where, f"P drops {r.p0} → {r.p1} without a linked mitigation "
                            "that reduces P")

    band = next(b for b in config.bands if b.code == residual["band"])
    # Unmitigated risks carry their initial band forward, so they need it too.
    if (band.justify and (has_residual or report.mode == "final")
            and not (r.p1_justification or r.s1_justification)):
        report.residual(where, f"residual risk is {band.name}; write a justification in "
                        "p1_justification or s1_justification")

    if config.rank(residual["band"]) > config.rank(config.acceptable_max):
        msg = (f"residual risk is {config.band_name(residual['band'])} "
               f"(P{p1} S{s1}); highest allowed for Final is "
               f"{config.band_name(config.acceptable_max)}")
        if report.mode == "final":
            report.error(where, msg)
        elif has_residual:
            report.warn(where, msg)

    if linked:
        weak = {m.type for m in linked
                if (t := config.mitigation_type(m.type)) and not t.lowers_severity}
        if all(m.type in weak for m in linked):
            report.warn(where, f"mitigated only by {'/'.join(sorted(weak))} measures")

    return {
        **r.model_dump(),
        "row": row.number,
        "initial": initial,
        "residual": {**residual, "assessed": has_residual},
    }


def _coverage_warnings(loaded, situations, report: Report) -> None:
    risks = [r for _, r in loaded["Risks"]]
    for row, h in loaded["Hazards"]:
        mine = [r for r in risks if r.hazard_id == h.hazard_id]
        if not mine:
            report.warn(row.where(), "hazard has no risks")
            continue
        persons = {situations[r.situation_id].persons.strip().lower()
                   for r in mine if r.situation_id in situations}
        if persons == {RIDER}:
            report.warn(row.where(), "hazard is assessed only against rider situations")
    for row, s in loaded["Situations"]:
        if not any(r.situation_id == s.situation_id for r in risks):
            report.warn(row.where(), "situation has no risks")
    for row, m in loaded["Mitigations"]:
        if not any(m.mitigation_id in r.mitigations for r in risks):
            report.warn(row.where(), "mitigation is not linked to any risk")
