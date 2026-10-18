"""Ollama adapter behaviour with a mocked HTTP transport (no real model): R17, R18, T17 part."""

import json

import httpx
import pytest

from app.agent.ollama import OllamaChat, probe_model
from app.config import Settings
from app.errors import AppError

SETTINGS = Settings(_env_file=None)


def transport(handler):
    return httpx.MockTransport(handler)


def ok_chat(message, **extra):
    return httpx.Response(200, json={"message": message, "prompt_eval_count": 10, "eval_count": 5,
                                     "load_duration": 2_000_000, "done_reason": "stop", **extra})


async def test_request_is_deterministic_local_and_non_thinking():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return ok_chat({"role": "assistant", "content": "DONE"})

    result = await OllamaChat(SETTINGS, transport(handler)).chat([{"role": "user", "content": "hi"}], timeout_s=5)
    body = seen["body"]
    assert seen["url"] == "http://127.0.0.1:11434/api/chat"
    assert body["think"] is False and body["stream"] is False
    assert body["options"]["temperature"] == 0 and body["options"]["seed"] == 42
    assert body["model"] == "qwen3:4b-instruct-2507-q4_K_M"
    assert result.content == "DONE" and result.gen_tokens == 5 and result.load_ms == 2


async def test_tool_calls_are_parsed_from_dicts_and_json_strings():
    def handler(_request):
        return ok_chat({"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "get_candidate_evidence", "arguments": {"creator_id": "cr_02"}}},
            {"function": {"name": "evaluate_candidates", "arguments": "{}"}},
            {"function": {"name": "get_candidate_evidence", "arguments": "{not json"}},
        ]})

    result = await OllamaChat(SETTINGS, transport(handler)).chat([], tools=[{"type": "function"}], timeout_s=5)
    assert [(c.name, c.arguments) for c in result.tool_calls] == [
        ("get_candidate_evidence", {"creator_id": "cr_02"}), ("evaluate_candidates", {}),
        ("get_candidate_evidence", "{not json")]


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(307, headers={"location": "https://cloud.example/api/chat"}), "MODEL_UNAVAILABLE"),
        (httpx.Response(404, json={"error": "model not found"}), "MODEL_NOT_INSTALLED"),
        (httpx.Response(500, text="boom"), "MODEL_UNAVAILABLE"),
        (httpx.Response(200, text="not json"), "INVALID_MODEL_OUTPUT"),
    ],
)
async def test_failures_are_specific_and_never_fall_back(response, code):
    with pytest.raises(AppError) as info:
        await OllamaChat(SETTINGS, transport(lambda _r: response)).chat([], timeout_s=5)
    assert info.value.code == code


async def test_timeout_maps_to_model_timeout():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(AppError) as info:
        await OllamaChat(SETTINGS, transport(handler)).chat([], timeout_s=5)
    assert info.value.code == "MODEL_TIMEOUT"


async def test_exhausted_budget_fails_before_calling():
    calls = []
    with pytest.raises(AppError) as info:
        await OllamaChat(SETTINGS, transport(lambda r: calls.append(r))).chat([], timeout_s=0)
    assert info.value.code == "MODEL_TIMEOUT" and calls == []


async def test_probe_ignores_cloud_models_and_reports_missing_model():
    def handler(request):
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.40.5"})
        return httpx.Response(200, json={"models": [{"name": "gpt-oss:120b-cloud", "digest": "x"}]})

    status = await probe_model(SETTINGS, transport=transport(handler))
    assert status.reachable is True and status.installed is False


async def test_probe_finds_the_local_model_digest():
    def handler(request):
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.40.5"})
        return httpx.Response(200, json={"models": [{"name": SETTINGS.ollama_model, "digest": "0edcdef34593"}]})

    status = await probe_model(SETTINGS, transport=transport(handler))
    assert status.installed is True and status.digest == "0edcdef34593"
