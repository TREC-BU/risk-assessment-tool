from pathlib import Path

import pytest

from risktool.config import load_config

ROOT = Path(__file__).resolve().parents[1]

HAZARD_COLS = ["hazard_id", "category", "hazard"]
SITUATION_COLS = ["situation_id", "persons", "ride_phase", "misuse", "situtation"]
MITIGATION_COLS = ["mitigation_id", "type", "mitigation", "reduces", "implemented_in",
                   "fat_ref", "design_ref"]
# The sheet's Risks tab has a two-row header: "mitigations" and
# "mitigated_risk" only appear in the group row above.
RISK_GROUP = ["Risk Defenition", "", "", "", "Initial Risk", "", "", "", "", "mitigations",
              "Mitigated risk", "", "", "", "mitigated_risk"]
RISK_COLS = ["risk_id", "hazard_id", "situation_id", "event", "p0", "p0_justification", "s0",
             "s0_justification", "initial_risk", "", "p1", "p1_justification", "s1",
             "s1_justification", ""]


def _tab(title, header, rows, group=None):
    # Column A is empty in the real sheet, and two title rows sit above.
    grid = [["", title.upper()], ["", "Description text"]]
    if group:
        grid.append([""] + group)
    grid.append([""] + header)
    grid += [[""] + [str(c) for c in r] for r in rows]
    return grid


def make_sheet(hazards=(), situations=(), mitigations=(), risks=()):
    return {
        "Hazards": _tab("Hazard definitions", HAZARD_COLS, hazards),
        "Situations": _tab("Situation definitions", SITUATION_COLS, situations),
        "Mitigations": _tab("Mitigation definitions", MITIGATION_COLS, mitigations),
        "Risks": _tab("Risks definitions", RISK_COLS, risks, group=RISK_GROUP),
    }


def risk(rid="RK_001", hz="HZ_001", st="ST_001", event="Cable snaps", p0=4, s0=5,
         mits="", p1="", s1="", p1j="", s1j=""):
    return [rid, hz, st, event, p0, "wear part", s0, "fatal fall", "", mits, p1, p1j, s1, s1j, ""]


@pytest.fixture(scope="session")
def config():
    return load_config(ROOT / "risk-config.typ")


@pytest.fixture
def base():
    """One hazard, one rider and one bystander situation, three mitigations."""
    return dict(
        hazards=[["HZ_001", "Stored Energy", "Raised ride vehicle at height"]],
        situations=[
            ["ST_001", "Rider", "Ride Cycle", "0", "rider seated while suspended"],
            ["ST_002", "Bystander", "Ride Cycle", "0", "bystander under the tower"],
        ],
        mitigations=[
            ["M_001", "Administrative", "Daily cable inspection", "P", "Service Plan", "", ""],
            ["M_002", "Safeguarding", "Redundant cable", "P", "Mechanical & Structural Design",
             "FAT_003;FAT_039", "MSD_94.32.2 Redundant Suspension"],
            ["M_003", "Design", "Shock absorber", "S", "Mechanical & Structural Design",
             "FAT_040", "MSD_94.1.1 Drop Shaft Shock Absorber"],
        ],
    )
