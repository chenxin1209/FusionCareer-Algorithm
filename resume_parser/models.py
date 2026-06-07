from pydantic import BaseModel
from typing import Optional, Dict, Any, List

class ParseRequest(BaseModel):
    file_url: Optional[str] = None       # 远程文件 URL
    file_base64: Optional[str] = None    # Base64 编码的文件
    raw_text: Optional[str] = None       # 直接传入已提取的文本
    options: Optional[Dict[str, Any]] = {}

class ParseResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: Optional[Dict[str, Any]] = None