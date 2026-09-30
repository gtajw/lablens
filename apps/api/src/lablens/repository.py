"""Persistence operations; all writes participate in the caller's transaction."""

from sqlalchemy import func, insert, select

from . import db as models
from .contracts import Cell, Column, ManualDataset, Row
from .engine import ENGINE_VERSION, RULESET_VERSION, run_analysis, snapshot_hash
from .errors import Problem, missing
from .units import column_units


def get_project(db, principal_id: str, project_id: str):
    project = db.scalar(
        select(models.Project).where(
            models.Project.id == project_id,
            models.Project.owner_id == principal_id,
            models.Project.status == "active",
        )
    )
    if project is None:
        missing()
    return project


def project_summary(db, project):
    version = db.scalar(
        select(func.max(models.Dataset.version_number)).where(models.Dataset.project_id == project.id)
    )
    return {
        "id": project.id,
        "title": project.title,
        "course_label": project.course_label,
        "unit_label": project.unit_label,
        "permission": "owner",
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
        "latest_dataset_version": version,
    }


def dataset_summary(db, dataset):
    columns = db.scalars(
        select(models.DatasetColumn)
        .where(models.DatasetColumn.dataset_id == dataset.id)
        .order_by(models.DatasetColumn.position)
    ).all()
    return {
        "id": dataset.id,
        "project_id": dataset.project_id,
        "version_number": dataset.version_number,
        "display_name": dataset.display_name,
        "status": dataset.status,
        "source": dataset.source,
        "row_count": dataset.row_count,
        "content_sha256": dataset.content_sha256,
        "created_at": dataset.created_at.isoformat(),
        "columns": [
            {
                k: getattr(c, k)
                for k in [
                    "role",
                    "position",
                    "name",
                    "symbol",
                    "unit_input",
                    "unit_canonical",
                    "dimension_signature",
                    "is_offset",
                ]
            }
            for c in columns
        ],
    }


def get_dataset(db, project_id, dataset_id):
    dataset = db.scalar(
        select(models.Dataset).where(
            models.Dataset.id == dataset_id,
            models.Dataset.project_id == project_id,
            models.Dataset.status == "ready",
        )
    )
    if dataset is None:
        missing()
    return dataset


def points(db, dataset_id, offset=0, limit=5000):
    records = db.scalars(
        select(models.DatasetPoint)
        .where(models.DatasetPoint.dataset_id == dataset_id)
        .order_by(models.DatasetPoint.point_index)
        .offset(offset)
        .limit(limit)
    ).all()
    return [
        {
            "point_index": r.point_index,
            "x": {"raw": r.x_raw, "value": r.x_value},
            "y": {"raw": r.y_raw, "value": r.y_value},
        }
        for r in records
    ]


def load_snapshot(db, dataset):
    summary = dataset_summary(db, dataset)
    rows = points(db, dataset.id)
    if len(rows) != dataset.row_count or [r["point_index"] for r in rows] != list(range(dataset.row_count)):
        raise Problem(
            "DATASET_INTEGRITY_ERROR", "The saved dataset could not be verified. Import a fresh copy.", 500
        )
    columns = [
        Column(**{k: c[k] for k in ["role", "position", "name", "symbol", "unit_input"]})
        for c in summary["columns"]
    ]
    return ManualDataset(
        display_name=dataset.display_name,
        columns=columns,
        rows=[Row(x=Cell(**r["x"]), y=Cell(**r["y"])) for r in rows],
    )


def save_dataset(db, project, payload: ManualDataset, source: str):
    count, total = db.execute(
        select(func.count(models.Dataset.id), func.coalesce(func.sum(models.Dataset.row_count), 0)).where(
            models.Dataset.project_id == project.id
        )
    ).one()
    if count >= 100 or total + len(payload.rows) > 50000:
        raise Problem(
            "WORKSPACE_CAPACITY",
            "This project has reached its storage limit. Export it and start a new project.",
            409,
        )
    version = (
        db.scalar(
            select(func.max(models.Dataset.version_number)).where(models.Dataset.project_id == project.id)
        )
        or 0
    ) + 1
    dataset = models.Dataset(
        project_id=project.id,
        version_number=version,
        source=source,
        display_name=payload.display_name,
        row_count=len(payload.rows),
        content_sha256=snapshot_hash(payload),
    )
    db.add(dataset)
    db.flush()
    db.add_all(
        [
            models.DatasetColumn(dataset_id=dataset.id, **c.model_dump(), **column_units(c.unit_input))
            for c in payload.columns
        ]
    )
    db.execute(
        insert(models.DatasetPoint),
        [
            {
                "dataset_id": dataset.id,
                "point_index": i,
                "x_raw": row.x.raw,
                "x_value": row.x.value,
                "y_raw": row.y.raw,
                "y_value": row.y.value,
            }
            for i, row in enumerate(payload.rows)
        ],
    )
    db.flush()
    dataset.status = "ready"
    project.updated_at = models.now()
    db.flush()
    return {**dataset_summary(db, dataset), "preview_rows": points(db, dataset.id, limit=10)}


