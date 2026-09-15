# 微信读书版公众号监测

现行方案：**微信读书扫码** + 固定 **25** 个公众号清单。  
旧公众平台 token/cookie 方案（原 60 号）已移至 `archive/`。

| 文档 | 说明 |
|------|------|
| [01-清单与鉴权.md](./01-清单与鉴权.md) | fakeid 清单、读书扫码 |
| [02-爬取流程与产出.md](./02-爬取流程与产出.md) | bootstrap / daily 与目录 |
| [03-终端命令手册.md](./03-终端命令手册.md) | 命令步骤 |

## 代码结构

```text
wechat_crawler_weread.py   # CLI 入口
weread/
  auth.py                  # 扫码登录 / 会话
  client.py                # 文章列表
  storage.py               # 正文 → Markdown
  modes.py                 # bootstrap / daily
  paths.py                 # 路径与配置
pipeline.sh                # 一键入口
gzh.txt / 公众号名字         # 监测清单
```

常用：`./pipeline.sh login` · `./pipeline.sh bootstrap` · `./pipeline.sh daily`
