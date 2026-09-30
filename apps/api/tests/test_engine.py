import copy
import json
import math
import random
from uuid import uuid4

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from lablens.contracts import AnalysisRequest, ManualDataset, number
from lablens.csv_import import parse_csv
from lablens.engine import run_analysis, snapshot_hash
from lablens.errors import Problem
from lablens.units import parse_unit
from pydantic import ValidationError


def data(xs=(0, 1, 2, 3), ys=(1, 3, 5, 7), xunit="s", yunit="m"):
    return ManualDataset.model_validate(
        {
            "display_name": "Synthetic fixture",
            "columns": [
                {"role": "independent", "position": 0, "name": "Time", "unit_input": xunit},
                {"role": "dependent", "position": 1, "name": "Distance", "unit_input": yunit},
            ],
            "rows": [
                {"x": {"raw": str(x), "value": x}, "y": {"raw": str(y), "value": y}} for x, y in zip(xs, ys)
            ],
        }
    )


def request(kind="identity", family="linear", fixed=False, shift=None, claim=None):
    return AnalysisRequest.model_validate(
        {
            "dataset_version_id": str(uuid4()),
            "x_transform": {"kind": kind, "input_role": "independent", "time_origin_shift": shift},
            "model": {
                "family": family,
                "intercept_policy": "fixed_zero" if fixed else "free",
                "intercept_rationale": "The physical model assumes zero at the origin." if fixed else None,
            },
            "student_claim": claim,
        }
    )


def rules(result):
    return {f["rule_id"] for f in result["findings"]}


def test_golden_acceleration_dimensional_reasoning():
    xs = [0.8, 1.8, 2.8, 3.8, 4.8]
    result = run_analysis(data(xs, [0.021 * x * x for x in xs], yunit="m/s^2"), request("square", fixed=True))
    assert result["status"] == "succeeded"
    slope = result["coefficients"][0]
    assert slope["value"] == pytest.approx(0.021, rel=1e-12)
    assert slope["dimension"] == {"[length]": 1, "[time]": -4}
    assert result["metrics"]["parameter_count"] == 1
    assert result["metrics"]["degrees_of_freedom"] == 4


@pytest.mark.parametrize(
    "kind,xs",
    [
        ("identity", [-2, -1, 1, 3]),
        ("square", [0.5, 1, 2, 3]),
        ("square_root", [0, 1, 4, 9]),
        ("reciprocal", [1, 2, 3, 4]),
    ],
)
@pytest.mark.parametrize(
    "family,fixed", [("linear", False), ("linear", True), ("quadratic", False), ("quadratic", True)]
)
def test_each_model_and_transform_recovers_known_coefficients(kind, xs, family, fixed):
    transform = {
        "identity": lambda x: x,
        "square": lambda x: x * x,
        "square_root": math.sqrt,
        "reciprocal": lambda x: 1 / x,
    }[kind]
    zs = [transform(x) for x in xs]
    ys = [(0 if fixed else 3) + 2 * z + (0.5 * z * z if family == "quadratic" else 0) for z in zs]
    output = run_analysis(data(xs, ys), request(kind, family, fixed))
    assert output["status"] == "succeeded"
    expected = {"intercept": 3, "linear": 2, "quadratic": 0.5}
    for coefficient in output["coefficients"]:
        assert coefficient["value"] == pytest.approx(expected[coefficient["key"]], rel=1e-12, abs=1e-12)
    assert output["metrics"]["r_squared"] == pytest.approx(1, abs=1e-12)


def test_centimeter_meter_equivalence():
    config = request()
    a = run_analysis(data(xunit="m", yunit="N"), config)
    b = run_analysis(data([0, 100, 200, 300], yunit="N", xunit="cm"), config)
    for x, y in zip(a["coefficients"], b["coefficients"]):
        assert x["value"] == pytest.approx(y["value"], rel=1e-12)
    assert a["series"] == b["series"]


@pytest.mark.parametrize(
    "xs,kind",
    [
        ([0, 1, 2, 3], "reciprocal"),
        ([-0.0, 1, 2, 3], "reciprocal"),
        ([-1, 0, 1, 2], "square_root"),
        ([-1e-20, 0, 1, 2], "square_root"),
    ],
)
def test_invalid_domains_preserve_all_rows(xs, kind):
    dataset = data(xs)
    old = dataset.model_dump()
    output = run_analysis(dataset, request(kind))
    assert output["status"] == "rejected" and "coefficients" not in output
    assert "TRANSFORM.DOMAIN_INVALID" in rules(output)
    assert output["findings"][0]["evidence"]["offending_indices"] == [0]
    assert dataset.model_dump() == old


def test_shift_precedes_transform_and_is_recorded():
    output = run_analysis(data([2, 3, 4, 5], [0, 2, 8, 18]), request("square", fixed=True, shift=2))
    assert output["coefficients"][0]["value"] == pytest.approx(2, rel=1e-12)
    assert "MODEL.SHIFT_WITH_FIXED_ZERO" in rules(output)
    assert output["provenance"]["origin_shift"]["canonical"] == 2


