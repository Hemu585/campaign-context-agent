"""Section 0 preflight: does the local model really call tools, and how fast?

Sends real requests to the local Ollama server (loopback only) and prints a JSON
summary that is copied into the verification notes. This is a measurement script,
not application code: the app's own model check is `python -m app.cli verify-model`.

Usage (with the project venv, which has the app installed):
    .venv/Scripts/python.exe scripts/preflight_model_smoke.py --model qwen3:4b-instruct-2507-q4_K_M --num-ctx 8192

The model tag and base URL go through the app's own local-only rules before any request.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request

from app.config import Settings

BASE = "http://127.0.0.1:11434"

TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather_fixture",
        "description": "Return the fixed fictional weather fixture for a city.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}

FINAL_SCHEMA = {
    "type": "object",
    "properties": {"city": {"type": "string"}, "summary": {"type": "string"}},
    "required": ["city", "summary"],
    "additionalProperties": False,
}


def post(path: str, body: dict, timeout: float = 300) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - loopback constant
        return json.loads(resp.read())


def get(path: str, timeout: float = 10) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=timeout) as resp:  # noqa: S310 - loopback constant
        return json.loads(resp.read())


def chat(model: str, messages: list, num_ctx: int, tools=None, fmt=None) -> dict:
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "seed": 42, "num_ctx": num_ctx, "num_predict": 256},
    }
    if tools:
        body["tools"] = tools
    if fmt:
        body["format"] = fmt
    started = time.perf_counter()
    result = post("/api/chat", body)
    result["_wall_s"] = time.perf_counter() - started
    return result


def stats(result: dict) -> dict:
    ns = 1e9
    gen, gen_ns = result.get("eval_count", 0), result.get("eval_duration", 0) or 1
    prompt, prompt_ns = result.get("prompt_eval_count", 0), result.get("prompt_eval_duration", 0) or 1
    return {
        "wall_s": round(result["_wall_s"], 2),
        "load_s": round(result.get("load_duration", 0) / ns, 2),
        "prompt_tokens": prompt,
        "prompt_tok_per_s": round(prompt / (prompt_ns / ns), 1),
        "gen_tokens": gen,
        "gen_tok_per_s": round(gen / (gen_ns / ns), 1),
    }


def checked_model(model: str) -> str:
    """Refuse what the app itself refuses (cloud-tagged models, non-loopback endpoints) before any
    request reaches Ollama, which could otherwise forward a cloud tag to remote inference."""
    try:
        Settings(_env_file=None, ollama_base_url=BASE, ollama_model=model)
    except ValueError as exc:  # pydantic's ValidationError is a ValueError
        raise SystemExit(f"refused: {exc}") from None
    return model


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3:4b-instruct-2507-q4_K_M")
    parser.add_argument("--num-ctx", type=int, default=8192)
    args = parser.parse_args(argv)
    args.model = checked_model(args.model)

    # Unload first so the first call measures a cold load.
    post("/api/generate", {"model": args.model, "keep_alive": 0})
    time.sleep(2)

    messages = [
        {"role": "system", "content": "You are a test harness. Use the provided tool when asked."},
        {"role": "user", "content": "Use the tool to get the weather fixture for Pune."},
    ]
    report: dict = {"model": args.model, "num_ctx": args.num_ctx}

    cold = chat(args.model, messages, args.num_ctx, tools=[TOOL])
    calls = cold["message"].get("tool_calls") or []
    report["cold_tool_turn"] = stats(cold)
    report["tool_called"] = bool(calls) and calls[0]["function"]["name"] == "get_weather_fixture"
    report["tool_args"] = calls[0]["function"].get("arguments") if calls else None
    report["thinking_emitted"] = bool(cold["message"].get("thinking")) or "<think>" in (cold["message"].get("content") or "")

    loaded = [m for m in get("/api/ps").get("models", []) if m.get("name", "").startswith(args.model)]
    if loaded:
        size, vram = loaded[0].get("size", 0), loaded[0].get("size_vram", 0)
        report["loaded_size_gb"] = round(size / 1e9, 2)
        report["vram_gb"] = round(vram / 1e9, 2)
        report["gpu_share_pct"] = round(100 * vram / size, 1) if size else None
        report["context_length_loaded"] = loaded[0].get("context_length")

    if calls:
        messages.append(cold["message"])
        messages.append({
            "role": "tool",
            "tool_name": "get_weather_fixture",
            "content": json.dumps({"city": "Pune", "fixture": "22 C, clear (fictional test fixture)"}),
        })
        final = chat(args.model, messages, args.num_ctx, tools=[TOOL])
        report["tool_result_turn"] = stats(final)
        report["final_text_present"] = bool((final["message"].get("content") or "").strip())

    structured = chat(
        args.model,
        [{"role": "user", "content": "Return the city Pune and a one-line summary of a 22 C clear day."}],
        args.num_ctx,
        fmt=FINAL_SCHEMA,
    )
    try:
        parsed = json.loads(structured["message"]["content"])
        report["structured_output_valid"] = set(parsed) == {"city", "summary"}
    except (json.JSONDecodeError, KeyError, TypeError):
        report["structured_output_valid"] = False
    report["structured_turn"] = stats(structured)

    warm = chat(args.model, messages[:2], args.num_ctx, tools=[TOOL])
    report["warm_tool_turn"] = stats(warm)
    report["warm_tool_called"] = bool(warm["message"].get("tool_calls"))

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
