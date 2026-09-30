import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, Form, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DBSession

from . import db as m
from . import repository as repo
from .contracts import (
    AnalysisRequest,
    DatasetMetadata,
    ExplanationRequest,
    ExportRequest,
    ManualDataset,
    ProjectCreate,
    ProjectPatch,
)
from .csv_import import parse_csv
from .engine import ENGINE_VERSION, digest
from .errors import Problem, missing
from .explanations import PROMPT_VERSION, explain
from .security import authenticate, csrf_token, rate_limit, token_hash, verify_gateway
from .settings import settings
from .units import ATOMS

log = logging.getLogger("lablens")
app = FastAPI(title="LabLens internal API", version="1.0.0", docs_url=None, redoc_url=None)


def error_response(request, problem):
    headers = {"Cache-Control": "no-store"}
    if problem.status in {429, 503}:
        headers["Retry-After"] = str(problem.details.get("retry_after", 5))
    return JSONResponse(
        {
            "request_id": getattr(request.state, "request_id", str(uuid4())),
            "error": {
                "code": problem.code,
                "message": problem.message,
                "retryable": problem.status in {429, 503},
                "field_errors": [],
                "details": problem.details,
            },
        },
        status_code=problem.status,
        headers=headers,
    )


@app.exception_handler(Problem)
async def problem_handler(request, exc):
    return error_response(request, exc)


@app.exception_handler(RequestValidationError)
async def validation_handler(request, exc):
    problem = Problem("CONFIGURATION_INVALID", "Check the highlighted fields and try again.")
    response = error_response(request, problem)
    payload = json.loads(response.body)
    payload["error"]["field_errors"] = [
        {
            "path": "/" + "/".join(str(v) for v in e["loc"]),
            "code": e["type"],
            "message": e["msg"],
            "value_preview": None,
        }
        for e in exc.errors()[:20]
    ]
    return JSONResponse(payload, status_code=422, headers={"Cache-Control": "no-store"})


@app.exception_handler(SQLAlchemyError)
async def database_handler(request, exc):
    log.error("database_unavailable request_id=%s type=%s", request.state.request_id, type(exc).__name__)
    return error_response(
        request, Problem("DATABASE_UNAVAILABLE", "Storage is temporarily unavailable. Please retry.", 503)
    )


@app.middleware("http")
async def boundary(request, call_next):
    request.state.request_id = str(uuid4())
    start = time.perf_counter()
    try:
        if request.url.path not in {"/health/live", "/health/ready"}:
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 2_097_152:
                    raise Problem("PAYLOAD_TOO_LARGE", "The request is larger than the supported limit.", 413)
                chunks.append(chunk)
            body = b"".join(chunks)
            request._body = body
            verify_gateway(request, body)
            if request.method in {"POST", "PATCH"}:
                media = request.headers.get("content-type", "").split(";")[0]
                if media not in {"application/json", "multipart/form-data"}:
                    raise Problem("MEDIA_TYPE_UNSUPPORTED", "Use JSON or the CSV upload form.", 415)
        response = await call_next(request)
    except Problem as exc:
        response = error_response(request, exc)
    except Exception as exc:
        log.error("unhandled request_id=%s type=%s", request.state.request_id, type(exc).__name__)
        response = error_response(
            request, Problem("INTERNAL_ERROR", "Something went wrong. Your saved work is unchanged.", 500)
        )
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    log.info(
        "request method=%s status=%s duration_ms=%.1f request_id=%s",
        request.method,
        response.status_code,
        (time.perf_counter() - start) * 1000,
        request.state.request_id,
    )
    return response


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    try:
        with m.engine().connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            if version != "0001":
                raise Problem("SCHEMA_NOT_READY", "A database migration is required.", 503)
    except SQLAlchemyError:
        raise Problem("DATABASE_UNAVAILABLE", "Storage is temporarily unavailable.", 503) from None
    return {"status": "ready", "engine_version": ENGINE_VERSION}


@dataclass
class Context:
    db: DBSession
    principal: m.Principal
    request: Request


