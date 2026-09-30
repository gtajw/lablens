import hashlib
import hmac
import re
import time
from datetime import timedelta

import jwt
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from .db import Principal, RateBucket, Session, now, sessions
from .errors import Problem
from .settings import settings


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token(token: str) -> str:
    return hmac.new(settings().gateway_secret.encode(), f"csrf:{token}".encode(), hashlib.sha256).hexdigest()


def verify_gateway(request: Request, body: bytes):
    try:
        claims = jwt.decode(
            request.headers.get("x-gateway-assertion", ""),
            settings().gateway_secret,
            algorithms=["HS256"],
            issuer="lablens-web",
            audience="lablens-api",
            options={
                "require": [
                    "exp",
                    "iat",
                    "iss",
                    "aud",
                    "method",
                    "path",
                    "body",
                    "session",
                    "csrf",
                    "idempotency",
                    "content_type",
                ]
            },
        )
        if not 0 < claims["exp"] - claims["iat"] <= 60:
            raise ValueError("TTL")
        expected = {
            "method": request.method,
            "path": request.url.path + (f"?{request.url.query}" if request.url.query else ""),
            "body": hashlib.sha256(body).hexdigest(),
            "session": token_hash(request.headers.get("x-session-token", "")),
            "csrf": token_hash(request.headers.get("x-csrf-token", "")),
            "idempotency": token_hash(request.headers.get("idempotency-key", "")),
            "content_type": token_hash(request.headers.get("content-type", "")),
        }
        if any(not hmac.compare_digest(str(claims[k]), v) for k, v in expected.items()):
            raise ValueError("Binding")
    except (jwt.PyJWTError, ValueError, TypeError):
        raise Problem(
            "GATEWAY_REQUIRED", "Use the LabLens web application to access this service.", 401
        ) from None


def rate_limit(subject: str, scope: str, limit: int, seconds: int):
    """Atomic and committed independently, including when the attempted operation fails."""
    window = int(time.time()) // seconds * seconds
    with sessions().begin() as db:
        statement = insert(RateBucket).values(
            subject=subject,
            scope=scope,
            window_start=window,
            count=1,
            expires_at=now() + timedelta(seconds=seconds * 2),
        )
        statement = statement.on_conflict_do_update(
            index_elements=[RateBucket.subject, RateBucket.scope, RateBucket.window_start],
            set_={"count": RateBucket.count + 1},
        ).returning(RateBucket.count)
        count = db.execute(statement).scalar_one()
    if count > limit:
        raise Problem(
            "RATE_LIMITED",
            "This workspace has reached its request limit. Please try again later.",
            429,
            {"retry_after": window + seconds - int(time.time())},
        )


def authenticate(db, request: Request) -> Principal:
    token = request.headers.get("x-session-token", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise Problem("AUTH_REQUIRED", "Your workspace session is missing. Reload the page.", 401)
    session = db.scalar(
        select(Session).where(Session.token_hash == token_hash(token), Session.expires_at > now())
    )
    if session is None:
        raise Problem(
            "SESSION_EXPIRED",
            "This workspace session has expired. Export work before clearing your browser cookies.",
            401,
        )
    principal = db.get(Principal, session.principal_id)
    if principal is None or principal.expires_at <= now():
        raise Problem("SESSION_EXPIRED", "This workspace session has expired.", 401)
    if request.method not in {"GET", "HEAD"}:
        if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), csrf_token(token)):
            raise Problem("CSRF_INVALID", "Reload the page before trying that action again.", 403)
    return principal
