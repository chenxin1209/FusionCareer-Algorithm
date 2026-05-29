"""
示例：解析 测试简历/ 下全部样例（.docx / .pdf / .png / .jpg / .jpeg），并批量导出 CSV。

环境变量：
    DEEPSEEK_API_KEY  DeepSeek API 密钥（必填）

用法（PowerShell）：
    $env:DEEPSEEK_API_KEY = "sk-..."
    python resume_parser_example.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from resume_parser import ResumeParser

_RESUME_GLOBS = ("*.docx", "*.pdf", "*.png", "*.jpg", "*.jpeg")


def _collect_samples(sample_dir: Path) -> list[Path]:
    if not sample_dir.is_dir():
        return []
    paths: list[Path] = []
    for pattern in _RESUME_GLOBS:
        paths.extend(sample_dir.glob(pattern))
    return sorted(set(paths))


def main() -> None:
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("请先设置环境变量 DEEPSEEK_API_KEY。", file=sys.stderr)
        sys.exit(1)

    parser = ResumeParser(api_key=api_key)
    project_root = Path(__file__).resolve().parent
    sample_dir = project_root / "测试简历"
    samples = _collect_samples(sample_dir)

    if not samples:
        print(f"未在 {sample_dir} 找到简历样例（支持: docx, pdf, png, jpg, jpeg）。")
        sys.exit(0)

    for path in samples:
        print(f"\n--- 解析: {path.name} ({path.suffix.lower()}) ---")
        result = parser.parse(str(path))
        filled = {k: v for k, v in result.items() if v not in ("", [], None)}
        print(f"已填充字段: {len(filled)} / {len(result)}")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    out_csv = project_root / "resume_parse_export.csv"
    print(f"\n--- 批量导出 CSV ({len(samples)} 份) -> {out_csv} ---")
    parser.parse_batch_to_csv([str(p) for p in samples], str(out_csv))
    print("完成。")


if __name__ == "__main__":
    main()
