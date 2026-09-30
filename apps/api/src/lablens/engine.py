"""Versioned, deterministic dimensional analysis and ordinary least squares.

No I/O, prompts, database connections, network access, or mutable input arrays.
The boundary accepts validated contracts but independently rechecks the snapshot.
"""

import hashlib
import json
import math

import numpy as np
from scipy import linalg

from .contracts import AnalysisRequest, ManualDataset
from .units import (
    REGISTRY,
    REGISTRY_CHECKSUM,
    REGISTRY_VERSION,
    canonical,
    dimensions,
    is_offset,
    parse_unit,
    unit_label,
)

ENGINE_VERSION = "1.0.0"
RULESET_VERSION = "1.0.0"
RULES = {
    "INPUT.DATASET_INVARIANT_BROKEN": (
        "error",
        True,
        "The saved dataset failed its integrity check. Import a fresh copy.",
    ),
    "UNIT.OFFSET_TRANSFORM_UNSAFE": (
        "error",
        True,
        "Use Kelvin for absolute temperature, or a delta unit for a temperature difference, before this operation.",
    ),
    "TRANSFORM.DOMAIN_INVALID": (
        "error",
        True,
        "The transform is undefined for one or more rows. Correct the data or choose another transform.",
    ),
    "TRANSFORM.RESULT_NONFINITE": (
        "error",
        True,
        "This transform exceeds the supported numerical range. Rescale the experiment or choose another transform.",
    ),
    "MODEL.INSUFFICIENT_POINTS": (
        "error",
        True,
        "Add more measurements: the fit needs at least one residual degree of freedom.",
    ),
    "MODEL.INSUFFICIENT_DISTINCT_X": (
        "error",
        True,
        "The model needs more distinct transformed x values to identify its coefficients.",
    ),
    "MODEL.BASIS_NONFINITE": (
        "error",
        True,
        "A polynomial term exceeds double-precision range. Choose a lower-degree model or a different transform.",
    ),
    "MODEL.DESIGN_MATRIX_RANK_DEFICIENT": (
        "error",
        True,
        "The measured x values cannot independently identify all model coefficients.",
    ),
    "MODEL.CONDITION_NUMBER_EXTREME": (
        "error",
        True,
        "The fit is too sensitive to small changes to report reliable coefficients. Collect more widely spaced measurements.",
    ),
    "MODEL.CONDITION_NUMBER_HIGH": (
        "warning",
        False,
        "Small changes in the data may cause large changes in these coefficients.",
    ),
    "MODEL.RESULT_UNREPRESENTABLE": (
        "error",
        True,
        "A result falls outside reliable double-precision range. Change the scale of the experiment.",
    ),
    "MODEL.FIXED_ZERO_ASSUMPTION": (
        "warning",
        False,
        "A zero intercept is an assumption you chose. Explain why zero transformed x should imply zero y in this experiment.",
    ),
    "MODEL.SHIFT_WITH_FIXED_ZERO": (
        "warning",
        False,
        "Shifting the origin changes where the model is forced through zero. Check this against the physical setup.",
    ),
    "UNIT.COEFFICIENT_DIMENSION_MISMATCH": (
        "error",
        False,
        "The claimed coefficient unit has different dimensions from the fitted coefficient. Divide the y unit by the unit of its x term.",
    ),
    "METRIC.R_SQUARED_UNDEFINED": (
        "info",
        False,
        "R² is undefined because all y values are identical. The coefficients and residuals remain available.",
    ),
    "INTERPRETATION.FIT_NOT_PHYSICAL_PROOF": (
        "info",
        False,
        "A close fit does not establish a physical law. Check your model assumptions, measurement procedure, and residual pattern.",
    ),
}


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def snapshot_payload(dataset: ManualDataset) -> dict:
    return {
        "columns": [c.model_dump() for c in sorted(dataset.columns, key=lambda c: c.position)],
        "rows": [r.model_dump() for r in dataset.rows],
    }


def snapshot_hash(dataset: ManualDataset) -> str:
    return digest(snapshot_payload(dataset))


def finding(rule: str, evidence: dict | None = None) -> dict:
    severity, blocking, message = RULES[rule]
    return {
        "rule_id": rule,
        "rule_version": 1,
        "severity": severity,
        "blocking": blocking,
        "message_key": rule,
        "message": message,
        "evidence": evidence or {},
        "evidence_schema_version": 1,
    }


def offending(mask: np.ndarray) -> dict:
    indices = np.flatnonzero(mask).tolist()
    return {"offending_indices": indices[:20], "offending_count": len(indices)}


