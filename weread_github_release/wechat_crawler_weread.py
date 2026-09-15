#!/usr/bin/env python3
"""
微信公众号监测（微信读书扫码版）— 命令行入口

用法:
  python wechat_crawler_weread.py login
  python wechat_crawler_weread.py bootstrap
  python wechat_crawler_weread.py daily
  python wechat_crawler_weread.py daily --fresh
"""
from __future__ import annotations

import argparse
import sys

from weread.auth import obtain_credentials
from weread.modes import mode_bootstrap, mode_daily
from weread.paths import get_articles_base_dir, load_account_names, load_config, load_fakeids


def main() -> None:
    parser = argparse.ArgumentParser(description="微信公众号监测（微信读书扫码版）")
    parser.add_argument(
        "command",
        choices=("login", "bootstrap", "daily"),
        help="login=扫码；bootstrap=初始化；daily=增量",
    )
    parser.add_argument("--fresh", action="store_true", help="强制重新扫码")
    args = parser.parse_args()

    if args.command == "login":
        obtain_credentials(force_fresh=True)
        print("登录完成。下一步可执行 bootstrap 或 daily。")
        return

    config = load_config()
    fakeids = load_fakeids()
    if not fakeids:
        print("错误: gzh.txt 为空或不存在")
        sys.exit(1)
    account_names = load_account_names()
    if len(account_names) != len(fakeids):
        print(
            f"警告: 公众号名字({len(account_names)}) 与 gzh.txt({len(fakeids)}) 行数不一致"
        )
    print(f"加载了 {len(fakeids)} 个公众号")
    articles_base_dir = get_articles_base_dir(config)

    try:
        credentials = obtain_credentials(force_fresh=args.fresh)
    except Exception as e:
        print(f"登录失败: {e}")
        sys.exit(1)

    if args.command == "bootstrap":
        limit = int(config.get("bootstrap_article_limit", 10))
        mode_bootstrap(
            credentials, fakeids, account_names, limit, articles_base_dir, config
        )
    else:
        mode_daily(credentials, fakeids, account_names, articles_base_dir, config)


if __name__ == "__main__":
    main()