def context(request: Request):
    with m.sessions()() as db:
        principal = authenticate(db, request)
        db.commit()
        path = request.url.path
        if request.method == "GET":
            rate_limit(principal.id, "read", 120, 60)
        else:
            scope, count, period = ("mutation", 30, 60)
            if path.endswith(("/manual", "/csv")):
                scope, count, period = "dataset", 10, 3600
            elif path.endswith(("/analyses", "/rerun")):
                scope, count, period = "analysis", 30, 3600
            elif path.endswith("/explanations"):
                scope, count, period = "explanation", 5, 3600
            rate_limit(principal.id, scope, count, period)
        with db.begin():
            db.execute(text("SET LOCAL statement_timeout = '15000ms'"))
            db.execute(text("SET LOCAL lock_timeout = '3000ms'"))
            if request.method != "GET":
                # All commands of one workspace serialize, including duplicates and deletion.
                locked = db.scalar(
                    select(m.Principal).where(m.Principal.id == principal.id).with_for_update()
                )
                if locked is None:
                    raise Problem("SESSION_EXPIRED", "Reload to open a new workspace.", 401)
            yield Context(db, principal, request)


Ctx = Annotated[Context, Depends(context, scope="function")]


def envelope(ctx, data, status=200):
    return JSONResponse({"request_id": ctx.request.state.request_id, "data": data}, status_code=status)


