"""Traceable IFC-material -> radio-material mapping. Every result is an explicit ASSUMPTION.

No electromagnetic numbers live here: ``em_materials`` reference ITU-R P.2040 types (as tabulated
in Sionna RT) together with their documented frequency validity ranges.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class MaterialConfigError(ValueError):
    """The materials configuration is inconsistent or unreadable."""


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmMaterial(_M):
    itu_type: str
    valid_frequency_ranges_ghz: list[tuple[float, float]] = Field(min_length=1)
    source: str = Field(min_length=3)  # traceability is mandatory


class Rule(_M):
    id: str
    priority: int
    em_material: str
    pattern: str

    @field_validator("pattern")
    @classmethod
    def _compiles(cls, v: str) -> str:
        try:
            re.compile(v)
        except re.error as exc:
            raise ValueError(f"invalid regex: {exc}") from exc
        return v


class MaterialConfig(_M):
    version: int
    composite_policy: Literal["priority"] = "priority"
    em_materials: dict[str, EmMaterial]
    rules: list[Rule]
    category_fallbacks: dict[str, str] = Field(default_factory=dict)
    overrides: dict[str, str] = Field(default_factory=dict)


class MaterialAssignment(_M):
    """Result for one element. ``status`` is never 'verified': all mappings are assumptions."""

    ifc_material_names: list[str] = Field(default_factory=list)
    em_material: str | None = None
    status: Literal["user_override", "assumed_from_name", "assumed_from_category", "unmapped"]
    rule: str | None = None
    candidates: list[str] = Field(default_factory=list)
    composite: bool = False  # several different radio classes matched: priority decided
    basis: str = ""


def load_material_config(path: Path | str) -> MaterialConfig:
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        cfg = MaterialConfig.model_validate(raw)
    except FileNotFoundError as exc:
        raise MaterialConfigError(f"materials config not found: {p}") from exc
    except (yaml.YAMLError, ValidationError, TypeError) as exc:
        raise MaterialConfigError(f"invalid materials config {p}: {exc}") from exc

    known = set(cfg.em_materials)
    ids = [r.id for r in cfg.rules]
    if len(ids) != len(set(ids)):
        raise MaterialConfigError("duplicate rule ids")
    for r in cfg.rules:
        if r.em_material not in known:
            raise MaterialConfigError(f"rule '{r.id}' uses unknown em_material '{r.em_material}'")
    for where, mapping in (
        ("category_fallbacks", cfg.category_fallbacks),
        ("overrides", cfg.overrides),
    ):
        for key, em in mapping.items():
            if em not in known:
                raise MaterialConfigError(f"{where}['{key}'] uses unknown em_material '{em}'")
    return cfg


class MaterialMapper:
    def __init__(self, config: MaterialConfig):
        self.config = config
        self._rules = sorted(config.rules, key=lambda r: r.priority)
        self._compiled = [(r, re.compile(r.pattern)) for r in self._rules]

    @classmethod
    def from_file(cls, path: Path | str) -> MaterialMapper:
        return cls(load_material_config(path))

    def assign(
        self, category: str, ifc_material_names: list[str], global_id: str | None = None
    ) -> MaterialAssignment:
        names = [n for n in ifc_material_names if n]
        if global_id and global_id in self.config.overrides:
            return MaterialAssignment(
                ifc_material_names=names,
                em_material=self.config.overrides[global_id],
                status="user_override",
                rule="override",
                basis="explicit override by GlobalId in the materials config",
            )
        hits: list[tuple[int, str, str]] = []  # (priority, em_material, rule id)
        for name in names:
            for rule, rx in self._compiled:
                if rx.search(name):
                    hits.append((rule.priority, rule.em_material, rule.id))
                    break  # first (highest-priority) rule that matches this name
        if hits:
            hits.sort()
            candidates = list(dict.fromkeys(em for _, em, _ in hits))
            return MaterialAssignment(
                ifc_material_names=names,
                em_material=hits[0][1],
                status="assumed_from_name",
                rule=hits[0][2],
                candidates=candidates,
                composite=len(candidates) > 1,
                basis="ASSUMPTION: radio class guessed from IFC material names (not verified)",
            )
        fallback = self.config.category_fallbacks.get(category)
        if fallback:
            return MaterialAssignment(
                ifc_material_names=names,
                em_material=fallback,
                status="assumed_from_category",
                rule=f"fallback:{category}",
                basis=(
                    f"ASSUMPTION: no material name matched; default for IFC category '{category}'"
                ),
            )
        return MaterialAssignment(
            ifc_material_names=names, status="unmapped", basis="no rule and no category fallback"
        )

    def frequency_coverage(self, frequency_hz: float) -> dict[str, bool]:
        """For each radio material: is the simulation frequency inside a documented range?"""
        ghz = frequency_hz / 1e9
        return {
            name: any(lo <= ghz <= hi for lo, hi in m.valid_frequency_ranges_ghz)
            for name, m in self.config.em_materials.items()
        }
