"""Typed vector filter for targeting rules."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class FilterOp(str, Enum):
    """Supported filter operators."""

    equals = "equals"           # field == value
    any_of = "any_of"           # field in [values]
    all_of = "all_of"           # field contains all of [values]
    not_equals = "not_equals"   # field != value
    not_in = "not_in"           # field not in [values]


class FieldFilter(BaseModel):
    """A single typed filter condition on a payload field."""

    field: str = Field(..., description="Payload field name")
    op: FilterOp = Field(..., description="Filter operator")
    value: str | list[str] = Field(..., description="Comparison value(s)")


class VectorFilter(BaseModel):
    """Typed filter for vector queries."""

    must: list[FieldFilter] = Field(default_factory=list)
    must_not: list[FieldFilter] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.must and not self.must_not
