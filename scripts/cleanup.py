"""Run hourly with the API environment. Erase expired workspace data and short-lived metadata."""

from datetime import timedelta

from lablens.db import AuditEvent, Explanation, Idempotency, Principal, Project, RateBucket, now, sessions
from sqlalchemy import delete, select, update

with sessions().begin() as db:
    expired = select(Principal.id).where(Principal.expires_at < now())
    db.execute(update(Project).where(Project.owner_id.in_(expired)).values(status="deleting"))
    principals = db.execute(delete(Principal).where(Principal.expires_at < now())).rowcount
    db.execute(delete(Idempotency).where(Idempotency.expires_at < now()))
    db.execute(delete(RateBucket).where(RateBucket.expires_at < now()))
    db.execute(delete(AuditEvent).where(AuditEvent.created_at < now() - timedelta(days=90)))
    db.execute(
        delete(Explanation).where(
            Explanation.created_at < now() - timedelta(days=7),
            Explanation.payload["status"].astext == "failed",
        )
    )
print(f"Retention complete: {principals} expired workspaces removed.")
