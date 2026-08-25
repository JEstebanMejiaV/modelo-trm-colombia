"""Tipos de dominio compartidos por contratos, productos y provenance."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class FactorTerm:
    component: str
    lag_months: int
    availability_lag_months: int | None = None

    def __post_init__(self) -> None:
        if not self.component.strip():
            raise ValueError("FactorTerm.component no puede estar vacío")
        if self.lag_months < 0:
            raise ValueError("FactorTerm.lag_months debe ser no negativo")
        if self.availability_lag_months is not None and self.availability_lag_months < 0:
            raise ValueError("FactorTerm.availability_lag_months debe ser no negativo")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        if value["availability_lag_months"] is None:
            value.pop("availability_lag_months")
        return value


@dataclass(frozen=True)
class FactorSpec:
    factor_id: str
    label: str
    group: str
    terms: tuple[FactorTerm, ...]
    information_set: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.factor_id.strip() or not self.label.strip() or not self.group.strip():
            raise ValueError("FactorSpec requiere factor_id, label y group")
        if not self.terms:
            raise ValueError("FactorSpec requiere al menos un término")

    @classmethod
    def from_legacy(
        cls,
        factor_id: str,
        legacy_spec: Mapping[str, Any],
        information_set: str | None = None,
    ) -> "FactorSpec":
        terms = tuple(
            FactorTerm(component=str(component), lag_months=int(lag))
            for component, lag in legacy_spec["terminos"]
        )
        return cls(
            factor_id=factor_id,
            label=factor_id,
            group=str(legacy_spec.get("grupo", "sin_clasificar")),
            terms=terms,
            information_set=information_set,
        )

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema_version": self.schema_version,
            "factor_id": self.factor_id,
            "label": self.label,
            "group": self.group,
            "terms": [term.to_dict() for term in self.terms],
        }
        if self.information_set is not None:
            value["information_set"] = self.information_set
        return value


@dataclass(frozen=True)
class ProductSpec:
    product_id: str
    label: str
    frequency: str
    information_set: str
    status: str
    source_of_truth: str
    vintage_policy: str = "latest_available"
    benchmark: str | None = None
    horizon_months: int | None = None
    horizon_days: int | None = None
    schema_version: int = 1
    validation: Mapping[str, Any] = field(default_factory=dict)
    model: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ProductSpec":
        known = {
            "schema_version",
            "product_id",
            "label",
            "frequency",
            "information_set",
            "status",
            "source_of_truth",
            "vintage_policy",
            "benchmark",
            "horizon_months",
            "horizon_days",
            "validation",
            "model",
        }
        unknown = set(value) - known
        if unknown:
            raise ValueError(f"Campos de producto no reconocidos: {sorted(unknown)}")
        return cls(
            schema_version=int(value.get("schema_version", 1)),
            product_id=str(value["product_id"]),
            label=str(value["label"]),
            frequency=str(value["frequency"]),
            information_set=str(value["information_set"]),
            status=str(value["status"]),
            source_of_truth=str(value["source_of_truth"]),
            vintage_policy=str(value.get("vintage_policy", "latest_available")),
            benchmark=value.get("benchmark"),
            horizon_months=value.get("horizon_months"),
            horizon_days=value.get("horizon_days"),
            validation=dict(value.get("validation", {})),
            model=dict(value.get("model", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["validation"] = dict(self.validation)
        return value
