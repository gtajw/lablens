"""Constrained units grammar. Never evaluate expressions supplied by users."""

import hashlib
import json
import math
import re

import pint

from .errors import Problem

REGISTRY = pint.UnitRegistry(autoconvert_offset_to_baseunit=False)
ATOMS = {
    "1",
    "m",
    "cm",
    "mm",
    "km",
    "s",
    "ms",
    "min",
    "h",
    "kg",
    "g",
    "mg",
    "K",
    "mol",
    "A",
    "N",
    "J",
    "W",
    "Pa",
    "kPa",
    "Hz",
    "V",
    "ohm",
    "C",
    "L",
    "mL",
    "rad",
    "deg",
    "delta_degC",
    "delta_degF",
    "degC",
    "degF",
}
GRAMMAR = re.compile(r"(?:[A-Za-z_]+|1)(?:\^-?\d{1,2})?(?:[*/](?:[A-Za-z_]+|1)(?:\^-?\d{1,2})?)*\Z")
REGISTRY_VERSION = f"pint-{pint.__version__}-lablens-units-1"
REGISTRY_CHECKSUM = hashlib.sha256(json.dumps(sorted(ATOMS)).encode()).hexdigest()


def parse_unit(value: str):
    text = value.strip().replace(" ", "").replace("**", "^")
    if not text or len(text) > 64 or not GRAMMAR.fullmatch(text):
        raise Problem("UNIT_UNKNOWN", "Use supported units such as m, s, m/s^2, or 1.")
    atoms = re.findall(r"[A-Za-z_]+", text)
    powers = re.findall(r"\^(-?\d+)", text)
    if any(a not in ATOMS for a in atoms) or any(abs(int(p)) > 12 for p in powers):
        raise Problem("UNIT_UNKNOWN", "That unit or exponent is not supported.")
    if any(a in {"degC", "degF"} for a in atoms) and text not in {"degC", "degF"}:
        raise Problem("UNIT_UNKNOWN", "Use delta_degC or delta_degF for temperature differences.")
    try:
        unit = REGISTRY.Unit(text.replace("^", "**"))
        magnitude = REGISTRY.Quantity(1, unit).to_base_units().magnitude
        if not math.isfinite(magnitude) or magnitude == 0:
            raise ValueError("Unit scale")
        return unit
    except (OverflowError, ValueError, pint.errors.PintError):
        raise Problem("UNIT_UNKNOWN", "This unit expression exceeds the supported scale.") from None


def dimensions(unit) -> dict:
    return {str(k): float(v) for k, v in sorted(unit.dimensionality.items())}


def unit_label(unit) -> str:
    return "1" if unit == REGISTRY.dimensionless else f"{unit:~}"


def canonical(unit):
    return REGISTRY.Quantity(1, unit).to_base_units().units


def is_offset(text: str) -> bool:
    return text.strip() in {"degC", "degF"}


def column_units(text: str) -> dict:
    unit = parse_unit(text)
    return {
        "unit_canonical": unit_label(canonical(unit)),
        "dimension_signature": dimensions(unit),
        "is_offset": is_offset(text),
    }
