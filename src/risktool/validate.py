"""Parse the five tabs, enforce the method rules and build the render data.

Every problem is reported against the tab and spreadsheet row it came from,
at one of three levels:

- error: the sheet can't be read as written (bad IDs, unknown types, malformed
  cells). Stops the build, since the PDF can't render it.
- warning: the method isn't satisfied yet (unmitigated or unjustified harmful
  event, residual above `acceptable-max`). The document is living, so these never
  stop the build.
- info: worth a look, e.g. a hazard with no harmful events.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from .config import MethodConfig
from .models import (
    COMPUTED_FIELDS, CONTENT_FIELDS, DEFAULT_FIELDS, MODELS, HarmfulEvent, Hazard, Mitigation,
    Situation, Task,
)
from .sheets import KEY_HEADER, TABS, Grid, Row, SheetFormatError, parse_tab

# Tasks person value that marks a rider (for the rider-only note).
RIDER = "rider"


@dataclass(frozen=True)
class Issue:
    """One problem, located by tab and (when it has one) spreadsheet row."""
    tab: str
    message: str
    row: int | None = None
    ident: str = ""

    @property
    def where(self) -> str:
        if self.row is None:
            return self.tab
        return f"{self.tab} row {self.row}" + (f" ({self.ident})" if self.ident else "")

    def __str__(self) -> str:
        return f"{self.where}: {self.message}"


def _issue(where: Row | str, msg: str) -> Issue:
    if isinstance(where, Row):
        return Issue(where.tab, msg, where.number, where.get(KEY_HEADER[where.tab]))
    return Issue(where, msg)


@dataclass
class Report:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    info: list[Issue] = field(default_factory=list)
    data: dict | None = None

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, where: Row | str, msg: str) -> None:
        self.errors.append(_issue(where, msg))

    def warn(self, where: Row | str, msg: str) -> None:
        self.warnings.append(_issue(where, msg))

    def note(self, where: Row | str, msg: str) -> None:
        self.info.append(_issue(where, msg))


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
                if v and k != key and k not in COMPUTED_FIELDS and k not in DEFAULT_FIELDS
            ]
            if stray:
                report.note(row, f"ignored: row has {', '.join(stray)} "
                            f"but no {' / '.join(CONTENT_FIELDS[tab])}")
            continue
        try:
            item = model.model_validate(
                {k: v for k, v in row.values.items() if k in model.model_fields}
            )
        except ValidationError as exc:
            report.error(row, _fmt_pydantic(exc))
            continue
        ident = getattr(item, key)
        if ident in seen:
            report.error(row, f"duplicate {key} (first used on row {seen[ident]})")
            continue
        seen[ident] = row.number
        out.append((row, item))
    return out


def validate(grids: dict[str, Grid], config: MethodConfig) -> Report:
    report = Report()
    loaded = {tab: _load_tab(tab, grids.get(tab, []), report) for tab in TABS}

    tasks: dict[str, Task] = {t.task_id: t for _, t in loaded["Tasks"]}
    hazards: dict[str, Hazard] = {h.hazard_id: h for _, h in loaded["Hazards"]}
    situations: dict[str, Situation] = {s.situation_id: s for _, s in loaded["Situations"]}
    mitigations: dict[str, Mitigation] = {m.mitigation_id: m for _, m in loaded["Mitigations"]}

    for row, s in loaded["Situations"]:
        if s.task_id not in tasks:
            report.error(row, f"task_id '{s.task_id}' is not on the Tasks tab")
        if s.hazard_id not in hazards:
            report.error(row, f"hazard_id '{s.hazard_id}' is not on the Hazards tab")

    for row, m in loaded["Mitigations"]:
        _check_mitigation(row, m, hazards, config, report)

    events_out = []
    for row, e in loaded["Harmful Events"]:
        events_out.append(_check_event(row, e, situations, mitigations, config, report))

    _coverage_notes(loaded, tasks, situations, report)

    if report.ok:
        report.data = {
            "tasks": [t.model_dump() for t in tasks.values()],
            "hazards": [h.model_dump() for h in hazards.values()],
            "situations": [s.model_dump() for s in situations.values()],
            "events": events_out,
            "mitigations": [
                {**m.model_dump(),
                 "events": [e["event_id"] for e in events_out
                            if m.mitigation_id in e["mitigations"]]}
                for m in mitigations.values()
            ],
        }
    return report


def _check_mitigation(row: Row, m: Mitigation, hazards, config: MethodConfig,
                      report: Report) -> None:
    mtype = config.mitigation_type(m.type)
    if mtype is None:
        names = ", ".join(t.name for t in config.mitigation_types)
        report.error(row, f"type '{m.type}' is not one of {names}")
    else:
        m.type = mtype.name  # normalise capitalisation

    for ref in m.design_ref:
        prefix = ref.split("_", 1)[0]
        if prefix not in config.document_prefixes:
            known = ", ".join(config.document_prefixes) or "none configured"
            report.error(row, f"design_ref '{ref}' has unknown document prefix "
                         f"'{prefix}' (known: {known})")

    for hid in m.introduces_hazard:
        if hid not in hazards:
            report.error(row, f"introduces_hazard '{hid}' is not on the Hazards tab")

    if not m.reduces:
        report.warn(row, "reduces is blank; give P, S or both")


def _scores(config: MethodConfig, p: int, s: int) -> dict:
    return {"p": p, "s": s, "score": p * s, "band": config.band(s, p)}


def _check_event(row, r: HarmfulEvent, situations, mitigations, config: MethodConfig,
                 report: Report) -> dict:
    where = row
    if r.situation_id not in situations:
        report.error(where, f"situation_id '{r.situation_id}' is not on the Situations tab")
    linked = []
    for mid in r.mitigations:
        if mid in mitigations:
            linked.append(mitigations[mid])
        else:
            report.error(where, f"mitigation '{mid}' is not on the Mitigations tab")

    if not r.p0_justification:
        report.note(where, "p0 has no justification")
    if not r.s0_justification:
        report.note(where, "s0 has no justification")

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
            report.warn(where, f"initial risk is {config.band_name(top)} "
                            f"(P{r.p0} S{r.s0}) but no mitigations are linked")
        if not has_residual:
            report.warn(where, f"initial risk is {config.band_name(top)} "
                            "but residual scores p1/s1 are missing")
    elif r.mitigations and not has_residual:
        report.note(where, "mitigations are linked but residual scores p1/s1 are blank; "
                    "residual taken as equal to initial")

    if has_residual:
        if r.p1 > r.p0 or r.s1 > r.s0:
            report.warn(where, f"residual (P{r.p1} S{r.s1}) is higher than initial "
                            f"(P{r.p0} S{r.s0})")
        if r.s1 < r.s0 and not any(
            "S" in m.reduces and (t := config.mitigation_type(m.type)) and t.lowers_severity
            for m in linked
        ):
            allowed = "/".join(t.name for t in config.mitigation_types if t.lowers_severity)
            report.warn(where, f"S drops {r.s0} → {r.s1} without a linked {allowed} "
                            "mitigation that reduces S")
        if r.p1 < r.p0 and not any("P" in m.reduces for m in linked):
            report.warn(where, f"P drops {r.p0} → {r.p1} without a linked mitigation "
                            "that reduces P")

    band = next(b for b in config.bands if b.code == residual["band"])
    # Unmitigated risks carry their initial band forward, so they need it too.
    if band.justify and not (r.p1_justification or r.s1_justification):
        report.warn(where, f"residual risk is {band.name}; write a justification in "
                        "p1_justification or s1_justification")

    if config.rank(residual["band"]) > config.rank(config.acceptable_max):
        report.warn(where, f"residual risk is {config.band_name(residual['band'])} "
                    f"(P{p1} S{s1}); highest acceptable is "
                    f"{config.band_name(config.acceptable_max)}")

    if linked:
        weak = {m.type for m in linked
                if (t := config.mitigation_type(m.type)) and not t.lowers_severity}
        if all(m.type in weak for m in linked):
            report.note(where, f"mitigated only by {'/'.join(sorted(weak))} measures")

    situation = situations.get(r.situation_id)
    return {
        **r.model_dump(),
        "hazard_id": situation.hazard_id if situation else "",
        "row": row.number,
        "initial": initial,
        "residual": {**residual, "assessed": has_residual},
    }


def _coverage_notes(loaded, tasks, situations, report: Report) -> None:
    events = [e for _, e in loaded["Harmful Events"]]
    for row, h in loaded["Hazards"]:
        mine = [s for s in situations.values() if s.hazard_id == h.hazard_id
                and any(e.situation_id == s.situation_id for e in events)]
        if not mine:
            report.note(row, "hazard has no harmful events")
            continue
        persons = {tasks[s.task_id].person.strip().lower() for s in mine if s.task_id in tasks}
        if persons == {RIDER}:
            report.note(row, "hazard is assessed only against rider tasks")
    for row, t in loaded["Tasks"]:
        if not any(s.task_id == t.task_id for s in situations.values()):
            report.note(row, "task has no hazardous situations")
    for row, s in loaded["Situations"]:
        if not any(e.situation_id == s.situation_id for e in events):
            report.note(row, "situation has no harmful events")
    for row, m in loaded["Mitigations"]:
        if not any(m.mitigation_id in e.mitigations for e in events):
            report.note(row, "mitigation is not linked to any harmful event")
