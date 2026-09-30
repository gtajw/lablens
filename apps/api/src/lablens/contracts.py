import math
import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import Problem
from .units import parse_unit

NUMERIC = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d{1,4})?\Z", re.ASCII)


def number(raw: str) -> float:
    if not isinstance(raw, str) or not 1 <= len(raw) <= 64 or not NUMERIC.fullmatch(raw):
        raise Problem("NUMERIC_LEXEME_INVALID", "Enter a decimal number, optionally in scientific notation.")
    value = float(raw)
    if not math.isfinite(value) or abs(value) > 1e100:
        raise Problem(
            "NUMERIC_LEXEME_INVALID", "Numbers must be finite and no larger than 1e100 in magnitude."
        )
    # A nonzero decimal silently underflowing to zero can invalidate reciprocal domains.
    if value == 0 and any(c in "123456789" for c in re.split("[eE]", raw)[0]):
        raise Problem(
            "NUMERIC_LEXEME_INVALID", "This number is too small for reliable double-precision input."
        )
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class ProjectCreate(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    course_label: str | None = Field(default=None, min_length=1, max_length=80)
    unit_label: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("title", "course_label", "unit_label")
    @classmethod
    def no_controls(cls, value):
        if value is not None and any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Control characters are not allowed.")
        return value


class ProjectPatch(StrictModel):
    expected_updated_at: datetime
    title: str = Field(min_length=1, max_length=120)
    course_label: str | None = Field(default=None, min_length=1, max_length=80)
    unit_label: str | None = Field(default=None, min_length=1, max_length=80)

    @model_validator(mode="after")
    def labels(self):
        ProjectCreate(**self.model_dump(exclude={"expected_updated_at"}))
        if self.expected_updated_at.tzinfo is None:
            raise ValueError("expected_updated_at must include a timezone.")
        return self


class Column(StrictModel):
    role: Literal["independent", "dependent"]
    position: int = Field(ge=0, le=1, strict=True)
    name: str = Field(min_length=1, max_length=64)
    symbol: str | None = Field(default=None, min_length=1, max_length=32)
    unit_input: str = Field(min_length=1, max_length=64)

    @field_validator("name", "symbol")
    @classmethod
    def label(cls, value):
        return ProjectCreate.no_controls(value)

    @field_validator("unit_input")
    @classmethod
    def unit(cls, value):
        parse_unit(value)
        return value


class Cell(StrictModel):
    raw: str = Field(min_length=1, max_length=64)
    value: float = Field(strict=True)

    @model_validator(mode="after")
    def matches(self):
        parsed = number(self.raw)
        if parsed != self.value:
            raise Problem("NUMERIC_LEXEME_MISMATCH", "The numeric value does not match its original text.")
        return self


class Row(StrictModel):
    x: Cell
    y: Cell


class DatasetMetadata(StrictModel):
    display_name: str = Field(min_length=1, max_length=120)
    columns: list[Column] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def distinct_columns(self):
        ProjectCreate.no_controls(self.display_name)
        if {c.role for c in self.columns} != {"independent", "dependent"}:
            raise ValueError("Choose exactly one independent and one dependent variable.")
        if {c.position for c in self.columns} != {0, 1} or len({c.name for c in self.columns}) != 2:
            raise ValueError("Column positions and names must be distinct.")
        return self


class ManualDataset(DatasetMetadata):
    rows: list[Row] = Field(min_length=2, max_length=5000)


class Transform(StrictModel):
    kind: Literal["identity", "square", "square_root", "reciprocal"]
    input_role: Literal["independent", "dependent"]
    time_origin_shift: float | None = Field(default=None, ge=-1e100, le=1e100, strict=True)


class Model(StrictModel):
    family: Literal["linear", "quadratic"]
    intercept_policy: Literal["free", "fixed_zero"]
    intercept_rationale: str | None = Field(default=None, max_length=280)
    fit_method: Literal["ordinary_least_squares"] = "ordinary_least_squares"

    @model_validator(mode="after")
    def rationale(self):
        if self.intercept_policy == "fixed_zero":
            if not self.intercept_rationale or len(self.intercept_rationale) < 10:
                raise ValueError("Explain the physical reason for a zero intercept in 10–280 characters.")
            ProjectCreate.no_controls(self.intercept_rationale)
        elif self.intercept_rationale is not None:
            raise ValueError("Rationale must be null when the intercept is free.")
        return self


class Claim(StrictModel):
    coefficient_key: Literal["linear", "quadratic"]
    unit_input: str = Field(min_length=1, max_length=64)

    @field_validator("unit_input")
    @classmethod
    def unit(cls, value):
        parse_unit(value)
        return value


class AnalysisRequest(StrictModel):
    dataset_version_id: UUID
    x_transform: Transform
    y_transform: Transform = Transform(kind="identity", input_role="dependent")
    model: Model
    student_claim: Claim | None = None
    display_precision: int = Field(default=6, ge=3, le=10, strict=True)

    @model_validator(mode="after")
    def compatible(self):
        if self.x_transform.input_role != "independent":
            raise ValueError("The x transform must apply to the independent variable.")
        if self.y_transform != Transform(kind="identity", input_role="dependent"):
            raise ValueError("Only an unchanged dependent variable is supported.")
        if (
            self.student_claim
            and self.student_claim.coefficient_key == "quadratic"
            and self.model.family != "quadratic"
        ):
            raise ValueError("A quadratic coefficient exists only in a quadratic model.")
        return self


class ExplanationRequest(StrictModel):
    reading_level: Literal["concise", "standard", "detailed"] = "standard"
    locale: Literal["en-US"] = "en-US"
    focus_rule_ids: list[str] | None = Field(default=None, min_length=1, max_length=10)

    @field_validator("focus_rule_ids")
    @classmethod
    def distinct(cls, value):
        if value is not None and len(value) != len(set(value)):
            raise ValueError("Finding IDs must be unique.")
        return value


class ExportRequest(StrictModel):
    format: Literal["json"] = "json"
    include_explanation_id: UUID | None = None
