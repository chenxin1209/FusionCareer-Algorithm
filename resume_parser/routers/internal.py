from fastapi import APIRouter, HTTPException, status
from models import ParseRequest, ParseResponse
from parser import ResumeParser
from config import settings
import aiohttp
import base64
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

router = APIRouter(prefix="/internal/resume", tags=["internal"])

_parser = None

def get_parser():
    global _parser
    if _parser is None:
        _parser = ResumeParser(api_key=settings.deepseek_api_key)
    return _parser

async def download_file(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise ValueError(f"Download failed: {resp.status}")
            return await resp.read()


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
async def parse_resume(user_id: str, req: ParseRequest):
    try:
        parser = get_parser()
        text = None

        if req.raw_text:
            result = parser.parse_text(req.raw_text)
        elif req.file_url:
            content = await download_file(req.file_url)
            suffix = _file_suffix(req.file_url)
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                result = parser.parse(tmp_path)
            finally:
                os.unlink(tmp_path)
        elif req.file_base64:
            content, suffix = _base64_file(req.file_base64)
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                result = parser.parse(tmp_path)
            finally:
                os.unlink(tmp_path)
        else:
            raise HTTPException(status_code=400, detail="No resume input provided")

        return ParseResponse(data=result)

    except Exception as e:
        return ParseResponse(code=500, message=str(e))