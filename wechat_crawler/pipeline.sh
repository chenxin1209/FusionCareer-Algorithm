#!/usr/bin/env bash
# 微信公众号爬虫流水线
# 目录命名见 config.json（与 wechat_crawler.py.py 一致）：
#   articles_base_dir          主存档，bootstrap / daily 写入（默认 公众号文章）
#   YYYYMMDD + daily_folder_suffix  仅 daily 当日增量（默认 20260517新增）

set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

VENV_PY="$ROOT/AIAgent_algorithm/bin/python3"
CRAWLER="$ROOT/wechat_crawler.py.py"
LOG_DIR="$ROOT/logs"
CONFIG="$ROOT/config.json"

if [[ ! -x "$VENV_PY" ]]; then
  echo "未找到虚拟环境: $VENV_PY"
  echo "请先创建: python3 -m venv AIAgent_algorithm && source AIAgent_algorithm/bin/activate && pip install -r requirements.txt"
  exit 1
fi

print_output_dirs() {
  "$VENV_PY" - <<'PY'
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

cfg = json.loads(Path("config.json").read_text(encoding="utf-8"))
base = cfg.get("articles_base_dir", "公众号文章")
suffix = cfg.get("daily_folder_suffix", "新增")
daily = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d") + suffix
print(f"  主存档 (config: articles_base_dir):     {base}/")
print(f"  当日增量 (daily, YYYYMMDD+suffix):      {daily}/")
PY
}

cmd="${1:-help}"
case "$cmd" in
  sync-session)
    "$VENV_PY" "$ROOT/sync_wechat_session.py" "${@:2}"
    ;;
  range)
    echo "输出目录（config.json）:"
    print_output_dirs
    echo ""
    "$VENV_PY" "$CRAWLER" range "${@:2}"
    ;;
  fetch-public)
    ROOT_REPO="$(cd "$ROOT/.." && pwd)"
    python3 "$ROOT/fetch_public.py" --urls "$ROOT/seed_urls.txt" --out "$ROOT_REPO/data/articles" "${@:2}"
    ;;
  daily)
    mkdir -p "$LOG_DIR"
    echo "输出目录（config.json）:"
    print_output_dirs
    echo ""
    "$VENV_PY" "$CRAWLER" daily 2>&1 | tee -a "$LOG_DIR/daily_$(TZ=Asia/Shanghai date +%Y%m%d).log"
    ;;
  install-cron)
    mkdir -p "$LOG_DIR"
    CRON_MARK="# AIAgent_algorithm wechat daily (Beijing 17:00)"
    CRON_JOB="0 17 * * * TZ=Asia/Shanghai cd \"$ROOT\" && \"$VENV_PY\" \"$CRAWLER\" daily >> \"$LOG_DIR/daily_cron.log\" 2>&1"
    CURRENT="$(crontab -l 2>/dev/null || true)"
    if echo "$CURRENT" | grep -Fq "$CRON_MARK"; then
      echo "定时任务已存在，无需重复安装。"
    else
      {
        echo "$CURRENT" | sed '/^$/d'
        echo "$CRON_MARK"
        echo "$CRON_JOB"
      } | crontab -
      echo "已安装 crontab：每天北京时间 17:00 执行 daily"
    fi
    echo "日志: $LOG_DIR/daily_cron.log"
    echo "查看: crontab -l"
    echo "卸载: ./pipeline.sh uninstall-cron"
    ;;
  uninstall-cron)
    CURRENT="$(crontab -l 2>/dev/null || true)"
    if [[ -z "$CURRENT" ]]; then
      echo "当前无 crontab 任务"
      exit 0
    fi
    echo "$CURRENT" | grep -Fv "AIAgent_algorithm wechat daily" | sed '/^$/d' | crontab - 2>/dev/null || true
    echo "已移除 AIAgent_algorithm 相关定时任务"
    ;;
  paths)
    print_output_dirs
    ;;
  help|*)
    cat <<EOF
用法: $0 <command>

  sync-session    同步 token/cookie → config.json
  range [--since YYYY-MM-DD --until YYYY-MM-DD]
                  按日期窗口抓取（默认 2026-07-01 ~ 2026-08-31），需 token/cookie
  fetch-public    抓取 seed_urls.txt 中的公开链接（无需登录） → ../data/articles
  daily           增量 → 主存档 + 当日目录（YYYYMMDD\${daily_folder_suffix}）
  paths           打印当前 config 中的输出目录名
  install-cron    每天北京时间 17:00 自动 daily
  uninstall-cron  移除定时任务

目录规则（config.json）:
  articles_base_dir       主存档，默认: 公众号文章/
  daily_folder_suffix     当日增量后缀，默认: 新增  →  如 20260517新增/

监测清单（固定）: gzh.txt、公众号名字

示例:
  ./pipeline.sh paths
  ./pipeline.sh bootstrap
  ./pipeline.sh daily

文档: docs/03-终端命令手册.md
EOF
    ;;
esac
