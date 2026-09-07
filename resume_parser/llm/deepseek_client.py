"""DeepSeek client (OpenAI-compatible): JSON-mode text extraction."""

from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from resume_parser.prompt import SYSTEM_PROMPT, build_user_prompt


def _strip_json_fence(raw: str) -> str:
    s = raw.strip()
    m = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", s, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return s


class DeepSeekClient:
    """Call DeepSeek Chat with JSON response format; retry once on parse failure."""

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
    ) -> None:
        if not api_key or not str(api_key).strip():
            raise ValueError("api_key cannot be empty")
        self._client = OpenAI(
            api_key=api_key.strip(),
            base_url=base_url.rstrip("/"),
        )
        self._model = model
        self.last_usage: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "api_calls": 0,
        }

    def parse_resume_to_dict(self, resume_text: str) -> dict[str, Any]:
        """
        将简历纯文本送入模型，返回解析后的 dict。

        Raises:
            RuntimeError: API 失败或两次均无法解析 JSON。
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(resume_text)},
        ]
        return self._complete_json(messages)

    def _complete_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        last_raw = ""
        self.last_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "api_calls": 0,
        }

        for attempt in range(2):
            try:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    temperature=0,
                    response_format={"type": "json_object"},
                    messages=messages,
                )
            except Exception as e:
                raise RuntimeError(f"DeepSeek API call failed: {e}") from e

            usage = getattr(resp, "usage", None)
            self.last_usage["prompt_tokens"] += int(
                getattr(usage, "prompt_tokens", 0) or 0
            )
            self.last_usage["completion_tokens"] += int(
                getattr(usage, "completion_tokens", 0) or 0
            )
            self.last_usage["total_tokens"] += int(
                getattr(usage, "total_tokens", 0) or 0
            )
            self.last_usage["api_calls"] += 1

            choice = resp.choices[0] if resp.choices else None
            if not choice or not choice.message or choice.message.content is None:
                last_raw = ""
            else:
                last_raw = choice.message.content
                parsed = self._try_parse_json(last_raw)
                if parsed is not None:
                    return parsed
            if attempt == 0:
                continue

        snippet = (last_raw[:2000] + "...") if len(last_raw) > 2000 else last_raw
        raise RuntimeError(
            "Model response is not valid JSON (retried once). Snippet:\n" + snippet
        )

    @staticmethod
    def _try_parse_json(raw: str) -> dict[str, Any] | None:
        s = _strip_json_fence(raw)
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            return None
        if not isinstance(obj, dict):
            return None
        return obj
