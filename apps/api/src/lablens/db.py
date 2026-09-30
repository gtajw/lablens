from datetime import datetime, timezone
from functools import lru_cache
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .settings import settings


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Principal(Base):
    __tablename__ = "principals"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(16), default="anonymous")
    role: Mapped[str] = mapped_column(String(16), default="student")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    __table_args__ = (CheckConstraint("kind = 'anonymous'"), CheckConstraint("role = 'student'"))


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uid)
    principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("principals.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(120))
    course_label: Mapped[str | None] = mapped_column(String(80))
    unit_label: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        CheckConstraint("status IN ('active','deleting')"),
        Index("ix_project_owner_sort", "owner_id", "updated_at", "id"),
    )


class Dataset(Base):
    __tablename__ = "dataset_versions"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="validating")
    display_name: Mapped[str] = mapped_column(String(120))
    row_count: Mapped[int] = mapped_column(Integer)
    content_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        UniqueConstraint("project_id", "version_number"),
        UniqueConstraint("project_id", "id"),
        CheckConstraint("row_count BETWEEN 2 AND 5000"),
        CheckConstraint("version_number > 0"),
        CheckConstraint("source IN ('manual','csv','seed')"),
        CheckConstraint("status IN ('validating','ready')"),
    )


class DatasetColumn(Base):
    __tablename__ = "dataset_columns"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uid)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(64))
    symbol: Mapped[str | None] = mapped_column(String(32))
    unit_input: Mapped[str] = mapped_column(String(64))
    unit_canonical: Mapped[str] = mapped_column(String(160))
    dimension_signature: Mapped[dict] = mapped_column(JSONB)
    is_offset: Mapped[bool] = mapped_column(Boolean)
    __table_args__ = (
        UniqueConstraint("dataset_id", "role"),
        UniqueConstraint("dataset_id", "position"),
        CheckConstraint("role IN ('independent','dependent')"),
        CheckConstraint("position IN (0,1)"),
    )


class DatasetPoint(Base):
    __tablename__ = "dataset_points"
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE"), primary_key=True
    )
    point_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    x_raw: Mapped[str] = mapped_column(String(64))
    y_raw: Mapped[str] = mapped_column(String(64))
    x_value: Mapped[float] = mapped_column(Float)
    y_value: Mapped[float] = mapped_column(Float)
    __table_args__ = (
        CheckConstraint("point_index BETWEEN 0 AND 4999"),
        CheckConstraint("x_value BETWEEN -1e100 AND 1e100 AND y_value BETWEEN -1e100 AND 1e100"),
    )


class RuleSet(Base):
    __tablename__ = "rule_sets"
    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    checksum: Mapped[str] = mapped_column(String(64), unique=True)
    engine_min_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RuleDefinition(Base):
    __tablename__ = "rule_definitions"
    rule_set_version: Mapped[str] = mapped_column(ForeignKey("rule_sets.version"), primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    definition: Mapped[dict] = mapped_column(JSONB)


class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    dataset_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    status: Mapped[str] = mapped_column(String(16))
    configuration: Mapped[dict] = mapped_column(JSONB)
    provenance: Mapped[dict] = mapped_column(JSONB)
    engine_version: Mapped[str] = mapped_column(String(32))
    rule_set_version: Mapped[str] = mapped_column(ForeignKey("rule_sets.version"))
    supersedes_analysis_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    sealed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "dataset_id"],
            ["dataset_versions.project_id", "dataset_versions.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("status IN ('succeeded','rejected','failed')"),
        Index("ix_analysis_project_sort", "project_id", "created_at", "id"),
    )


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), primary_key=True)
    metrics: Mapped[dict] = mapped_column(JSONB)
    chart_summary: Mapped[str] = mapped_column(Text)


class Coefficient(Base):
    __tablename__ = "analysis_coefficients"
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), primary_key=True)
    key: Mapped[str] = mapped_column(String(16), primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    value: Mapped[float] = mapped_column(Float)
    standard_error: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(160))
    dimension: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("analysis_id", "ordinal"),
        CheckConstraint("ordinal BETWEEN 0 AND 2"),
        CheckConstraint("value > '-Infinity'::float8 AND value < 'Infinity'::float8"),
        CheckConstraint("standard_error >= 0 AND standard_error < 'Infinity'::float8"),
    )


class AnalysisPoint(Base):
    __tablename__ = "analysis_point_results"
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), primary_key=True)
    point_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    transformed_x: Mapped[float] = mapped_column(Float)
    transformed_y: Mapped[float] = mapped_column(Float)
    predicted_y: Mapped[float] = mapped_column(Float)
    residual: Mapped[float] = mapped_column(Float)
    __table_args__ = tuple(
        CheckConstraint(f"{col} > '-Infinity'::float8 AND {col} < 'Infinity'::float8")
        for col in ["transformed_x", "transformed_y", "predicted_y", "residual"]
    )


class Finding(Base):
    __tablename__ = "findings"
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    display_order: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSONB)


class Explanation(Base):
    __tablename__ = "explanations"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uid)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    configuration: Mapped[dict] = mapped_column(JSONB)
    cache_key: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Idempotency(Base):
    __tablename__ = "idempotency_records"
    principal_id: Mapped[str] = mapped_column(
        ForeignKey("principals.id", ondelete="CASCADE"), primary_key=True
    )
    scope: Mapped[str] = mapped_column(String(240), primary_key=True)
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    request_sha256: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSONB)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(32))
    outcome: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (Index("ix_audit_created_brin", "created_at", postgresql_using="brin"),)


class RateBucket(Base):
    __tablename__ = "rate_buckets"
    subject: Mapped[str] = mapped_column(String(80), primary_key=True)
    scope: Mapped[str] = mapped_column(String(32), primary_key=True)
    window_start: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    count: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


@lru_cache
def engine():
    config = settings()
    return create_engine(
        config.database_url,
        pool_pre_ping=True,
        pool_size=config.pool_size,
        max_overflow=0,
        pool_timeout=5,
        hide_parameters=True,
        connect_args={"connect_timeout": 5, "prepare_threshold": None},
    )


@lru_cache
def sessions():
    return sessionmaker(engine(), expire_on_commit=False)
