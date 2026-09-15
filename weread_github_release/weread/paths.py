"""微信读书版公众号监测：路径、配置与清单。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config.json"
FAKEID_FILE = ROOT / "gzh.txt"
ACCOUNT_NAMES_FILE = ROOT / "公众号名字"
HISTORY_FILE = ROOT / "history_weread.json"
SESSION_FILE = ROOT / "weread_session.json"
DEFAULT_ARTICLES_BASE_DIR = "公众号文章"
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def beijing_now() -> datetime:
    return datetime.now(BEIJING_TZ)


def load_json(filepath: Path | str) -> Dict[str, Any]:
    path = Path(filepath)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def save_json(filepath: Path | str, data: Any) -> None:
    Path(filepath).write_text(
        json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def load_config() -> Dict[str, Any]:
    return load_json(CONFIG_FILE)


def load_fakeids() -> List[str]:
    if not FAKEID_FILE.is_file():
        return []
    return [ln.strip() for ln in FAKEID_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]


def load_account_names() -> Dict[int, str]:
    if not ACCOUNT_NAMES_FILE.is_file():
        return {}
    names = [
        ln.strip()
        for ln in ACCOUNT_NAMES_FILE.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    return {i: name for i, name in enumerate(names)}


def get_articles_base_dir(config: Dict[str, Any]) -> str:
    return str(config.get("articles_base_dir", DEFAULT_ARTICLES_BASE_DIR))


def get_daily_folder_basename(config: Dict[str, Any]) -> str:
    suffix = config.get("daily_folder_suffix", "新增")
    return beijing_now().strftime("%Y%m%d") + str(suffix)


def get_daily_increment_dir(config: Dict[str, Any]) -> str:
    return str(ROOT / get_daily_folder_basename(config))
