"""261013 版 DeepSeek 客户端：结构化简历抽取、重试与脱敏 I/O 日志。"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from openai import OpenAI

from resume_parser.llm.io_log_261013 import (
    ModelIOLogger261013,
    TraceContext261013,
    new_request_id,
)
from resume_parser.prompt_261013 import SYSTEM_PROMPT, build_user_prompt


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    match = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", text, re.IGNORECASE)
    return match.group(1).strip() if match else text


class DeepSeekClient261013:
    """调用 DeepSeek JSON mode，并为每次 attempt 记录独立日志。"""

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        io_logger: ModelIOLogger261013 | None = None,
    ) -> None:
        if not api_key or not str(api_key).strip():
            raise ValueError("api_key cannot be empty")
        self._client = OpenAI(
            api_key=str(api_key).strip(),
            base_url=str(base_url).rstrip("/"),
        )
        self._model = model
        self._io_logger = io_logger or ModelIOLogger261013()
        self.last_usage: dict[str, int] = self._empty_usage()

    @staticmethod
    def _empty_usage() -> dict[str, int]:
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "api_calls": 0,
        }

    def parse_resume_to_dict(
        self,
        resume_text: str,
        *,
        trace: TraceContext261013 | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(resume_text)},
        ]
        current_trace = trace or TraceContext261013(request_id=new_request_id())
        return self._complete_json(messages, current_trace, diagnostics or {})

    def _complete_json(
        self,
        messages: list[dict[str, Any]],
        trace: TraceContext261013,
        diagnostics: dict[str, Any],
    ) -> dict[str, Any]:
        last_raw = ""
        self.last_usage = self._empty_usage()

        for attempt_index in range(2):
            attempt = attempt_index + 1
            started_at = time.perf_counter()
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    temperature=0,
                    response_format={"type": "json_object"},
                    messages=messages,
                )
            except Exception as exc:
                self._io_logger.log_attempt(
                    trace=trace,
                    attempt=attempt,
                    status="api_error",
                    model=self._model,
                    messages=messages,
                    raw_output="",
                    parsed_output=None,
                    duration_ms=round((time.perf_counter() - started_at) * 1000),
                    usage={},
                    error_type=type(exc).__name__,
                    error_message="DeepSeek API call failed",
                    diagnostics=diagnostics,
                )
                raise RuntimeError("DeepSeek API call failed") from exc

            usage_obj = getattr(response, "usage", None)
            attempt_usage = {
                "prompt_tokens": int(getattr(usage_obj, "prompt_tokens", 0) or 0),
                "completion_tokens": int(
                    getattr(usage_obj, "completion_tokens", 0) or 0
                ),
                "total_tokens": int(getattr(usage_obj, "total_tokens", 0) or 0),
            }
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                self.last_usage[key] += attempt_usage[key]
            self.last_usage["api_calls"] += 1

            choice = response.choices[0] if response.choices else None
            last_raw = (
                choice.message.content
                if choice and choice.message and choice.message.content is not None
                else ""
            )
            parsed = self._try_parse_json(last_raw)
            status = "ok" if parsed is not None else "invalid_json"
            self._io_logger.log_attempt(
                trace=trace,
                attempt=attempt,
                status=status,
                model=self._model,
                messages=messages,
                raw_output=last_raw,
                parsed_output=parsed,
                duration_ms=round((time.perf_counter() - started_at) * 1000),
                usage=attempt_usage,
                diagnostics=diagnostics,
            )
            if parsed is not None:
                return parsed

        raise RuntimeError("Model response is not valid JSON after retry")

    @staticmethod
    def _try_parse_json(raw: str) -> dict[str, Any] | None:
        try:
            value = json.loads(_strip_json_fence(raw))
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None


DeepSeekClient = DeepSeekClient261013
