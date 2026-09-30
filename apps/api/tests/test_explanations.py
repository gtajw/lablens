"""Provider boundary tests: privacy, failures and oversized/untrusted output."""

import json
from types import SimpleNamespace

import httpx
import pytest
from lablens import explanations
from lablens.contracts import ExplanationRequest

FINDINGS = [
    {
        "rule_id": "UNIT.CLAIM",
        "message": "The slope unit does not match the claim.",
        "evidence": {"raw": "PRIVATE_MEASUREMENT"},
    },
    {"rule_id": "MODEL.ZERO", "message": "A zero intercept is an assumption."},
]


def provider(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(
        explanations,
        "settings",
        lambda: SimpleNamespace(
            ai_api_key="test-only", ai_model="test-model", ai_base_url="https://provider.example/v1"
        ),
    )
    monkeypatch.setattr(
        explanations.httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )


def test_provider_success_sends_only_selected_application_rule_text(monkeypatch):
    def handle(request):
        payload = json.loads(request.content)
        assert "PRIVATE_MEASUREMENT" not in request.content.decode()
        assert "zero intercept" not in request.content.decode()
        assert request.url == "https://provider.example/v1/chat/completions"
        assert payload["model"] == "test-model"
        return httpx.Response(200, json={"choices": [{"message": {"content": " Check the units. "}}]})

    provider(monkeypatch, handle)
    result = explanations.explain(FINDINGS, ExplanationRequest(focus_rule_ids=["UNIT.CLAIM"]))
    assert result["status"] == "succeeded" and result["text"] == "Check the units."
    assert result["referenced_rule_ids"] == ["UNIT.CLAIM"]


@pytest.mark.parametrize(
    "body",
    [
        b"invalid",
        b"{}",
        b'{"choices":[]}',
        b'{"choices":[{"message":{"content":null}}]}',
        b'{"choices":[{"message":{"content":" "}}]}',
        json.dumps({"choices": [{"message": {"content": "a" * 4001}}]}).encode(),
        b"a" * 32769,
    ],
)
def test_invalid_output_preserves_deterministic_fallback(monkeypatch, body):
    provider(monkeypatch, lambda request: httpx.Response(200, content=body))
    result = explanations.explain(FINDINGS, ExplanationRequest())
    assert result["status"] == "failed" and result["text"] is None
    assert "slope unit" in result["fallback_text"]


@pytest.mark.parametrize("status", [401, 429, 500, 302])
def test_provider_http_failures_do_not_change_result(monkeypatch, status):
    provider(
        monkeypatch, lambda request: httpx.Response(status, headers={"location": "https://other.example"})
    )
    assert explanations.explain(FINDINGS, ExplanationRequest())["status"] == "failed"


def test_provider_timeout_falls_back(monkeypatch):
    def handle(request):
        raise httpx.ReadTimeout("test timeout", request=request)

    provider(monkeypatch, handle)
    assert explanations.explain(FINDINGS, ExplanationRequest())["status"] == "failed"


def test_slow_response_is_bounded(monkeypatch):
    provider(
        monkeypatch, lambda request: httpx.Response(200, json={"choices": [{"message": {"content": "late"}}]})
    )
    ticks = iter([0, 9])
    monkeypatch.setattr(explanations.time, "monotonic", lambda: next(ticks))
    assert explanations.explain(FINDINGS, ExplanationRequest())["status"] == "failed"
