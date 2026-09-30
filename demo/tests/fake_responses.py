"""A scripted stand-in for the Responses API, for agent tests labeled as replays.

It mimics only the fields the agent reads: output items (function_call and
message), output_text, usage, and incomplete_details. It records every request.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any


class Item(SimpleNamespace):
    def model_dump(self, exclude_none: bool = True) -> dict[str, Any]:
        return {k: v for k, v in vars(self).items() if not (exclude_none and v is None)}


def usage(input_tokens: int = 1000, output_tokens: int = 100, cached: int = 0, reasoning: int = 20) -> SimpleNamespace:
    return SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens,
                           input_tokens_details=SimpleNamespace(cached_tokens=cached),
                           output_tokens_details=SimpleNamespace(reasoning_tokens=reasoning))


def tool_calls(*calls: tuple[str, dict[str, Any]], model: str = "gpt-6-astra") -> SimpleNamespace:
    items = [Item(type="function_call", id=f"fc_{i}", call_id=f"call_{i}", name=name, arguments=json.dumps(args))
             for i, (name, args) in enumerate(calls)]
    return SimpleNamespace(id="resp_tools", model=model, output=[Item(type="reasoning", id="rs_1"), *items],
                           output_text="", usage=usage(), incomplete_details=None)


def answer(narrative: str, evidence: list[str] | None = None, in_scope: bool = True,
           model: str = "gpt-6-astra") -> SimpleNamespace:
    text = json.dumps({"narrative": narrative, "key_evidence_ids": evidence or [], "in_scope": in_scope})
    message = Item(type="message", role="assistant", content=[Item(type="output_text", text=text)])
    return SimpleNamespace(id="resp_answer", model=model, output=[message], output_text=text,
                           usage=usage(800, 150), incomplete_details=None)


class FakeResponses:
    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.requests: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


class FakeClient:
    def __init__(self, script: list[Any]) -> None:
        self.responses = FakeResponses(script)


class ContentFilterError(Exception):
    code = "content_filter"
