# 微信公众号监测爬虫（微信读书扫码版）

固定 **25** 个就业类公众号：扫码登录微信读书 → bootstrap / daily 增量 → 本地 Markdown 存档。

## 结构

```text
wechat_crawler_weread.py   # CLI
pipeline.sh
weread/                    # auth / client / storage / modes / paths
gzh.txt / 公众号名字
config.example.json
docs/
```

## 快速开始

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.json config.json
chmod +x pipeline.sh

./pipeline.sh login
./pipeline.sh bootstrap
./pipeline.sh daily
```

勿提交 `weread_session.json`。旧公众平台方案见项目 `archive/`（不在本上传包内）。
