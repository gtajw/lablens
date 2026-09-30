import hashlib
import json
import os
import time
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from lablens import db as m
from lablens.main import app
from lablens.security import csrf_token, token_hash
from lablens.settings import settings
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError
from test_engine import data, request

pytestmark = pytest.mark.skipif(
    not os.environ.get("LABLENS_TEST_DATABASE"),
    reason="Set LABLENS_TEST_DATABASE=1 against an isolated migrated PostgreSQL test database.",
)


class Browser:
    def __init__(self):
        self.client = TestClient(app)
        self.token = ""
        response = self.send("GET", "/session")
        assert response.status_code == 200, response.text
        self.token = response.headers["x-new-session"]

    def send(self, method, path, payload=None, key=None, csrf=True):
        body = b"" if payload is None else json.dumps(payload, separators=(",", ":")).encode()
        target = "/internal/v1" + path
        csrf_value = csrf_token(self.token) if csrf else ""
        key = key or str(uuid4())
        now = int(time.time())
        claims = {
            "iss": "lablens-web",
            "aud": "lablens-api",
            "iat": now,
            "exp": now + 30,
            "method": method,
            "path": target,
            "body": hashlib.sha256(body).hexdigest(),
            "session": token_hash(self.token),
            "csrf": token_hash(csrf_value),
            "idempotency": token_hash(key),
            "content_type": token_hash("application/json"),
        }
        headers = {
            "x-gateway-assertion": jwt.encode(claims, settings().gateway_secret, algorithm="HS256"),
            "x-session-token": self.token,
            "x-csrf-token": csrf_value,
            "content-type": "application/json",
            "idempotency-key": key,
        }
        return self.client.request(method, target, content=body, headers=headers)

    def create_project(self):
        response = self.send("POST", "/projects", {"title": "Synthetic test experiment"})
        assert response.status_code == 201, response.text
        return response.json()["data"]["id"]

    def create_dataset(self, project):
        response = self.send("POST", f"/projects/{project}/datasets/manual", data().model_dump())
        assert response.status_code == 201, response.text
        return response.json()["data"]["id"]

    def create_analysis(self, project, dataset):
        payload = request().model_dump(mode="json")
        payload["dataset_version_id"] = dataset
        response = self.send("POST", f"/projects/{project}/analyses", payload)
        assert response.status_code == 201, response.text
        return response.json()["data"]


@pytest.fixture(autouse=True)
def clear_rate_buckets():
    with m.sessions().begin() as db:
        db.execute(delete(m.RateBucket))
    yield
    # Isolate test connections, including protocol state after intentionally failed SQL.
    m.engine().dispose()


def test_end_to_end_persistence_idempotency_export_and_delete():
    browser = Browser()
    project = browser.create_project()
    key = str(uuid4())
    path = f"/projects/{project}/datasets/manual"
    payload = data().model_dump()
    first = browser.send("POST", path, payload, key)
    second = browser.send("POST", path, payload, key)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["data"] == second.json()["data"]
    changed = {**payload, "display_name": "Changed"}
    assert browser.send("POST", path, changed, key).status_code == 409
    dataset = first.json()["data"]["id"]
    output = browser.create_analysis(project, dataset)
    identity = output["analysis"]["id"]
    read = browser.send("GET", f"/projects/{project}/analyses/{identity}").json()["data"]
    assert read == output and read["status"] == "succeeded"
    exported = browser.send("POST", f"/projects/{project}/analyses/{identity}/exports", {"format": "json"})
    assert exported.status_code == 201, exported.text
    bundle = exported.json()["data"]
    from lablens.engine import digest

    assert digest(bundle["content"]) == bundle["sha256"]
    assert hashlib.sha256(bundle["content_json"].encode()).hexdigest() == bundle["sha256"]
    assert "owner" not in json.dumps(bundle)
    explanation = browser.send("POST", f"/projects/{project}/analyses/{identity}/explanations", {})
    assert explanation.status_code == 201, explanation.text
    assert explanation.json()["data"]["status"] == "failed"
    assert explanation.json()["data"]["fallback_text"]
    assert browser.send("GET", f"/projects/{project}/analyses/{identity}").json()["data"] == output
    assert browser.send("DELETE", f"/projects/{project}").status_code == 204
    assert browser.send("GET", f"/projects/{project}").status_code == 404
    with m.sessions()() as db:
        assert db.get(m.Dataset, dataset) is None
        assert db.get(m.Analysis, identity) is None
        assert db.scalar(select(m.Idempotency).where(m.Idempotency.project_id == project)) is None


