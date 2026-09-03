# 项目文档索引

本仓库保留**监测算法与固定公众号清单**；爬取结果目录（如 `公众号文章/`、`history.json`）在运行后生成。

| 文档 | 说明 |
|------|------|
| [01-公众号fakeid获取.md](./01-公众号fakeid获取.md) | fakeid 概念、清单维护（`gzh.txt` + `公众号名字`） |
| [02-公众号文章爬取结果.md](./02-公众号文章爬取结果.md) | 爬取流程、配置、运行后产出与统计方法 |
| **[03-终端命令手册.md](./03-终端命令手册.md)** | **按步骤整理的全部终端命令（推荐查阅）** |

## 根目录核心文件

| 路径 | 作用 |
|------|------|
| `wechat_crawler.py.py` | 主爬虫：`bootstrap` / `daily` / `watch` |
| `pipeline.sh` | 流水线入口 |
| `sync_wechat_session.py` | 同步 token/cookie → `config.json` |
| `gzh.txt` / `公众号名字` | 固定监测清单（当前 60 个，逐行对应） |
| `config.json` | 凭证与运行参数（勿公开提交） |
| `requirements.txt` | Python 依赖 |
| `AIAgent_algorithm/` | 虚拟环境 |

**常用命令**：`./pipeline.sh sync-session` · `./pipeline.sh bootstrap` · `./pipeline.sh daily` · `./pipeline.sh install-cron`（每天北京时间 17:00）— 完整列表见 [03-终端命令手册.md](./03-终端命令手册.md)
