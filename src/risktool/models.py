"""Row models for the four data tabs.

Pydantic handles per-cell parsing (types, score ranges, list splitting).
Cross-row and method rules live in validate.py because they need the config.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

_LIST_SPLIT = re.compile(r"[;,\n]")


def _blank_to_none(v):
    return None if isinstance(v, str) and not v.strip() else v


def _score(v):
    v = _blank_to_none(v)
    if isinstance(v, str):
        try:
            f = float(v)
        except ValueError:
            raise ValueError(f"'{v}' is not a number") from None
        if not f.is_integer():
            raise ValueError(f"'{v}' is not a whole number")
        return int(f)
    return v


def _id_list(v):
    if isinstance(v, str):
        return [t.strip() for t in _LIST_SPLIT.split(v) if t.strip()]
    return v


def _reduces(v):
    if isinstance(v, str):
        tokens = [t.strip().upper() for t in re.split(r"[;,\s/&]+", v) if t.strip()]
        bad = [t for t in tokens if t not in ("P", "S")]
        if bad:
            raise ValueError(f"must be P, S or both (got '{v}')")
        return tokens
    return v


def _flag(v):
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("", "0", "false", "no", "n"):
            return False
        if s in ("1", "true", "yes", "y"):
            return True
        raise ValueError(f"'{v}' is not 0/1")
    return v


Level = Annotated[int, Field(ge=1, le=5)]
Score = Annotated[Level, BeforeValidator(_score)]
OptScore = Annotated[Level | None, BeforeValidator(_score)]
Text = Annotated[str, Field(min_length=1)]
IdList = Annotated[list[str], BeforeValidator(_id_list)]


class Hazard(BaseModel):
    hazard_id: Text
    category: Text
    hazard: Text


class Situation(BaseModel):
    situation_id: Text
    persons: Text
    ride_phase: Text
    misuse: Annotated[bool, BeforeValidator(_flag)] = False
    situation: Text


class Mitigation(BaseModel):
    mitigation_id: Text
    type: Text
    mitigation: Text
    reduces: Annotated[list[str], BeforeValidator(_reduces), Field(min_length=1)]
    implemented_in: str = ""
    fat_ref: IdList = []
    design_ref: IdList = []


class Risk(BaseModel):
    risk_id: Text
    hazard_id: Text
    situation_id: Text
    event: Text
    p0: Score
    p0_justification: str = ""
    s0: Score
    s0_justification: str = ""
    mitigations: IdList = []
    p1: OptScore = None
    p1_justification: str = ""
    s1: OptScore = None
    s1_justification: str = ""


MODELS = {
    "Hazards": Hazard,
    "Situations": Situation,
    "Mitigations": Mitigation,
    "Risks": Risk,
}

# A row counts as filled in once any of these has a value. The sheet
# pre-numbers IDs and pre-fills formulas and defaults (misuse = 0,
# initial_risk = 0), so those don't count.
CONTENT_FIELDS = {
    "Hazards": ("category", "hazard"),
    "Situations": ("persons", "ride_phase", "situation"),
    "Mitigations": ("type", "mitigation"),
    "Risks": ("hazard_id", "situation_id", "event"),
}

# Spreadsheet formula columns; recomputed here, never read.
COMPUTED_FIELDS = {"initial_risk", "mitigated_risk"}
