"""
示例：解析 测试简历/ 下全部样例（.docx / .pdf / .png / .jpg / .jpeg），并批量导出 CSV。

环境变量：
    DEEPSEEK_API_KEY  DeepSeek API 密钥（必填）

用法（PowerShell）：
    $env:DEEPSEEK_API_KEY = "sk-..."
    python resume_parser_example.py
"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

from resume_parser import ResumeParser
from resume_parser.parser import FIELD_NAMES, _row_for_csv

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

    parsed_rows: list[dict[str, str]] = []
    metrics: list[dict[str, int | float]] = []
    for path in samples:
        print(f"\n--- 解析: {path.name} ({path.suffix.lower()}) ---")
        result = parser.parse(str(path))
        parsed_rows.append(_row_for_csv(result))
        metrics.append(parser.last_metrics.copy())
        filled = {k: v for k, v in result.items() if v not in ("", [], None)}
        print(f"已填充字段: {len(filled)} / {len(result)}")
        print(
            "本次统计: "
            f"输入 Token={parser.last_metrics['prompt_tokens']}, "
            f"输出 Token={parser.last_metrics['completion_tokens']}, "
            f"总 Token={parser.last_metrics['total_tokens']}, "
            f"API 调用={parser.last_metrics['api_calls']}, "
            f"耗时={parser.last_metrics['elapsed_seconds']:.3f} 秒"
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))

    out_csv = project_root / "resume_parse_export.csv"
    print(f"\n--- 批量导出 CSV ({len(samples)} 份) -> {out_csv} ---")
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELD_NAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(parsed_rows)

    count = len(metrics)
    prompt_tokens = sum(item["prompt_tokens"] for item in metrics)
    completion_tokens = sum(item["completion_tokens"] for item in metrics)
    total_tokens = sum(item["total_tokens"] for item in metrics)
    elapsed_seconds = sum(item["elapsed_seconds"] for item in metrics)
    print(
        "平均统计: "
        f"输入 Token={prompt_tokens / count:.1f}, "
        f"输出 Token={completion_tokens / count:.1f}, "
        f"总 Token={total_tokens / count:.1f}, "
        f"耗时={elapsed_seconds / count:.3f} 秒"
    )
    print("完成。")


if __name__ == "__main__":
    main()
