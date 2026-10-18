"""Bounded agent loop (AGENT_WORKFLOW "Execution sequence", "Limits and recovery").

1. Tool phase: the local model chooses allowlisted tools; each call is validated and executed,
   and its real structured result goes back with the tool name.
2. If the model stops before reading requirements and evaluating, it gets a structured
   validation message and ONLY the missing tools (no successful call is ever faked for it).
3. Final step: one schema-constrained JSON call (no tools), validated against the evaluation.
   One repair attempt is allowed; a missing draft sends the model back to the evidence and
   staging tools. Otherwise the run fails with INVALID_MODEL_OUTPUT.

Hard caps: model turns, tool invocations and wall-clock time. Cancelling the asyncio task
aborts the in-flight HTTP request and stops all further tools. Model message content from
tool turns is never stored or shown (no reasoning in the graph or UI).
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.agent.final import FINAL_SCHEMA, parse_final, render_final, validate_final
from app.agent.prompts import FINAL_INSTRUCTION, SYSTEM_PROMPT, user_turn
from app.agent.tools import PHASES, TOOL_SCHEMAS, AgentServices, RunContext, execute_tool
from app.errors import AppError

Emit = Callable[[dict], Awaitable[None]]


@dataclass(frozen=True)
class AgentLimits:
    max_turns: int = 8
    max_tool_calls: int = 12
    timeout_s: float = 180.0
    max_repairs: int = 1
    final_num_predict: int = 400


def _tools(names: list[str]) -> list[dict]:
    return [t for t in TOOL_SCHEMAS if t["function"]["name"] in names]


def _safe_args(args) -> dict:
    """Bounded copy of tool arguments for the operational trace."""
    if not isinstance(args, dict):
        return {"_unparsed": str(args)[:80]}
    out = {}
    for key, value in list(args.items())[:4]:
        if isinstance(value, (bool, int, float)) or value is None:
            out[str(key)[:40]] = value
        else:
            out[str(key)[:40]] = str(value)[:80]
    return out


async def run_agent(*, model, ctx: RunContext, services: AgentServices, message: str, history: list[dict],
                    campaign_title: str, limits: AgentLimits, emit: Emit | None = None,
                    clock: Callable[[], float] = time.monotonic) -> dict:
    deadline = clock() + limits.timeout_s
    turns = 0

    async def note(event: dict) -> None:
        if emit is not None:
            await emit(event)

    async def call_model(messages: list[dict], *, tools=None, fmt=None, purpose: str):
        nonlocal turns
        if turns >= limits.max_turns:
            raise AppError("TOOL_LIMIT_REACHED", f"The agent used all {limits.max_turns} model turns without "
                           "finishing.", 409, details={"turns": turns})
        remaining = deadline - clock()
        if remaining <= 0:
            raise AppError("MODEL_TIMEOUT", f"The run exceeded its {int(limits.timeout_s)} s limit.", 504)
        turns += 1
        started = clock()
        result = await model.chat(messages, tools=tools, fmt=fmt, timeout_s=remaining,
                                  num_predict=limits.final_num_predict if fmt else None)
        await note({"type": "model", "purpose": purpose, "turn": turns,
                    "elapsed_ms": int((clock() - started) * 1000), "gen_tokens": result.gen_tokens,
                    "tool_calls": [c.name for c in result.tool_calls],
                    "offered_tools": [t["function"]["name"] for t in tools or []]})
        return result

    async def tool_phase(messages: list[dict], offered: list[dict]) -> None:
        tools = offered
        while True:
            result = await call_model(messages, tools=tools, purpose="tools")
            if not result.tool_calls:
                return  # the model is done; its free text is not kept
            messages.append({"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": c.name, "arguments": c.arguments if isinstance(c.arguments, dict) else {}}}
                for c in result.tool_calls]})
            for call in result.tool_calls:
                if ctx.tool_calls >= limits.max_tool_calls:
                    raise AppError("TOOL_LIMIT_REACHED", f"The agent reached the {limits.max_tool_calls} tool-call "
                                   "limit.", 409, details={"tool_calls": ctx.tool_calls})
                ctx.tool_calls += 1
                started = clock()
                outcome = await execute_tool(call.name, call.arguments, ctx, services)
                await note({"type": "tool", "tool": call.name, "args": _safe_args(call.arguments),
                            "status": "ok" if outcome.ok else "error", "error_code": outcome.error_code,
                            "elapsed_ms": int((clock() - started) * 1000), "record_ids": outcome.record_ids[:20],
                            "query_ids": outcome.query_ids, "phase": PHASES.get(call.name)})
                messages.append({"role": "tool", "tool_name": call.name,
                                 "content": json.dumps(outcome.content, ensure_ascii=False)})
                if outcome.fatal is not None:
                    raise outcome.fatal
            tools = TOOL_SCHEMAS

    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history,
                {"role": "user", "content": user_turn(ctx.campaign_id, campaign_title, message)}]
    await tool_phase(messages, TOOL_SCHEMAS)

    missing = [name for name, done in (("get_campaign_requirements", ctx.requirements_read),
                                       ("evaluate_candidates", ctx.evaluation is not None)) if not done]
    if missing:
        await note({"type": "validation", "problems": ["PREREQUISITES_MISSING"], "offered_tools": missing})
        messages.append({"role": "user", "content": "VALIDATION: before finishing you must call "
                                                    + " and ".join(missing) + ". Then reply DONE."})
        await tool_phase(messages, _tools(missing))

    repairs = 0
    while True:
        result = await call_model(messages + [{"role": "user", "content": FINAL_INSTRUCTION}], fmt=FINAL_SCHEMA,
                                  purpose="final")
        final, problems = parse_final(result.content)
        if final is not None:
            problems = validate_final(final, ctx.evaluation, ctx.staged)
        await note({"type": "validation", "phase": "writing_summary", "problems": problems})
        if not problems:
            return render_final(final, ctx.evaluation, ctx.staged, campaign_id=ctx.campaign_id, title=campaign_title)
        if repairs >= limits.max_repairs:
            raise AppError("INVALID_MODEL_OUTPUT", "The model's final answer did not match the verified evaluation, "
                           "even after one repair.", 502, details={"problems": problems})
        repairs += 1
        if ("STAGE_REQUIRED" in problems or "EVALUATION_REQUIRED" in problems) and ctx.evaluation is not None:
            top = ctx.evaluation.recommended_creator_ids[0]
            messages.append({"role": "user", "content": (
                f"VALIDATION: {'; '.join(problems)}. Call get_candidate_evidence for {top}, then "
                f"stage_replacement_proposal for {top}, then reply DONE.")})
            await tool_phase(messages, _tools(["get_candidate_evidence", "stage_replacement_proposal"]))
        elif "EVALUATION_REQUIRED" in problems:
            messages.append({"role": "user", "content": "VALIDATION: call get_campaign_requirements and "
                                                        "evaluate_candidates, then reply DONE."})
            await tool_phase(messages, _tools(["get_campaign_requirements", "evaluate_candidates"]))
        else:
            server = ctx.evaluation.recommended_creator_ids if ctx.evaluation else []
            messages.append({"role": "assistant", "content": result.content})
            messages.append({"role": "user", "content": (
                f"VALIDATION ERRORS: {'; '.join(problems)}. The server ranking is {server}. Use only reason codes "
                "or check names that the tools returned for that creator. Return corrected JSON.")})