def test_constant_x_rejected_and_constant_y_r2_null():
    assert "MODEL.INSUFFICIENT_DISTINCT_X" in rules(run_analysis(data([1, 1, 1, 1]), request()))
    output = run_analysis(data(ys=[7, 7, 7, 7]), request())
    assert output["status"] == "succeeded" and output["metrics"]["r_squared"] is None
    assert "METRIC.R_SQUARED_UNDEFINED" in rules(output)


def test_r2_is_centered_and_may_be_negative():
    output = run_analysis(data([1, 2, 3, 4], [100, 101, 102, 103]), request(fixed=True))
    actual = np.array([100, 101, 102, 103])
    predictions = np.array([p["predicted_y"] for p in output["series"]])
    assert output["metrics"]["r_squared"] == pytest.approx(
        1 - np.sum((actual - predictions) ** 2) / np.sum((actual - actual.mean()) ** 2)
    )
    assert output["metrics"]["r_squared"] < 0


@pytest.mark.parametrize("claim,mismatch", [("m/s", False), ("cm/s", False), ("m/s^2", True), ("degC", True)])
def test_claim_uses_dimensions_not_spelling(claim, mismatch):
    output = run_analysis(data(), request(claim={"coefficient_key": "linear", "unit_input": claim}))
    assert ("UNIT.COEFFICIENT_DIMENSION_MISMATCH" in rules(output)) == mismatch
    assert output["status"] == "succeeded"


def test_condition_extreme_and_rank_deficient():
    a = run_analysis(data([1, 1 + 1e-13, 1 + 2e-13, 1 + 3e-13]), request())
    b = run_analysis(data([1, 1 + 2.22e-16, 1 + 4.44e-16, 1 + 6.66e-16]), request())
    assert "MODEL.CONDITION_NUMBER_EXTREME" in rules(a)
    assert "MODEL.DESIGN_MATRIX_RANK_DEFICIENT" in rules(b)


def test_condition_warning():
    output = run_analysis(data([1, 1 + 1e-9, 1 + 2e-9, 1 + 3e-9]), request())
    assert output["status"] == "succeeded" and "MODEL.CONDITION_NUMBER_HIGH" in rules(output)


def test_finite_transform_but_overflowing_polynomial_basis():
    output = run_analysis(data([1e90, 2e90, 3e90, 4e90]), request("square", "quadratic"))
    assert "MODEL.BASIS_NONFINITE" in rules(output)
    assert "coefficients" not in output


def test_overflowing_transform_and_integrity_hash():
    assert "TRANSFORM.RESULT_NONFINITE" in rules(
        run_analysis(data([1e100, 2e99, 3e99, 4e99], xunit="h^12*km^12"), request("square"))
    )
    output = run_analysis(data(), request(), "0" * 64)
    assert output["status"] == "failed" and "INPUT.DATASET_INVARIANT_BROKEN" in rules(output)


@pytest.mark.parametrize(
    "kind,family,fixed,shift",
    [
        ("square", "linear", False, None),
        ("identity", "quadratic", False, None),
        ("identity", "linear", True, None),
        ("identity", "linear", False, 1),
    ],
)
def test_offset_temperature_restrictions(kind, family, fixed, shift):
    assert "UNIT.OFFSET_TRANSFORM_UNSAFE" in rules(
        run_analysis(data(xunit="degC"), request(kind, family, fixed, shift))
    )


def test_temperature_identity_and_delta_temperature():
    result = run_analysis(data(xunit="degC"), request())
    assert result["status"] == "succeeded"
    assert result["series"][0]["transformed_x"] == pytest.approx(273.15)
    assert run_analysis(data(xunit="delta_degC"), request("square"))["status"] == "succeeded"
    assert run_analysis(data(yunit="degC"), request(fixed=True))["status"] == "rejected"


@pytest.mark.parametrize(
    "family,fixed,n", [("linear", False, 2), ("quadratic", False, 3), ("quadratic", True, 2)]
)
def test_minimum_observations(family, fixed, n):
    assert "MODEL.INSUFFICIENT_POINTS" in rules(
        run_analysis(data(list(range(n)), list(range(n))), request(family=family, fixed=fixed))
    )


def test_standard_errors_match_independent_formula():
    xs = np.array([0, 1, 2, 3, 4.0])
    ys = np.array([1.1, 2.8, 5.2, 6.7, 9.1])
    output = run_analysis(data(xs.tolist(), ys.tolist()), request())
    X = np.column_stack([np.ones(5), xs])
    beta = np.linalg.inv(X.T @ X) @ X.T @ ys
    se = np.sqrt(np.diag(np.linalg.inv(X.T @ X)) * np.sum((ys - X @ beta) ** 2) / 3)
    assert [c["standard_error"] for c in output["coefficients"]] == pytest.approx(se, rel=1e-12)


def test_repeat_determinism_and_json_roundtrip():
    dataset, config = data(), request()
    first = run_analysis(dataset, config)
    assert first == run_analysis(dataset, config)
    assert first == json.loads(json.dumps(first, allow_nan=False))
    assert snapshot_hash(dataset) == snapshot_hash(copy.deepcopy(dataset))


