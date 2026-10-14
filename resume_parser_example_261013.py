"""261013 版简历解析示例；不会覆盖旧版导出文件。"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

from resume_parser.parser_261013 import FIELD_NAMES, ResumeParser261013, _row_for_csv


_RESUME_GLOBS = ("*.docx", "*.pdf", "*.png", "*.jpg", "*.jpeg")


def _collect_samples(sample_dir: Path) -> list[Path]:
    paths: list[Path] = []
    if sample_dir.is_dir():
        for pattern in _RESUME_GLOBS:
            paths.extend(sample_dir.glob(pattern))
    return sorted(set(paths))


def main() -> None:
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("请先设置环境变量 DEEPSEEK_API_KEY。", file=sys.stderr)
        raise SystemExit(1)

    parser = ResumeParser261013(
        api_key=api_key,
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        actor_hmac_secret=os.getenv("RESUME_MODEL_IO_ACTOR_HMAC_SECRET", ""),
    )
    project_root = Path(__file__).resolve().parent
    samples = _collect_samples(project_root / "测试简历")
    if not samples:
        print("测试简历目录中没有可解析文件。")
        return

    rows: list[dict[str, str]] = []
    for path in samples:
        print(f"\n--- 261013 解析: {path.name} ---")
        result = parser.parse(str(path))
        rows.append(_row_for_csv(result))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(parser.last_metrics, ensure_ascii=False, indent=2))

    output = project_root / "resume_parse_export_261013.csv"
    with output.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELD_NAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"完成：{output}")


if __name__ == "__main__":
    main()
