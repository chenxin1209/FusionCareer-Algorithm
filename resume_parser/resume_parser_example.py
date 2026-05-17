"""
Example: single-file parse and batch CSV export.

Set environment variable DEEPSEEK_API_KEY before running:
  set DEEPSEEK_API_KEY=your_key_here   (Windows CMD)
  $env:DEEPSEEK_API_KEY="your_key"     (PowerShell)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from resume_parser import ResumeParser


def main() -> None:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("Please set environment variable DEEPSEEK_API_KEY")

    parser = ResumeParser(api_key=api_key)
    project_root = Path(__file__).resolve().parent
    sample_dir = project_root / "测试简历"

    # Single file
    samples = list(sample_dir.glob("*.docx")) + list(sample_dir.glob("*.pdf"))
    if samples:
        one = samples[0]
        print(f"Parsing: {one}")
        result = parser.parse(str(one))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("No sample resumes under 测试简历/; skip single-file demo.")

    # Batch CSV
    if len(samples) >= 1:
        paths = [str(p) for p in samples]
        out_csv = project_root / "resume_parse_export.csv"
        parser.parse_batch_to_csv(paths, str(out_csv))
        print(f"Batch export written: {out_csv}")


if __name__ == "__main__":
    main()
