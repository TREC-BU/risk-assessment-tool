from pathlib import Path

import pytest

from risktool.config import load_config

ROOT = Path(__file__).resolve().parents[1]

TASK_COLS = ["task_id", "person_class", "person", "use_case", "location", "task"]
HAZARD_COLS = ["hazard_id", "category", "hazard"]
SITUATION_COLS = ["situation_id", "task_id", "hazard_id", "situtation"]
MITIGATION_COLS = ["mitigation_id", "status", "type", "mitigation", "reduces",
                   "introduces_hazard", "implemented_in", "fat_ref", "design_ref"]
# The sheet's Harmful Events tab has a two-row header: "mitigations" and
# "mitigated_risk" only appear in the group row above.
EVENT_GROUP = ["Harm Definition", "", "", "", "", "Initial Risk", "", "", "", "",
               "mitigations", "Mitigated risk", "", "", "", "mitigated_risk"]
EVENT_COLS = ["event_id", "situation_id", "cause_type", "cause", "harm", "p0",
              "p0_justification", "s0", "s0_justification", "initial_risk", "", "p1",
              "p1_justification", "s1", "s1_justification", ""]


def _tab(title, header, rows, group=None):
    # Column A is empty in the real sheet, and two title rows sit above.
    grid = [["", title.upper()], ["", "Description text"]]
    if group:
        grid.append([""] + group)
    grid.append([""] + header)
    grid += [[""] + [str(c) for c in r] for r in rows]
    return grid


def make_sheet(tasks=(), hazards=(), situations=(), mitigations=(), events=()):
    return {
        "Tasks": _tab("Task definitions", TASK_COLS, tasks),
        "Hazards": _tab("Hazard definitions", HAZARD_COLS, hazards),
        "Situations": _tab("Situation definitions", SITUATION_COLS, situations),
        "Harmful Events": _tab("Harmful event definitions", EVENT_COLS, events,
                               group=EVENT_GROUP),
        "Mitigations": _tab("Mitigation definitions", MITIGATION_COLS, mitigations),
    }


def event(eid="HE_001", st="ST_001", cause="Cable snaps", harm="Fatal fall", p0=4, s0=5,
          mits="", p1="", s1="", p1j="", s1j=""):
    return [eid, st, "Equipment Failure", cause, harm, p0, "wear part", s0, "fatal fall", "",
            mits, p1, p1j, s1, s1j, ""]


@pytest.fixture(scope="session")
def config():
    return load_config(ROOT / "risk-config.typ")


@pytest.fixture
def base():
    """One hazard, a rider and a bystander task and situation, three mitigations."""
    return dict(
        tasks=[
            ["TS_001", "Untrained Person", "Rider", "Operate with Riders", "on ride",
             "Interacting with the amusement ride"],
            ["TS_002", "Untrained Person", "Bystander", "Operate with Riders", "queue",
             "Watching the ride"],
        ],
        hazards=[["HZ_001", "Stored Energy", "Raised ride vehicle at height"]],
        situations=[
            ["ST_001", "TS_001", "HZ_001", "rider seated while suspended"],
            ["ST_002", "TS_002", "HZ_001", "bystander under the tower"],
        ],
        mitigations=[
            ["M_001", "Proposed", "Administrative", "Daily cable inspection", "P", "",
             "Service Plan", "", ""],
            ["M_002", "Proposed", "Safeguarding", "Redundant cable", "P", "",
             "Mechanical & Structural Design", "FAT_003;FAT_039",
             "MSD_94.32.2 Redundant Suspension"],
            ["M_003", "Proposed", "Design", "Shock absorber", "S", "",
             "Mechanical & Structural Design", "FAT_040",
             "MSD_94.1.1 Drop Shaft Shock Absorber"],
        ],
    )
