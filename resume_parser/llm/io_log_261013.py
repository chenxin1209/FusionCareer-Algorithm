"""261013 版简历模型 I/O JSONL 日志，默认脱敏且写入失败不影响解析。"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


LOG_SCHEMA_VERSION = "261013-1"
_TZ = timezone(timedelta(hours=8))
_WRITE_LOCK = threading.Lock()
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)1[3-9](?:[\s-]?\d){9}(?!\d)")
_ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_WECHAT_LABEL_RE = re.compile(r"((?:微信(?:号)?|wechat)\s*[:：]\s*)[^\s,，;；|]+", re.I)
_NAME_LABEL_RE = re.compile(r"(姓名\s*[:：]\s*)[^\s,，;；|]{2,12}")
_ADDRESS_LABEL_RE = re.compile(
    r"((?:家庭住址|现居住地|现居地|通讯地址|联系地址|地址)\s*[:：]\s*)[^\n;；|]+"
)
_ACCOUNT_LABEL_RE = re.compile(
    r"((?:QQ|学号|护照号|身份证号)\s*[:：]\s*)[^\s,，;；|]+", re.I
)
_JSON_SECRET_RE = re.compile(
    r"(\"(?:real_name|name|phone|mobile|email|wechat|birth_date|hometown|address|student_id|qq)\"\s*:\s*\")[^\"]*(\")",
    re.I,
)
_SENSITIVE_KEYS = {
    "real_name",
    "realname",
    "name",
    "姓名",
    "phone",
    "mobile",
    "telephone",
    "手机号",
    "电话",
    "email",
    "邮箱",
    "wechat",
    "wechat_id",
    "微信",
    "微信号",
    "birth_date",
    "birthdate",
    "出生日期",
    "hometown",
    "address",
    "地址",
    "student_id",
    "studentid",
    "学号",
    "qq",
    "id_card",
    "身份证号",
    "passport",
    "护照号",
    "file_url",
    "file_base64",
}
_TOKEN_PLACEHOLDERS = {
    "real_name": "[NAME_REDACTED]",
    "realname": "[NAME_REDACTED]",
    "name": "[NAME_REDACTED]",
    "姓名": "[NAME_REDACTED]",
    "phone": "[PHONE_REDACTED]",
    "mobile": "[PHONE_REDACTED]",
    "email": "[EMAIL_REDACTED]",
    "wechat": "[WECHAT_REDACTED]",
    "wechat_id": "[WECHAT_REDACTED]",
}
_NORMALIZED_SENSITIVE_KEYS = {
    re.sub(r"[-_\s]+", "", key.lower()) for key in _SENSITIVE_KEYS
}
_NORMALIZED_TOKEN_PLACEHOLDERS = {
    re.sub(r"[-_\s]+", "", key.lower()): value
    for key, value in _TOKEN_PLACEHOLDERS.items()
}


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def new_request_id() -> str:
    return uuid4().hex


def hash_actor(actor_id: str, secret: str) -> str:
    """使用 HMAC 生成不可直接枚举的用户关联标识；缺少密钥时不记录。"""
    actor = str(actor_id or "").strip()
    key = str(secret or "").strip()
    if not actor or not key:
        return ""
    return hmac.new(
        key.encode("utf-8"), actor.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def hash_text(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _redact_text(value: str) -> str:
    text = str(value or "")
    text = _EMAIL_RE.sub("[EMAIL_REDACTED]", text)
    text = _PHONE_RE.sub("[PHONE_REDACTED]", text)
    text = _ID_CARD_RE.sub("[ID_REDACTED]", text)
    text = _WECHAT_LABEL_RE.sub(r"\1[WECHAT_REDACTED]", text)
    text = _NAME_LABEL_RE.sub(r"\1[NAME_REDACTED]", text)
    text = _ADDRESS_LABEL_RE.sub(r"\1[ADDRESS_REDACTED]", text)
    text = _ACCOUNT_LABEL_RE.sub(r"\1[ACCOUNT_REDACTED]", text)
    text = _JSON_SECRET_RE.sub(r"\1[REDACTED]\2", text)
    return text


def _normalized_key(value: Any) -> str:
    return re.sub(r"[-_\s]+", "", str(value or "").lower())


def _is_sensitive_key(value: Any) -> bool:
    normalized = _normalized_key(value)
    return normalized in _NORMALIZED_SENSITIVE_KEYS


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _is_sensitive_key(key) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _sensitive_tokens(value: Any) -> dict[str, str]:
    tokens: dict[str, str] = {}
    if not isinstance(value, dict):
        return tokens

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                normalized = _normalized_key(key)
                if _is_sensitive_key(key) and isinstance(child, (str, int)):
                    token = str(child).strip()
                    if len(token) >= 2:
                        placeholder = _NORMALIZED_TOKEN_PLACEHOLDERS.get(
                            normalized, "[DIRECT_IDENTIFIER_REDACTED]"
                        )
                        tokens[token] = placeholder
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return tokens


def _replace_tokens(value: Any, tokens: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {str(key): _replace_tokens(item, tokens) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_tokens(item, tokens) for item in value]
    if isinstance(value, str):
        result = value
        for token, placeholder in sorted(
            tokens.items(), key=lambda pair: len(pair[0]), reverse=True
        ):
            result = result.replace(token, placeholder)
        return result
    return value


def _truncate_strings(value: Any, limit: int) -> Any:
    if isinstance(value, dict):
        return {str(key): _truncate_strings(item, limit) for key, item in value.items()}
    if isinstance(value, list):
        return [_truncate_strings(item, limit) for item in value]
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"\n[TRUNCATED_{len(value) - limit}_CHARS]"
    return value


@dataclass(frozen=True)
class TraceContext261013:
    request_id: str
    actor_hash: str = ""
    source_kind: str = "unknown"
    source_sha256: str = ""


class ModelIOLogger261013:
    """按天追加 JSONL。生产默认记录脱敏输入输出，不创建 latest 快照。"""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        log_dir: str | Path | None = None,
        include_sensitive: bool | None = None,
        max_text_chars: int | None = None,
    ) -> None:
        self.enabled = (
            _env_flag("RESUME_MODEL_IO_LOG_ENABLED", True)
            if enabled is None
            else bool(enabled)
        )
        self.include_sensitive = (
            _env_flag("RESUME_MODEL_IO_LOG_INCLUDE_SENSITIVE", False)
            if include_sensitive is None
            else bool(include_sensitive)
        )
        configured_dir = os.getenv(
            "RESUME_MODEL_IO_LOG_DIR", "logs/resume_llm_io_261013"
        )
        self.log_dir = Path(log_dir or configured_dir)
        configured_limit = os.getenv("RESUME_MODEL_IO_LOG_MAX_TEXT_CHARS", "120000")
        try:
            parsed_limit = int(configured_limit)
        except ValueError:
            parsed_limit = 120000
        self.max_text_chars = max(1000, int(max_text_chars or parsed_limit))

    def log_attempt(
        self,
        *,
        trace: TraceContext261013,
        attempt: int,
        status: str,
        model: str,
        messages: list[dict[str, Any]],
        raw_output: str,
        parsed_output: dict[str, Any] | None,
        duration_ms: int,
        usage: dict[str, int] | None = None,
        error_type: str = "",
        error_message: str = "",
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        if not self.enabled:
            return
        try:
            now = datetime.now(_TZ)
            record: dict[str, Any] = {
                "schema_version": LOG_SCHEMA_VERSION,
                "event_type": (
                    "normalized"
                    if status == "normalized"
                    else (
                        "pipeline_error"
                        if status == "pipeline_error"
                        else "model_attempt"
                    )
                ),
                "timestamp": now.isoformat(timespec="milliseconds"),
                "event_id": uuid4().hex,
                "request_id": trace.request_id,
                "attempt": attempt,
                "status": status,
                "actor_hash": trace.actor_hash,
                "source_kind": trace.source_kind,
                "source_sha256": trace.source_sha256,
                "prompt_version": "261013",
                "system_prompt_sha256": hash_text(
                    next(
                        (
                            str(message.get("content", ""))
                            for message in messages
                            if message.get("role") == "system"
                        ),
                        "",
                    )
                ),
                "user_prompt_sha256": hash_text(
                    next(
                        (
                            str(message.get("content", ""))
                            for message in messages
                            if message.get("role") == "user"
                        ),
                        "",
                    )
                ),
                "model": model,
                "temperature": 0,
                "response_format": "json_object",
                "duration_ms": max(0, int(duration_ms)),
                "usage": usage or {},
                "input": messages,
                "output_raw": raw_output,
                "output_json_valid": isinstance(parsed_output, dict),
                "output_parsed": parsed_output,
                "error_type": error_type,
                "error_message": error_message,
                "diagnostics": diagnostics or {},
            }
            record = _truncate_strings(record, self.max_text_chars)
            if not self.include_sensitive:
                tokens = _sensitive_tokens(parsed_output)
                record = _replace_tokens(_redact(record), tokens)

            path = self.log_dir / f"model_io_261013_{now:%Y-%m-%d}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
            with _WRITE_LOCK:
                with path.open("a", encoding="utf-8") as stream:
                    stream.write(line)
        except Exception:
            # 调试日志不可影响正常解析。
            return

    def log_pipeline_error(
        self,
        *,
        trace: TraceContext261013,
        model: str,
        error_type: str,
        stage: str,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        self.log_attempt(
            trace=trace,
            attempt=0,
            status="pipeline_error",
            model=model,
            messages=[],
            raw_output="",
            parsed_output=None,
            duration_ms=0,
            error_type=error_type,
            error_message=f"resume pipeline failed at {stage}",
            diagnostics={"stage": stage, **(diagnostics or {})},
        )

    def log_normalized(
        self,
        *,
        trace: TraceContext261013,
        model: str,
        normalized_output: dict[str, Any],
        diagnostics: dict[str, Any],
    ) -> None:
        """记录确定性后处理结果，便于区分模型问题和归一化问题。"""
        self.log_attempt(
            trace=trace,
            attempt=0,
            status="normalized",
            model=model,
            messages=[],
            raw_output="",
            parsed_output=normalized_output,
            duration_ms=0,
            diagnostics=diagnostics,
        )
