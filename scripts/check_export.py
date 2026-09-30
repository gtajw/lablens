"""Check a LabLens JSON export's checksums and reproduce its saved scientific result.

This checks internal consistency, not cryptographic authenticity: an attacker who
controls the entire file can replace both its content and its unkeyed SHA-256.
"""

import json
import math
import sys
from pathlib import Path

from lablens.contracts import AnalysisRequest, ManualDataset
from lablens.engine import digest, run_analysis, snapshot_hash


def check(source: Path):
    bundle = json.loads(source.read_text(encoding="utf-8"))
    content = bundle["content"]
    assert bundle["sha256"] == digest(content), "Export checksum mismatch"
    dataset = ManualDataset.model_validate(content["dataset"])
    assert content["dataset_sha256"] == snapshot_hash(dataset), "Dataset checksum mismatch"
    request = AnalysisRequest.model_validate(content["analysis_request"])
    saved = content["result"]
    calculated = run_analysis(dataset, request, expected_hash=content["dataset_sha256"])
    assert calculated["status"] == saved["status"], "Result status mismatch"
    assert calculated["provenance"]["scientific_sha256"] == saved["provenance"]["scientific_sha256"], (
        "Scientific request differs"
    )
    assert calculated["findings"] == saved["findings"], "Findings mismatch"
    assert calculated.get("failure_code") == saved["analysis"]["failure_code"], "Failure code mismatch"
    if calculated["status"] == "succeeded":
        for left, right in zip(calculated["coefficients"], saved["coefficients"], strict=True):
            assert left["key"] == right["key"] and left["dimension"] == right["dimension"]
            for key in ("value", "standard_error"):
                assert math.isclose(left[key], right[key], rel_tol=1e-9, abs_tol=1e-14), key
        for key, value in calculated["metrics"].items():
            other = saved["metrics"][key]
            assert value == other or (
                value is not None
                and other is not None
                and math.isclose(value, other, rel_tol=1e-9, abs_tol=1e-14)
            ), key
        for left, right in zip(calculated["series"], saved["series"], strict=True):
            assert left["point_index"] == right["point_index"]
            for key in ("transformed_x", "transformed_y", "predicted_y", "residual"):
                assert math.isclose(left[key], right[key], rel_tol=1e-9, abs_tol=1e-14), key
    print(f"Verified export, {len(dataset.rows)} rows, status {saved['status']}.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/check_export.py path/to/export.json")
    check(Path(sys.argv[1]))
