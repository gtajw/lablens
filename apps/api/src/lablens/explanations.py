"""Optional prose. Sends only application-authored rule text, never student data."""

import time

import httpx

from .settings import settings

PROMPT_VERSION = "1.0.0"


def explain(findings: list[dict], request) -> dict:
    selected = [
        f for f in findings if request.focus_rule_ids is None or f["rule_id"] in request.focus_rule_ids
    ]
    fallback = "\n\n".join(f["message"] for f in selected)
    config = settings()
    result = {
        "status": "failed",
        "text": None,
        "fallback_text": fallback,
        "failure_code": "AI_PROVIDER_UNAVAILABLE",
        "prompt_version": PROMPT_VERSION,
        "provider": "featherless-compatible",
        "model": config.ai_model or None,
        "referenced_rule_ids": [f["rule_id"] for f in selected],
        "configuration": request.model_dump(),
    }
    if not config.ai_api_key or not config.ai_model:
        result["failure_code"] = "AI_NOT_CONFIGURED"
        return result
    # The user cannot supply prompt text, URLs, raw data, titles, or the intercept rationale.
    messages = [
        {
            "role": "system",
            "content": "Explain these lab-analysis findings to a high school student. Use only the supplied rule statements. Do not invent numerical values, a physical law, grades, or a lab conclusion. Do not write the student's assignment. Plain text, no links. Keep under 250 words.",
        },
        {"role": "user", "content": f"Detail level: {request.reading_level}.\n" + fallback},
    ]
    started = time.monotonic()
    try:
        with httpx.Client(timeout=httpx.Timeout(8, connect=3), follow_redirects=False) as client:
            with client.stream(
                "POST",
                config.ai_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {config.ai_api_key}"},
                json={"model": config.ai_model, "messages": messages, "max_tokens": 450, "temperature": 0.2},
            ) as response:
                response.raise_for_status()
                content = b""
                for chunk in response.iter_bytes():
                    content += chunk
                    if len(content) > 32768 or time.monotonic() - started > 8:
                        return result
                import json

                data = json.loads(content)
        text = data["choices"][0]["message"]["content"]
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 4000:
            return result
        result.update(status="succeeded", text=text.strip(), failure_code=None)
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        pass
    return result