@given(
    st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.1, max_value=100, allow_nan=False),
)
@settings(max_examples=100, deadline=None)
def test_linear_recovery_property(intercept, slope):
    output = run_analysis(data([0, 1, 2, 3], [intercept + slope * x for x in range(4)]), request())
    assert output["status"] == "succeeded"
    assert output["coefficients"][1]["value"] == pytest.approx(slope, rel=1e-8, abs=1e-9)


@pytest.mark.parametrize(
    "text",
    [
        "NaN",
        "inf",
        "-Infinity",
        "=1+1",
        "@SUM(1)",
        "+cmd",
        "1_000",
        "1,2",
        "1e1001",
        "1e-999",
        "0x10",
        "true",
        "",
        " 1",
        "1\n",
    ],
)
def test_unsafe_numeric_lexemes(text):
    with pytest.raises(Problem):
        number(text)


@pytest.mark.parametrize(
    "text", ["m;import os", "__import__('os')", "foo", "m^99", "degC/s", "", "m^(2)", "m^0.5"]
)
def test_unsafe_units_rejected(text):
    with pytest.raises(Problem):
        parse_unit(text)


def test_numeric_fuzz_10000_and_csv_fuzz_5000():
    rng = random.Random(20260926)
    for _ in range(10000):
        value = rng.uniform(-1e99, 1e99)
        assert number(repr(value)) == value
    definition = data().model_dump(exclude={"rows"})
    from lablens.contracts import DatasetMetadata

    meta = DatasetMetadata.model_validate(definition)
    for i in range(5000):
        raw = f"Time,Distance\n{rng.uniform(-100, 100):.8g},{rng.uniform(-100, 100):.8g}\n+4.0e-2,-3.2\n".encode()
        assert len(parse_csv(raw, meta).rows) == 2


@pytest.mark.parametrize(
    "raw,code",
    [
        (b"Time,Distance\n0,1\n\n2,3", "CSV_SCHEMA_INVALID"),
        (b"Time,Time\n0,1\n2,3", "CSV_SCHEMA_INVALID"),
        (b"Time,Distance\n=1+1,1\n2,3", "NUMERIC_LEXEME_INVALID"),
        (b"Time,Distance\n0,1,4\n2,3,4", "CSV_SCHEMA_INVALID"),
        (b'Time,Distance\n"0,1\n2,3', "CSV_SYNTAX_INVALID"),
        (b"\xff\xfe", "CSV_ENCODING_INVALID"),
        (b"Time,Distance\n0,1\n2,\x00", "CSV_SYNTAX_INVALID"),
    ],
)
def test_csv_invalid(raw, code):
    from lablens.contracts import DatasetMetadata

    with pytest.raises(Problem) as exc:
        parse_csv(raw, DatasetMetadata.model_validate(data().model_dump(exclude={"rows"})))
    assert exc.value.code == code


def test_csv_bom_quoted_negative_trailing_blank_and_swapped_roles():
    from lablens.contracts import DatasetMetadata

    meta = DatasetMetadata.model_validate(data().model_dump(exclude={"rows"}))
    parsed = parse_csv(b'\xef\xbb\xbfTime,Distance\r\n"-1.2",+4.0e-2\r\n2,3\r\n\r\n', meta)
    assert parsed.rows[0].x.value == -1.2 and parsed.rows[0].y.value == 0.04
    swapped = meta.model_copy(deep=True)
    swapped.columns[0].position = 1
    swapped.columns[1].position = 0
    assert parse_csv(b"Distance,Time\n1,2\n3,4", swapped).rows[0].x.value == 2


def test_contract_forbids_unknown_fields_and_boolean_numbers():
    payload = data().model_dump()
    payload["surprise"] = "hidden"
    with pytest.raises(ValidationError):
        ManualDataset.model_validate(payload)
    payload = data().model_dump()
    payload["rows"][0]["x"]["value"] = True
    with pytest.raises(ValidationError):
        ManualDataset.model_validate(payload)
    payload = data().model_dump()
    payload["rows"][0]["x"]["raw"] = "999"
    with pytest.raises(Problem):
        ManualDataset.model_validate(payload)


@pytest.mark.parametrize("expression", ["*".join(["h^12"] * 10), "*".join(["h^-12"] * 9)])
def test_compound_unit_scale_overflow_and_underflow_rejected(expression):
    with pytest.raises(Problem):
        parse_unit(expression)


def test_solver_failure_is_a_failed_snapshot_not_a_plausible_fit(monkeypatch):
    from lablens import engine

    def fail(*args, **kwargs):
        raise np.linalg.LinAlgError("synthetic convergence failure")

    monkeypatch.setattr(engine.linalg, "lstsq", fail)
    result = run_analysis(data(), request())
    assert result["status"] == "failed" and result["failure_code"] == "NUMERICAL_FIT_FAILED"
    assert "coefficients" not in result