def run_analysis(dataset: ManualDataset, request: AnalysisRequest, expected_hash: str | None = None) -> dict:
    """Always returns a JSON-serializable terminal result; never silently removes rows."""
    content_hash = snapshot_hash(dataset)
    config = request.model_dump(mode="json")
    scientific_config = {
        k: v for k, v in config.items() if k not in {"dataset_version_id", "display_precision"}
    }
    provenance = {
        "engine_version": ENGINE_VERSION,
        "rule_set_version": RULESET_VERSION,
        "unit_registry_version": REGISTRY_VERSION,
        "unit_registry_checksum": REGISTRY_CHECKSUM,
        "dataset_sha256": content_hash,
        "request": config,
        "scientific_sha256": digest(
            {
                "dataset": content_hash,
                "configuration": scientific_config,
                "engine": ENGINE_VERSION,
                "rules": RULESET_VERSION,
            }
        ),
    }
    findings: list[dict] = []

    def reject(rule: str, evidence: dict | None = None, status: str = "rejected"):
        return {"status": status, "provenance": provenance, "findings": findings + [finding(rule, evidence)]}

    if expected_hash is not None and expected_hash != content_hash:
        return reject("INPUT.DATASET_INVARIANT_BROKEN", status="failed")
    columns = {c.role: c for c in dataset.columns}
    xunit, yunit = (parse_unit(columns[r].unit_input) for r in ("independent", "dependent"))
    ux, uy = canonical(xunit), canonical(yunit)
    kind = request.x_transform.kind
    shift = request.x_transform.time_origin_shift
    fixed = request.model.intercept_policy == "fixed_zero"
    degree = 1 if request.model.family == "linear" else 2
    xoffset, yoffset = (is_offset(columns[r].unit_input) for r in ("independent", "dependent"))
    provenance["original_units"] = {"x": str(xunit), "y": str(yunit)}
    provenance["canonical_units"] = {"x": unit_label(ux), "y": unit_label(uy)}
    if (xoffset and (kind != "identity" or degree > 1 or fixed or shift is not None)) or (yoffset and fixed):
        return reject("UNIT.OFFSET_TRANSFORM_UNSAFE")
    power = {"identity": 1, "square": 2, "square_root": 0.5, "reciprocal": -1}[kind]
    uz = ux**power
    provenance["transformed_x_unit"] = unit_label(uz)
    try:
        with np.errstate(over="raise", divide="raise", invalid="raise", under="ignore"):
            x = np.array([row.x.value for row in dataset.rows], dtype=np.float64)
            y = np.array([row.y.value for row in dataset.rows], dtype=np.float64)
            x = REGISTRY.Quantity(x, xunit).to(ux).magnitude
            y = REGISTRY.Quantity(y, yunit).to(uy).magnitude
            delta = 0.0 if shift is None else float(REGISTRY.Quantity(shift, xunit).to(ux).magnitude)
            provenance["origin_shift"] = {
                "original": shift,
                "original_unit": str(xunit),
                "canonical": delta,
                "canonical_unit": unit_label(ux),
            }
            q = x - delta
            invalid = (
                (q < 0)
                if kind == "square_root"
                else (q == 0)
                if kind == "reciprocal"
                else np.zeros(len(q), dtype=bool)
            )
            if invalid.any():
                return reject(
                    "TRANSFORM.DOMAIN_INVALID",
                    {"transform": kind, "shift_present": shift is not None, **offending(invalid)},
                )
            if kind == "square":
                z = np.square(q)
            elif kind == "square_root":
                z = np.sqrt(q)
            elif kind == "reciprocal":
                z = np.reciprocal(q)
            else:
                z = q.copy()
            if not np.isfinite(z).all() or not np.isfinite(y).all():
                return reject("TRANSFORM.RESULT_NONFINITE")
    except (FloatingPointError, OverflowError):
        return reject("TRANSFORM.RESULT_NONFINITE")

    n, p = len(z), degree + (not fixed)
    if n < p + 1:
        return reject(
            "MODEL.INSUFFICIENT_POINTS",
            {
                "observed_n": n,
                "required_n": p + 1,
                "model_family": request.model.family,
                "intercept_policy": request.model.intercept_policy,
            },
        )
    distinct = len(np.unique(z))
    if distinct < degree + 1:
        return reject(
            "MODEL.INSUFFICIENT_DISTINCT_X", {"distinct_count": distinct, "required_count": degree + 1}
        )
    if degree == 2:
        with np.errstate(over="ignore", under="ignore"):
            basis_invalid = ~np.isfinite(z * z)
        if basis_invalid.any():
            return reject(
                "MODEL.BASIS_NONFINITE",
                {
                    "model_family": "quadratic",
                    "transform": kind,
                    "offending_term_power": 2,
                    **offending(basis_invalid),
                },
            )
    s = float(np.max(np.abs(z)))
    w = z / s
    orders = list(range(1 if fixed else 0, degree + 1))
    design = np.column_stack([w**order for order in orders])
    yscale = float(np.max(np.abs(y))) or 1.0
    yn = y / yscale
    provenance["fit_scaling"] = {
        "x": s,
        "y": yscale,
        "centering": "none",
        "solver": "scipy.linalg.lstsq:gelsd",
    }
    try:
        with np.errstate(over="raise", divide="raise", invalid="raise", under="ignore"):
            beta, _, rank, singular = linalg.lstsq(
                design, yn, cond=np.finfo(float).eps * max(design.shape), lapack_driver="gelsd"
            )
            if rank < p:
                return reject("MODEL.DESIGN_MATRIX_RANK_DEFICIENT", {"rank": int(rank), "parameter_count": p})
            condition = float(singular[0] / singular[-1])
            if condition > 1e12:
                return reject(
                    "MODEL.CONDITION_NUMBER_EXTREME", {"value": condition, "rejection_threshold": 1e12}
                )
            if condition > 1e8:
                findings.append(
                    finding("MODEL.CONDITION_NUMBER_HIGH", {"value": condition, "warning_threshold": 1e8})
                )
            # Evaluate in the bounded basis, which is algebraically identical but avoids cancellation from unit scales.
            predn = design @ beta
            residualn = yn - predn
            predicted, residual = predn * yscale, residualn * yscale
            sse_n = float(residualn @ residualn)
            sse = float(np.longdouble(sse_n) * np.longdouble(yscale) ** 2)
            rmse = math.sqrt(sse_n / n) * yscale
            mae = float(np.mean(np.abs(residualn))) * yscale
            constant_y = bool(np.all(y == y[0]))
            centered = yn - np.mean(yn)
            tss_n = float(centered @ centered)
            r2 = None if constant_y else 1 - sse_n / tss_n
            _, sv, vt = linalg.svd(design, full_matrices=False)
            covariance_diagonal = np.sum((vt.T / sv) ** 2, axis=1) * (sse_n / (n - p))
            coefficients = []
            for index, order in enumerate(orders):
                conversion = np.longdouble(yscale) / np.longdouble(s) ** order
                extended = np.longdouble(beta[index]) * conversion
                value = float(extended)
                stderr = float(np.sqrt(covariance_diagonal[index]) * conversion)
                if (value == 0 and extended != 0) or not all(math.isfinite(v) for v in [value, stderr]):
                    return reject("MODEL.RESULT_UNREPRESENTABLE")
                unit = uy / uz**order
                coefficients.append(
                    {
                        "key": ["intercept", "linear", "quadratic"][order],
                        "ordinal": order,
                        "value": value,
                        "standard_error": stderr,
                        "unit": unit_label(unit),
                        "dimension": dimensions(unit),
                    }
                )
            metrics = {
                "n": n,
                "parameter_count": p,
                "degrees_of_freedom": n - p,
                "sse": sse,
                "rmse": rmse,
                "mae": mae,
                "r_squared": r2,
                "condition_number": condition,
            }
            if (
                not all(v is None or math.isfinite(v) for v in metrics.values())
                or not np.isfinite(predicted).all()
                or not np.isfinite(residual).all()
            ):
                return reject("MODEL.RESULT_UNREPRESENTABLE")
    except (FloatingPointError, OverflowError, ZeroDivisionError):
        return reject("MODEL.RESULT_UNREPRESENTABLE")
    except linalg.LinAlgError:
        return {
            "status": "failed",
            "failure_code": "NUMERICAL_FIT_FAILED",
            "provenance": provenance,
            "findings": findings,
        }

    if fixed:
        findings.append(
            finding(
                "MODEL.FIXED_ZERO_ASSUMPTION",
                {"model_family": request.model.family, "rationale_present": True},
            )
        )
        if delta != 0:
            findings.append(finding("MODEL.SHIFT_WITH_FIXED_ZERO", provenance["origin_shift"]))
    if request.student_claim:
        claim = request.student_claim
        coefficient = next(c for c in coefficients if c["key"] == claim.coefficient_key)
        claim_unit = parse_unit(claim.unit_input)
        if dimensions(claim_unit) != coefficient["dimension"] or is_offset(claim.unit_input):
            findings.append(
                finding(
                    "UNIT.COEFFICIENT_DIMENSION_MISMATCH",
                    {
                        "coefficient_key": claim.coefficient_key,
                        "claimed_unit": claim.unit_input,
                        "derived_unit": coefficient["unit"],
                        "claimed_dimensions": dimensions(claim_unit),
                        "derived_dimensions": coefficient["dimension"],
                    },
                )
            )
    if constant_y:
        findings.append(finding("METRIC.R_SQUARED_UNDEFINED"))
    findings.append(finding("INTERPRETATION.FIT_NOT_PHYSICAL_PROOF"))
    series = [
        {
            "point_index": i,
            "transformed_x": float(z[i]),
            "transformed_y": float(y[i]),
            "predicted_y": float(predicted[i]),
            "residual": float(residual[i]),
        }
        for i in range(n)
    ]
    summary = f"{n} measurements fitted with a {request.model.family} model; x in {unit_label(uz)}, y in {unit_label(uy)}. Residual = observed minus predicted. RMSE {rmse:.6g} {unit_label(uy)}."
    return {
        "status": "succeeded",
        "provenance": provenance,
        "coefficients": coefficients,
        "metrics": metrics,
        "series": series,
        "findings": findings,
        "chart_summary": summary,
    }