def analysis_summary(analysis):
    return {
        "id": analysis.id,
        "dataset_version_id": analysis.dataset_id,
        "status": analysis.status,
        "engine_version": analysis.engine_version,
        "rule_set_version": analysis.rule_set_version,
        "created_at": analysis.created_at.isoformat(),
        "completed_at": analysis.completed_at.isoformat(),
        "supersedes_analysis_id": analysis.supersedes_analysis_id,
        "configuration": analysis.configuration,
        "failure_code": analysis.failure_code,
    }


def get_analysis(db, project_id, analysis_id):
    analysis = db.scalar(
        select(models.Analysis).where(
            models.Analysis.project_id == project_id, models.Analysis.id == analysis_id
        )
    )
    if analysis is None:
        missing()
    return analysis


def analysis_detail(db, analysis):
    findings = db.scalars(
        select(models.Finding)
        .where(models.Finding.analysis_id == analysis.id)
        .order_by(models.Finding.display_order)
    ).all()
    detail = {
        "analysis": analysis_summary(analysis),
        "status": analysis.status,
        "provenance": analysis.provenance,
        "findings": [f.payload for f in findings],
    }
    if analysis.status == "succeeded":
        result = db.get(models.AnalysisResult, analysis.id)
        coefficients = db.scalars(
            select(models.Coefficient)
            .where(models.Coefficient.analysis_id == analysis.id)
            .order_by(models.Coefficient.ordinal)
        ).all()
        series = db.scalars(
            select(models.AnalysisPoint)
            .where(models.AnalysisPoint.analysis_id == analysis.id)
            .order_by(models.AnalysisPoint.point_index)
        ).all()
        detail.update(
            {
                "metrics": result.metrics,
                "chart_summary": result.chart_summary,
                "coefficients": [
                    {
                        k: getattr(c, k)
                        for k in ["key", "ordinal", "value", "standard_error", "unit", "dimension"]
                    }
                    for c in coefficients
                ],
                "series": [
                    {
                        k: getattr(p, k)
                        for k in ["point_index", "transformed_x", "transformed_y", "predicted_y", "residual"]
                    }
                    for p in series
                ],
            }
        )
    return detail


def save_analysis(db, project, request, supersedes=None):
    dataset = get_dataset(db, project.id, str(request.dataset_version_id))
    count = db.scalar(select(func.count(models.Analysis.id)).where(models.Analysis.project_id == project.id))
    if count >= 200:
        raise Problem(
            "WORKSPACE_CAPACITY",
            "This project has reached its analysis limit. Export it and create a new project.",
            409,
        )
    snapshot = load_snapshot(db, dataset)
    result = run_analysis(snapshot, request, dataset.content_sha256)
    analysis = models.Analysis(
        project_id=project.id,
        dataset_id=dataset.id,
        status=result["status"],
        configuration=request.model_dump(mode="json"),
        provenance=result["provenance"],
        engine_version=ENGINE_VERSION,
        rule_set_version=RULESET_VERSION,
        supersedes_analysis_id=supersedes,
        failure_code=result.get("failure_code"),
    )
    db.add(analysis)
    db.flush()
    db.add_all(
        [
            models.Finding(analysis_id=analysis.id, rule_id=f["rule_id"], display_order=i, payload=f)
            for i, f in enumerate(result["findings"])
        ]
    )
    if result["status"] == "succeeded":
        db.add(
            models.AnalysisResult(
                analysis_id=analysis.id, metrics=result["metrics"], chart_summary=result["chart_summary"]
            )
        )
        db.add_all([models.Coefficient(analysis_id=analysis.id, **c) for c in result["coefficients"]])
        db.execute(
            insert(models.AnalysisPoint), [{"analysis_id": analysis.id, **p} for p in result["series"]]
        )
    project.updated_at = models.now()
    db.flush()
    analysis.sealed = True
    db.flush()
    db.refresh(analysis)
    return analysis_detail(db, analysis)
