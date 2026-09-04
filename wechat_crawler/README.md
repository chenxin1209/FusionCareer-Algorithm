# 微信公众号就业类监测爬虫

基于 [WeChat-Article-Crawler](https://github.com/Shaoshi17/WeChat-Article-Crawler) 思路，对固定清单中的公众号做初始化抓取与每日增量监测。

## 固定监测清单

- `gzh.txt`：每行一个 fakeid（当前 60 个）
- `公众号名字`：与 `gzh.txt` 逐行对应的名称（第 1 行为 FDiCareer；其余请补全真实名称）

## 快速开始

```bash
python3 -m venv AIAgent_algorithm
source AIAgent_algorithm/bin/activate
pip install -r requirements.txt
playwright install chromium

cp config.example.json config.json
chmod +x pipeline.sh

./pipeline.sh sync-session   # 浏览器登录同步 token/cookie
./pipeline.sh bootstrap      # 每号最新 10 篇 → 公众号文章/
./pipeline.sh daily          # 增量监测
```

按日期窗口抓取（老师要求的 7–8 月测试数据）：

```bash
python3 wechat_crawler.py.py range --since 2026-07-01 --until 2026-08-31
```

无公众平台登录时，抓 `seed_urls.txt` 中的公开文章：

```bash
python3 fetch_public.py --urls seed_urls.txt --out ../data/articles
```

## 主要文件

| 路径 | 说明 |
|------|------|
| `wechat_crawler.py.py` | 主爬虫：`bootstrap` / `daily` / `watch` / `range` |
| `fetch_public.py` | 公开 URL → Markdown（无需 token） |
| `seed_urls.txt` | 公开测试链接 |
| `pipeline.sh` | 流水线入口 |
| `sync_wechat_session.py` | 同步公众平台凭证 |
| `config.example.json` | 配置模板（复制为 `config.json`） |

完整命令见 [`docs/03-终端命令手册.md`](docs/03-终端命令手册.md)。

## 注意

- 勿将含真实 `token`/`cookie` 的 `config.json` 提交到公开仓库
- 凭证过期会出现 `invalid session`，重新执行 `./pipeline.sh sync-session`
