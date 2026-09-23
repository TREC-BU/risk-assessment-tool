"""Load the method definitions from risk-config.typ via Typst introspection."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from pydantic import BaseModel, model_validator

LEVELS = ("1", "2", "3", "4", "5")


class Band(BaseModel):
    code: str
    name: str
    label: str
    color: str
    meaning: str
    justify: bool = False


class MitigationType(BaseModel):
    name: str
    lowers_severity: bool


class MethodConfig(BaseModel):
    bands: list[Band]
    matrix: dict[str, list[str]]
    acceptable_max: str
    mitigation_types: list[MitigationType]
    document_prefixes: dict[str, str]

    @model_validator(mode="after")
    def _check(self) -> "MethodConfig":
        codes = {b.code for b in self.bands}
        if set(self.matrix) != set(LEVELS):
            raise ValueError(f"matrix needs severity rows {', '.join(LEVELS)}")
        for s, row in self.matrix.items():
            if len(row) != 5:
                raise ValueError(f"matrix row {s} needs 5 entries, has {len(row)}")
            unknown = set(row) - codes
            if unknown:
                raise ValueError(f"matrix row {s} uses unknown bands {unknown}")
        if self.acceptable_max not in codes:
            raise ValueError(f"acceptable-max '{self.acceptable_max}' is not a band")
        return self

    def band(self, severity: int, probability: int) -> str:
        return self.matrix[str(severity)][probability - 1]

    def rank(self, code: str) -> int:
        """Position of a band from least (0) to most severe."""
        return [b.code for b in self.bands].index(code)

    def band_name(self, code: str) -> str:
        return next(b.name for b in self.bands if b.code == code)

    def mitigation_type(self, name: str) -> MitigationType | None:
        return next(
            (t for t in self.mitigation_types if t.name.lower() == name.lower()), None
        )


def _snake(obj):
    """Typst dictionary keys use kebab-case; Pydantic fields use snake_case."""
    if isinstance(obj, dict):
        return {k.replace("-", "_"): _snake(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_snake(v) for v in obj]
    return obj


def load_config(path: Path) -> MethodConfig:
    result = subprocess.run(
        [
            "typst", "eval", "query(<risk-config>).first().value",
            "--in", str(path), "--root", str(path.parent),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"typst could not read {path}:\n{result.stderr}")
    raw = json.loads(result.stdout)
    # Matrix and document-prefix keys are data, not field names; keep them as-is.
    return MethodConfig.model_validate(
        {**_snake({k: v for k, v in raw.items() if k != "document-prefixes"}),
         "document_prefixes": raw.get("document-prefixes", {})}
    )
