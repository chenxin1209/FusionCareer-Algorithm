"""
向后兼容 CLI（逻辑在 job_structuring.engine）。

推荐使用统一入口:
  python pipeline/run_pipeline.py
"""
from job_structuring.engine import main

if __name__ == "__main__":
    main()