def test_cross_workspace_authorization_matrix():
    owner, other = Browser(), Browser()
    project = owner.create_project()
    dataset = owner.create_dataset(project)
    analysis = owner.create_analysis(project, dataset)["analysis"]["id"]
    p = f"/projects/{project}"
    operations = [
        ("GET", p, None),
        ("DELETE", p, None),
        ("PATCH", p, {"title": "Stolen", "expected_updated_at": "2026-01-01T00:00:00Z"}),
        ("GET", p + "/datasets", None),
        ("GET", p + f"/datasets/{dataset}", None),
        ("POST", p + "/datasets/manual", data().model_dump()),
        ("GET", p + "/analyses", None),
        ("GET", p + f"/analyses/{analysis}", None),
        ("POST", p + f"/analyses/{analysis}/rerun", {}),
        ("POST", p + f"/analyses/{analysis}/exports", {}),
        ("POST", p + f"/analyses/{analysis}/explanations", {}),
    ]
    for method, path, payload in operations:
        response = other.send(method, path, payload)
        assert response.status_code == 404, (method, path, response.text)


def test_csrf_gateway_assertion_and_request_binding():
    browser = Browser()
    assert browser.client.get("/internal/v1/projects").status_code == 401
    assert browser.send("POST", "/projects", {"title": "X"}, csrf=False).status_code == 403
    response = browser.send("POST", "/projects", {"title": "Good"})
    headers = dict(response.request.headers)
    body = response.request.content
    headers["x-session-token"] = "x" * 43
    assert browser.client.post("/internal/v1/projects", content=body, headers=headers).status_code == 401
    for name in ("idempotency-key", "content-type"):
        tampered = dict(response.request.headers)
        tampered[name] = "changed"
        assert browser.client.post("/internal/v1/projects", content=body, headers=tampered).status_code == 401
    headers = dict(response.request.headers)
    assert (
        browser.client.post(
            "/internal/v1/projects", content=b'{"title":"tampered"}', headers=headers
        ).status_code
        == 401
    )


def test_immutable_snapshots_and_ready_integrity():
    browser = Browser()
    project = browser.create_project()
    dataset = browser.create_dataset(project)
    analysis = browser.create_analysis(project, dataset)["analysis"]["id"]
    for sql, identity in [
        ("UPDATE dataset_points SET x_value=42 WHERE dataset_id=:id", dataset),
        ("UPDATE dataset_versions SET display_name='changed' WHERE id=:id", dataset),
        ("UPDATE analyses SET engine_version='fake' WHERE id=:id", analysis),
        ("UPDATE analysis_coefficients SET value=42 WHERE analysis_id=:id", analysis),
        ("DELETE FROM findings WHERE analysis_id=:id", analysis),
    ]:
        with pytest.raises(DBAPIError):
            with m.sessions().begin() as db:
                db.execute(text(sql), {"id": identity})


