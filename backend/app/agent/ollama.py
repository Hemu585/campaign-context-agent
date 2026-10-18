"""Loopback-only Ollama access: model probe and the chat call used by the agent loop.

No other provider exists in this codebase. If the local model is missing, slow or returns
malformed data, the run fails visibly; it never falls back to a hosted endpoint or a canned
answer (R17, R18, SECURITY_PRIVACY). Redirects are refused so the loopback check cannot be
escaped, and `think: false` keeps hidden reasoning out of responses where the model allows it.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import httpx

from app.config import CLOUD_TAG_RE, Settings
from app.errors import AppError

KEEP_ALIVE = "30m"  # keep the warm model loaded through a demo


@dataclass(frozen=True)
class ModelStatus:
    reachable: bool
    installed: bool
    tag: str
    digest: str | None
    server_version: str | None
    detail: str


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict | str | None


@dataclass
class ChatResult:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    gen_tokens: int = 0
    elapsed_ms: int = 0
    load_ms: int = 0
    done_reason: str | None = None


def _client(settings: Settings, timeout: httpx.Timeout, transport: httpx.AsyncBaseTransport | None):
    return httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=timeout, follow_redirects=False,
                             trust_env=False, transport=transport)


# 10 s, not 3: right after a cold load on the 5.9 GB test laptop, /api/tags answered in 3.2 s.
async def probe_model(settings: Settings, *, timeout_s: float = 10.0,
                      transport: httpx.AsyncBaseTransport | None = None) -> ModelStatus:
    tag = settings.ollama_model
    try:
        async with _client(settings, httpx.Timeout(timeout_s), transport) as http:
            version_res = await http.get("/api/version")
            tags = await http.get("/api/tags")
            if version_res.is_redirect or tags.is_redirect:
                raise httpx.HTTPError("redirect refused")
            tags.raise_for_status()
            version = version_res.json().get("version")
            models = tags.json().get("models", [])
    except (httpx.HTTPError, ValueError) as exc:
        return ModelStatus(False, False, tag, None, None,
                           f"Ollama is not reachable at the local endpoint ({type(exc).__name__}).")
    for m in models:
        name = m.get("name") or m.get("model")
        if name == tag and not CLOUD_TAG_RE.search(name or ""):
            return ModelStatus(True, True, tag, m.get("digest"), version, "Local model installed.")
    return ModelStatus(True, False, tag, None, version, f"Model {tag} is not installed. Run `ollama pull {tag}`.")


def _parse_tool_calls(message: dict) -> list[ToolCall]:
    calls = []
    for raw in message.get("tool_calls") or []:
        fn = (raw or {}).get("function") or {}
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                pass  # left as a string; the tool validator rejects it
        calls.append(ToolCall(name=str(fn.get("name") or ""), arguments=args))
    return calls


class OllamaChat:
    """The production model client: one non-streaming /api/chat request per agent turn."""

    is_test_double = False

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    async def chat(self, messages: list[dict], *, tools: list[dict] | None = None, fmt: dict | None = None,
                   timeout_s: float, num_predict: int | None = None) -> ChatResult:
        if timeout_s <= 0:
            raise AppError("MODEL_TIMEOUT", "The run's time budget was used up before the model answered.", 504)
        body: dict = {
            "model": self.settings.ollama_model,
            "messages": messages,
            "stream": False,
            "think": False,
            "keep_alive": KEEP_ALIVE,
            "options": {"temperature": 0, "seed": self.settings.ollama_seed, "num_ctx": self.settings.ollama_num_ctx,
                        "num_predict": num_predict or self.settings.ollama_num_predict},
        }
        if tools:
            body["tools"] = tools
        if fmt:
            body["format"] = fmt
        started = time.perf_counter()
        try:
            async with _client(self.settings, httpx.Timeout(timeout_s, connect=3.0), self.transport) as http:
                res = await http.post("/api/chat", json=body)
        except httpx.TimeoutException as exc:
            raise AppError("MODEL_TIMEOUT", "The local model did not answer within the run's time limit.",
                           504) from exc
        except httpx.HTTPError as exc:
            raise AppError("MODEL_UNAVAILABLE", "The local Ollama server is not reachable.", 503,
                           retryable=True) from exc
        if res.is_redirect:
            raise AppError("MODEL_UNAVAILABLE", "The model endpoint tried to redirect; redirects are refused.", 503)
        if res.status_code == 404:
            raise AppError("MODEL_NOT_INSTALLED",
                           f"Model {self.settings.ollama_model} is not installed locally.", 503)
        if res.status_code >= 400:
            raise AppError("MODEL_UNAVAILABLE", f"The local model returned HTTP {res.status_code}.", 503,
                           retryable=True)
        try:
            data = res.json()
            message = data.get("message") or {}
        except (ValueError, AttributeError) as exc:
            raise AppError("INVALID_MODEL_OUTPUT", "The local model returned a malformed response.", 502) from exc
        return ChatResult(
            content=str(message.get("content") or ""),
            tool_calls=_parse_tool_calls(message),
            prompt_tokens=int(data.get("prompt_eval_count") or 0),
            gen_tokens=int(data.get("eval_count") or 0),
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            load_ms=int((data.get("load_duration") or 0) / 1_000_000),
            done_reason=data.get("done_reason"),
        )
