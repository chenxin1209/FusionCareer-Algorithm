"""261013 版内部简历解析路由；响应字段与旧版保持兼容。"""

from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from fastapi import APIRouter, HTTPException, Response

from resume_parser.config_261013 import settings_261013
from resume_parser.llm.io_log_261013 import ModelIOLogger261013, new_request_id
from resume_parser.models import ParseRequest, ParseResponse
from resume_parser.parser_261013 import ResumeParser261013


router = APIRouter(prefix="/internal/resume", tags=["internal-resume-261013"])
_parser: ResumeParser261013 | None = None


def get_parser_261013() -> ResumeParser261013:
    global _parser
    if _parser is None:
        io_logger = ModelIOLogger261013(
            enabled=settings_261013.resume_model_io_log_enabled,
            log_dir=settings_261013.resume_model_io_log_dir,
            include_sensitive=settings_261013.resume_model_io_log_include_sensitive,
            max_text_chars=settings_261013.resume_model_io_log_max_text_chars,
        )
        _parser = ResumeParser261013(
            api_key=settings_261013.deepseek_api_key,
            model=settings_261013.deepseek_model,
            base_url=settings_261013.deepseek_base_url,
            io_logger=io_logger,
            actor_hmac_secret=settings_261013.resume_model_io_actor_hmac_secret,
        )
    return _parser


async def _download_file(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise ValueError(f"Download failed: HTTP {response.status}")
            return await response.read()


def _file_suffix(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in {".docx", ".pdf", ".png", ".jpg", ".jpeg"} else ".pdf"


def _base64_file(value: str) -> tuple[bytes, str]:
    suffix = ".pdf"
    encoded = value
    if value.startswith("data:") and "," in value:
        header, encoded = value.split(",", 1)
        mime = header.split(";", 1)[0].lower()
        suffix = {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/pdf": ".pdf",
            "image/png": ".png",
            "image/jpeg": ".jpg",
        }.get(mime, suffix)
    return base64.b64decode(encoded), suffix


@router.post("/{user_id}", response_model=ParseResponse)
async def parse_resume_261013(
    user_id: str, request: ParseRequest, response: Response
) -> ParseResponse:
    request_id = new_request_id()
    response.headers["X-Resume-Trace-Id"] = request_id
    try:
        parser = get_parser_261013()
        if request.raw_text:
            result = parser.parse_text(
                request.raw_text,
                actor_id=user_id,
                request_id=request_id,
            )
        elif request.file_url:
            content = await _download_file(request.file_url)
            suffix = _file_suffix(request.file_url)
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temporary:
                temporary.write(content)
                temporary_path = temporary.name
            try:
                result = parser.parse(
                    temporary_path,
                    actor_id=user_id,
                    request_id=request_id,
                )
            finally:
                os.unlink(temporary_path)
        elif request.file_base64:
            content, suffix = _base64_file(request.file_base64)
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temporary:
                temporary.write(content)
                temporary_path = temporary.name
            try:
                result = parser.parse(
                    temporary_path,
                    actor_id=user_id,
                    request_id=request_id,
                )
            finally:
                os.unlink(temporary_path)
        else:
            raise HTTPException(status_code=400, detail="No resume input provided")

        return ParseResponse(message="success", data=result)
    except HTTPException:
        raise
    except Exception:
        # 原始模型输出只进入内部脱敏日志，不通过接口返回。
        return ParseResponse(
            code=500,
            message=f"简历解析失败，请使用追踪编号 {request_id} 联系管理员",
        )