def test_wrong_project_dataset_and_rerun():
    browser = Browser()
    p1 = browser.create_project()
    p2 = browser.create_project()
    dataset = browser.create_dataset(p1)
    payload = request().model_dump(mode="json")
    payload["dataset_version_id"] = dataset
    assert browser.send("POST", f"/projects/{p2}/analyses", payload).status_code == 404
    original = browser.create_analysis(p1, dataset)
    again = browser.send("POST", f"/projects/{p1}/analyses/{original['analysis']['id']}/rerun", {})
    assert again.status_code == 201, again.text
    assert again.json()["data"]["analysis"]["supersedes_analysis_id"] == original["analysis"]["id"]
    assert again.json()["data"]["coefficients"] == original["coefficients"]


def test_rate_limit_and_session_deletion():
    browser = Browser()
    from lablens.security import rate_limit

    rate_limit("test", "quota", 1, 60)
    from lablens.errors import Problem

    with pytest.raises(Problem) as exc:
        rate_limit("test", "quota", 1, 60)
    assert exc.value.status == 429
    p = browser.create_project()
    browser.create_dataset(p)
    assert browser.send("DELETE", "/session", {}).status_code == 204
    assert browser.send("GET", "/projects").status_code == 401
    with m.sessions()() as db:
        assert db.get(m.Project, p) is None


def test_pagination_cursor_tampering_and_binding():
    browser = Browser()
    browser.create_project()
    browser.create_project()
    result = browser.send("GET", "/projects?limit=1").json()["data"]
    assert len(result["items"]) == 1 and result["next_cursor"]
    next_page = browser.send("GET", "/projects?limit=1&cursor=" + result["next_cursor"])
    assert (
        next_page.status_code == 200
        and next_page.json()["data"]["items"][0]["id"] != result["items"][0]["id"]
    )
    assert browser.send("GET", "/projects?cursor=invalid").status_code == 400
    other = Browser()
    assert other.send("GET", "/projects?cursor=" + result["next_cursor"]).status_code == 400


def test_optimistic_project_edit_and_structural_validation():
    browser = Browser()
    p = browser.create_project()
    current = browser.send("GET", f"/projects/{p}").json()["data"]
    update = {"title": "Renamed", "expected_updated_at": current["updated_at"]}
    assert browser.send("PATCH", f"/projects/{p}", update).status_code == 200
    assert browser.send("PATCH", f"/projects/{p}", update).status_code == 409
    assert browser.send("POST", "/projects", {"title": "Private", "owner_id": "x"}).status_code == 422
    assert browser.send("POST", "/projects", {"title": "Test"}, key="bad").status_code == 400


def test_rejected_analysis_is_saved_without_coefficients():
    browser = Browser()
    project = browser.create_project()
    dataset = browser.create_dataset(project)
    payload = request(kind="reciprocal").model_dump(mode="json")
    payload["dataset_version_id"] = dataset
    result = browser.send("POST", f"/projects/{project}/analyses", payload)
    assert result.status_code == 201
    saved = result.json()["data"]
    assert saved["status"] == "rejected" and "coefficients" not in saved
    assert (
        browser.send("GET", f"/projects/{project}/analyses/{saved['analysis']['id']}").json()["data"] == saved
    )


def test_health_validation_and_idempotency_errors():
    browser = Browser()
    assert browser.client.get("/health/live").json()["status"] == "ok"
    assert browser.client.get("/health/ready").json()["status"] == "ready"
    assert "m" in browser.send("GET", "/units").json()["data"]["atoms"]
    assert browser.send("GET", "/session").headers.get("x-new-session") is None
    response = browser.send("POST", "/projects", {"title": "valid"}, key="short")
    assert response.status_code == 400 and response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    response = browser.send("POST", "/projects", {"title": ""})
    assert response.status_code == 422 and response.json()["error"]["field_errors"]
    assert all(e["value_preview"] is None for e in response.json()["error"]["field_errors"])
    assert browser.send("GET", "/projects?cursor=invalid").status_code == 400
    response = browser.client.post("/internal/v1/projects", content=b"x" * 2097153)
    assert response.status_code == 413


