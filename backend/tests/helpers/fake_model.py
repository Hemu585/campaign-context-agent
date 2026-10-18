"""TEST DOUBLE for the local model. Used only by automated loop tests; never by the live demo.

Every instance announces itself, so logs and assertions cannot mistake it for a real run.
"""

from __future__ import annotations

import asyncio
import json
import logging

from app.agent.ollama import ChatResult, ToolCall
from app.errors import AppError

log = logging.getLogger("campaign_context.test_double")


def call(name: str, **args) -> ChatResult:
    return ChatResult(content="", tool_calls=[ToolCall(name, args)])


def calls(*pairs) -> ChatResult:
    return ChatResult(content="", tool_calls=[ToolCall(name, args) for name, args in pairs])


def done() -> ChatResult:
    return ChatResult(content="DONE")


def final(outcome="recommendation", recommended=("cr_02", "cr_04", "cr_09"), reasons=(), clarification="none",
          **extra) -> ChatResult:
    body = {"outcome": outcome, "recommended_creator_ids": list(recommended),
            "highlighted_reasons": [{"creator_id": c, "reason_code": r} for c, r in reasons],
            "clarification_code": clarification, **extra}
    return ChatResult(content=json.dumps(body))


HAPPY_PATH = [
    call("get_campaign_requirements"),
    call("evaluate_candidates"),
    call("get_candidate_evidence", creator_id="cr_02"),
    call("stage_replacement_proposal", creator_id="cr_02"),
    done(),
    final(reasons=[("cr_03", "COMPETITOR_EXCLUSIVITY"), ("cr_02", "budget")]),
]


class ScriptedModel:
    """Returns scripted replies in order. Labelled TEST DOUBLE; it never contacts Ollama."""

    is_test_double = True
    label = "TEST DOUBLE"

    def __init__(self, script, *, delay_s: float = 0.0, block: asyncio.Event | None = None):
        self.script = list(script)
        self.delay_s = delay_s
        self.block = block
        self.calls: list[dict] = []
        log.info("TEST DOUBLE model created with %d scripted replies", len(self.script))

    async def chat(self, messages, *, tools=None, fmt=None, timeout_s: float, num_predict=None) -> ChatResult:
        self.calls.append({"tools": [t["function"]["name"] for t in tools or []], "final": fmt is not None,
                           "last": messages[-1]["content"] if messages else ""})
        if self.block is not None:
            await self.block.wait()
        if self.delay_s:
            if self.delay_s >= timeout_s:
                await asyncio.sleep(timeout_s)
                raise AppError("MODEL_TIMEOUT", "TEST DOUBLE timed out", 504)
            await asyncio.sleep(self.delay_s)
        if not self.script:
            return done()
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