def mutation(ctx, payload, operation, project_id=None):
    key = ctx.request.headers.get("idempotency-key", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", key):
        raise Problem("IDEMPOTENCY_KEY_REQUIRED", "Use a 16–80 character idempotency key.", 400)
    scope = ctx.request.url.path
    request_hash = digest(payload)
    old = ctx.db.get(m.Idempotency, (ctx.principal.id, scope, key))
    if old and old.expires_at > m.now():
        if old.request_sha256 != request_hash:
            raise Problem(
                "IDEMPOTENCY_KEY_REUSED", "This retry key was already used for different input.", 409
            )
        return envelope(ctx, old.response, 200)
    if old:
        ctx.db.delete(old)
        ctx.db.flush()
    result = operation()
    saved_project = project_id or (result.get("id") if scope.endswith("/projects") else None)
    ctx.db.add(
        m.Idempotency(
            principal_id=ctx.principal.id,
            scope=scope,
            key=key,
            request_sha256=request_hash,
            response=result,
            project_id=saved_project,
            expires_at=m.now() + timedelta(hours=24),
        )
    )
    ctx.db.add(
        m.AuditEvent(
            request_id=ctx.request.state.request_id, action=scope.rsplit("/", 1)[-1], outcome="created"
        )
    )
    ctx.db.flush()
    return envelope(ctx, result, 201)


def page(ctx, query, model, scope, serializer, cursor, limit):
    # Stable keyset cursor, integrity-protected and bound to workspace + resource scope.
    timestamp_column = model.updated_at if model is m.Project else model.created_at
    if cursor:
        try:
            encoded, signature = cursor.split(".")
            expected = hmac.new(
                settings().gateway_secret.encode(), encoded.encode(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError()
            data = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            if data["owner"] != ctx.principal.id or data["scope"] != scope:
                raise ValueError()
            from datetime import datetime

            timestamp = datetime.fromisoformat(data["at"])
            identity = str(UUID(data["id"]))
            query = query.where(
                (timestamp_column < timestamp) | ((timestamp_column == timestamp) & (model.id < identity))
            )
        except (ValueError, KeyError, TypeError):
            raise Problem("CURSOR_INVALID", "Restart this list to refresh its page cursor.", 400) from None
    rows = ctx.db.scalars(query.order_by(timestamp_column.desc(), model.id.desc()).limit(limit + 1)).all()
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        payload = {
            "owner": ctx.principal.id,
            "scope": scope,
            "at": getattr(last, timestamp_column.key).isoformat(),
            "id": last.id,
        }
        encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        signature = hmac.new(settings().gateway_secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        next_cursor = encoded + "." + signature
    return envelope(ctx, {"items": [serializer(r) for r in rows[:limit]], "next_cursor": next_cursor})


PREFIX = "/internal/v1"


@app.get(PREFIX + "/session")
def session(request: Request):
    new_token = None
    rate_limit("bootstrap", "session", 120, 60)
    with m.sessions().begin() as db:
        try:
            principal = authenticate(db, request)
        except Problem as exc:
            if exc.status != 401:
                raise
            new_token = secrets.token_urlsafe(32)
            principal = m.Principal(expires_at=m.now() + timedelta(days=settings().session_days))
            db.add(principal)
            db.flush()
            db.add(
                m.Session(
                    principal_id=principal.id,
                    token_hash=token_hash(new_token),
                    expires_at=principal.expires_at,
                )
            )
        data = {
            "principal": {
                "id": principal.id,
                "kind": principal.kind,
                "role": principal.role,
                "expires_at": principal.expires_at.isoformat(),
            },
            "retention_days": settings().session_days,
            "csrf": {
                "header_name": "X-CSRF-Token",
                "token": csrf_token(new_token or request.headers["x-session-token"]),
            },
            "capabilities": {
                "sharing": False,
                "accounts": False,
                "ai": bool(settings().ai_api_key and settings().ai_model),
            },
        }
    response = JSONResponse({"request_id": request.state.request_id, "data": data})
    if new_token:
        response.headers["X-New-Session"] = new_token
    return response


@app.delete(PREFIX + "/session", status_code=204)
def end_session(ctx: Ctx):
    ctx.db.execute(
        m.Project.__table__.update().where(m.Project.owner_id == ctx.principal.id).values(status="deleting")
    )
    ctx.db.delete(ctx.principal)
    return Response(status_code=204, headers={"X-Clear-Session": "1"})


@app.get(PREFIX + "/units")
def units(ctx: Ctx):
    return envelope(ctx, {"atoms": sorted(ATOMS), "maximum_exponent": 12})


@app.post(PREFIX + "/projects", status_code=201)
def create_project(payload: ProjectCreate, ctx: Ctx):
    def operation():
        count = ctx.db.scalar(select(func.count(m.Project.id)).where(m.Project.owner_id == ctx.principal.id))
        if count >= 20:
            raise Problem(
                "WORKSPACE_CAPACITY",
                "Keep up to 20 projects. Export and delete an older one to make room.",
                409,
            )
        project = m.Project(owner_id=ctx.principal.id, **payload.model_dump())
        ctx.db.add(project)
        ctx.db.flush()
        return repo.project_summary(ctx.db, project)

    return mutation(ctx, payload.model_dump(), operation)


@app.get(PREFIX + "/projects")
def list_projects(
    ctx: Ctx, cursor: str | None = Query(None, max_length=1000), limit: int = Query(20, ge=1, le=50)
):
    return page(
        ctx,
        select(m.Project).where(m.Project.owner_id == ctx.principal.id, m.Project.status == "active"),
        m.Project,
        "projects",
        lambda p: repo.project_summary(ctx.db, p),
        cursor,
        limit,
    )


@app.get(PREFIX + "/projects/{project_id}")
def project_detail(project_id: UUID, ctx: Ctx):
    return envelope(
        ctx, repo.project_summary(ctx.db, repo.get_project(ctx.db, ctx.principal.id, str(project_id)))
    )


@app.patch(PREFIX + "/projects/{project_id}")
def edit_project(project_id: UUID, payload: ProjectPatch, ctx: Ctx):
    project = repo.get_project(ctx.db, ctx.principal.id, str(project_id))
    if project.updated_at != payload.expected_updated_at:
        raise Problem("PROJECT_VERSION_CONFLICT", "The project changed. Reload it before saving.", 409)
    for field, value in payload.model_dump(exclude={"expected_updated_at"}).items():
        setattr(project, field, value)
    project.updated_at = m.now()
    return envelope(ctx, repo.project_summary(ctx.db, project))


@app.delete(PREFIX + "/projects/{project_id}", status_code=204)
def delete_project(project_id: UUID, ctx: Ctx):
    project = repo.get_project(ctx.db, ctx.principal.id, str(project_id))
    project.status = "deleting"
    ctx.db.flush()
    ctx.db.delete(project)
    return Response(status_code=204)


@app.post(PREFIX + "/projects/{project_id}/datasets/manual", status_code=201)
def manual_dataset(project_id: UUID, payload: ManualDataset, ctx: Ctx):
    project = repo.get_project(ctx.db, ctx.principal.id, str(project_id))
    return mutation(
        ctx, payload.model_dump(), lambda: repo.save_dataset(ctx.db, project, payload, "manual"), project.id
    )


@app.post(PREFIX + "/projects/{project_id}/datasets/csv", status_code=201)
def csv_dataset(
    project_id: UUID, ctx: Ctx, metadata: Annotated[str, Form(max_length=4096)], file: UploadFile = File()
):
    project = repo.get_project(ctx.db, ctx.principal.id, str(project_id))
    try:
        definition = DatasetMetadata.model_validate_json(metadata)
    except ValidationError:
        raise Problem(
            "CSV_SCHEMA_INVALID", "Check the variable names and units in the upload form."
        ) from None
    raw = file.file.read(1048577)
    payload = parse_csv(raw, definition)
    return mutation(
        ctx,
        {"metadata": definition.model_dump(), "sha256": hashlib.sha256(raw).hexdigest()},
        lambda: repo.save_dataset(ctx.db, project, payload, "csv"),
        project.id,
    )


@app.get(PREFIX + "/projects/{project_id}/datasets")
def list_datasets(
    project_id: UUID,
    ctx: Ctx,
    cursor: str | None = Query(None, max_length=1000),
    limit: int = Query(20, ge=1, le=50),
):
    project = repo.get_project(ctx.db, ctx.principal.id, str(project_id))
    return page(
        ctx,
        select(m.Dataset).where(m.Dataset.project_id == project.id),
        m.Dataset,
        "datasets:" + project.id,
        lambda d: repo.dataset_summary(ctx.db, d),
        cursor,
        limit,
    )


@app.get(PREFIX + "/projects/{project_id}/datasets/{dataset_id}")
def dataset_detail(
    project_id: UUID,
    dataset_id: UUID,
    ctx: Ctx,
    offset: int = Query(0, ge=0, le=4999),
    limit: int = Query(1000, ge=1, le=1000),
):
    repo.get_project(ctx.db, ctx.principal.id, str(project_id))
    dataset = repo.get_dataset(ctx.db, str(project_id), str(dataset_id))
    return envelope(
        ctx,
        {
            **repo.dataset_summary(ctx.db, dataset),
            "rows": repo.points(ctx.db, dataset.id, offset, limit),
            "offset": offset,
            "next_offset": offset + limit if offset + limit < dataset.row_count else None,
        },
    )


@app.post(PREFIX + "/projects/{project_id}/analyses", status_code=201)
def create_analysis(project_id: UUID, payload: AnalysisRequest, ctx: Ctx):
    project = repo.get_project(ctx.db, ctx.principal.id, str(project_id))
    return mutation(
        ctx, payload.model_dump(mode="json"), lambda: repo.save_analysis(ctx.db, project, payload), project.id
    )


@app.get(PREFIX + "/projects/{project_id}/analyses")
def list_analyses(
    project_id: UUID,
    ctx: Ctx,
    cursor: str | None = Query(None, max_length=1000),
    limit: int = Query(20, ge=1, le=50),
):
    project = repo.get_project(ctx.db, ctx.principal.id, str(project_id))
    return page(
        ctx,
        select(m.Analysis).where(m.Analysis.project_id == project.id),
        m.Analysis,
        "analyses:" + project.id,
        repo.analysis_summary,
        cursor,
        limit,
    )


@app.get(PREFIX + "/projects/{project_id}/analyses/{analysis_id}")
def get_analysis(project_id: UUID, analysis_id: UUID, ctx: Ctx):
    repo.get_project(ctx.db, ctx.principal.id, str(project_id))
    return envelope(
        ctx, repo.analysis_detail(ctx.db, repo.get_analysis(ctx.db, str(project_id), str(analysis_id)))
    )


@app.post(PREFIX + "/projects/{project_id}/analyses/{analysis_id}/rerun", status_code=201)
def rerun(project_id: UUID, analysis_id: UUID, ctx: Ctx):
    project = repo.get_project(ctx.db, ctx.principal.id, str(project_id))
    previous = repo.get_analysis(ctx.db, project.id, str(analysis_id))
    payload = AnalysisRequest.model_validate(previous.configuration)
    return mutation(
        ctx,
        {"analysis_id": previous.id},
        lambda: repo.save_analysis(ctx.db, project, payload, previous.id),
        project.id,
    )


@app.post(PREFIX + "/projects/{project_id}/analyses/{analysis_id}/explanations", status_code=201)
def explanation(project_id: UUID, analysis_id: UUID, payload: ExplanationRequest, ctx: Ctx):
    project = repo.get_project(ctx.db, ctx.principal.id, str(project_id))
    analysis = repo.get_analysis(ctx.db, project.id, str(analysis_id))
    result = repo.analysis_detail(ctx.db, analysis)
    if analysis.status not in {"succeeded", "rejected"}:
        raise Problem(
            "ANALYSIS_NOT_READY", "Only completed or rejected analyses have explainable findings.", 409
        )
    if payload.focus_rule_ids and not set(payload.focus_rule_ids) <= {
        f["rule_id"] for f in result["findings"]
    }:
        raise Problem("CONFIGURATION_INVALID", "Select findings from this analysis.")
    cache_key = digest(
        {"analysis": analysis.id, "configuration": payload.model_dump(), "prompt": PROMPT_VERSION}
    )

    def operation():
        existing = ctx.db.scalar(
            select(m.Explanation)
            .where(m.Explanation.cache_key == cache_key)
            .order_by(m.Explanation.created_at.desc())
        )
        if existing and existing.payload["status"] == "succeeded":
            return {"id": existing.id, **existing.payload}
        data = explain(result["findings"], payload)
        saved = m.Explanation(
            analysis_id=analysis.id, configuration=payload.model_dump(), cache_key=cache_key, payload=data
        )
        ctx.db.add(saved)
        ctx.db.flush()
        return {"id": saved.id, **data}

    return mutation(ctx, payload.model_dump(), operation, project.id)


@app.get(PREFIX + "/projects/{project_id}/analyses/{analysis_id}/explanations/{explanation_id}")
def get_explanation(project_id: UUID, analysis_id: UUID, explanation_id: UUID, ctx: Ctx):
    repo.get_project(ctx.db, ctx.principal.id, str(project_id))
    repo.get_analysis(ctx.db, str(project_id), str(analysis_id))
    record = ctx.db.get(m.Explanation, str(explanation_id))
    if not record or record.analysis_id != str(analysis_id):
        missing()
    return envelope(ctx, {"id": record.id, **record.payload})


@app.post(PREFIX + "/projects/{project_id}/analyses/{analysis_id}/exports", status_code=201)
def export(project_id: UUID, analysis_id: UUID, payload: ExportRequest, ctx: Ctx):
    project = repo.get_project(ctx.db, ctx.principal.id, str(project_id))
    analysis = repo.get_analysis(ctx.db, project.id, str(analysis_id))

    def operation():
        dataset = repo.get_dataset(ctx.db, project.id, analysis.dataset_id)
        snapshot = repo.load_snapshot(ctx.db, dataset)
        content = {
            "contract_version": "1.0.0",
            "project": {
                "title": project.title,
                "course_label": project.course_label,
                "unit_label": project.unit_label,
            },
            "dataset": snapshot.model_dump(mode="json"),
            "dataset_sha256": dataset.content_sha256,
            "analysis_request": analysis.configuration,
            "result": repo.analysis_detail(ctx.db, analysis),
        }
        if payload.include_explanation_id:
            saved = ctx.db.get(m.Explanation, str(payload.include_explanation_id))
            if not saved or saved.analysis_id != analysis.id:
                missing()
            content["explanation"] = saved.payload
        return {
            "content": content,
            "content_json": json.dumps(content, sort_keys=True, separators=(",", ":"), allow_nan=False),
            "sha256": digest(content),
            "filename": f"lablens-{analysis.id}.json",
        }

    return mutation(ctx, payload.model_dump(mode="json"), operation, project.id)