def test_expired_session_cannot_access_and_bootstrap_replaces_it():
    from datetime import timedelta

    browser = Browser()
    with m.sessions().begin() as db:
        stored = db.scalar(select(m.Session).where(m.Session.token_hash == token_hash(browser.token)))
        stored.expires_at = m.now() - timedelta(seconds=1)
    assert browser.send("GET", "/projects").status_code == 401
    assert browser.send("GET", "/session").headers["x-new-session"] != browser.token


def test_expired_idempotency_record_allows_fresh_operation():
    from datetime import timedelta

    browser = Browser()
    key = str(uuid4())
    first = browser.send("POST", "/projects", {"title": "Original"}, key=key)
    with m.sessions().begin() as db:
        record = db.scalar(select(m.Idempotency).where(m.Idempotency.key == key))
        record.expires_at = m.now() - timedelta(seconds=1)
    second = browser.send("POST", "/projects", {"title": "New"}, key=key)
    assert second.status_code == 201 and second.json()["data"]["id"] != first.json()["data"]["id"]


def test_workspace_capacity_and_http_rate_limit_response():
    browser = Browser()
    for _ in range(20):
        browser.create_project()
    assert browser.send("POST", "/projects", {"title": "Over capacity"}).status_code == 409
    from lablens.security import rate_limit

    principal = browser.send("GET", "/session").json()["data"]["principal"]["id"]
    with pytest.raises(Exception):
        rate_limit(principal, "read", 0, 60)
    with m.sessions().begin() as db:
        bucket = db.scalar(
            select(m.RateBucket).where(m.RateBucket.subject == principal, m.RateBucket.scope == "read")
        )
        bucket.count = 120
    response = browser.send("GET", "/projects")
    assert response.status_code == 429 and int(response.headers["retry-after"]) > 0


def test_explanation_cache_export_and_object_binding(monkeypatch):
    from lablens import main

    calls = []

    def fake_explain(findings, payload):
        calls.append(1)
        return {
            "status": "succeeded",
            "text": "Synthetic provider output.",
            "fallback_text": findings[0]["message"],
            "failure_code": None,
        }

    monkeypatch.setattr(main, "explain", fake_explain)
    browser = Browser()
    project = browser.create_project()
    dataset = browser.create_dataset(project)
    analysis = browser.create_analysis(project, dataset)["analysis"]["id"]
    base = f"/projects/{project}/analyses/{analysis}"
    first = browser.send("POST", base + "/explanations", {}).json()["data"]
    second = browser.send("POST", base + "/explanations", {}).json()["data"]
    assert second == first and len(calls) == 1
    assert browser.send("GET", base + "/explanations/" + first["id"]).json()["data"] == first
    assert browser.send("GET", base + "/explanations/" + str(uuid4())).status_code == 404
    bundle = browser.send("POST", base + "/exports", {"include_explanation_id": first["id"]}).json()["data"]
    assert bundle["content"]["explanation"]["text"] == first["text"]
    assert (
        browser.send("POST", base + "/exports", {"include_explanation_id": str(uuid4())}).status_code == 404
    )
    assert (
        browser.send("POST", base + "/explanations", {"focus_rule_ids": ["NONEXISTENT"]}).status_code == 422
    )
    other = browser.create_analysis(project, dataset)["analysis"]["id"]
    assert (
        browser.send("GET", f"/projects/{project}/analyses/{other}/explanations/{first['id']}").status_code
        == 404
    )


def test_dataset_point_pagination_is_lossless():
    browser = Browser()
    project = browser.create_project()
    dataset = browser.create_dataset(project)
    path = f"/projects/{project}/datasets/{dataset}"
    first = browser.send("GET", path + "?limit=2").json()["data"]
    second = browser.send("GET", path + "?limit=2&offset=2").json()["data"]
    assert first["next_offset"] == 2 and second["next_offset"] is None
    assert [row["point_index"] for row in first["rows"] + second["rows"]] == [0, 1, 2, 3]
