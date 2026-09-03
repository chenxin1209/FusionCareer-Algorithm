# （1）公众号 fakeid 清单：说明与维护

## 1. 背景与概念

| 术语 | 含义 | 在本项目中的用途 |
|------|------|------------------|
| **fakeid** | 微信公众平台后台为每个公众号分配的内部 ID（常为 Base64 字符串，如 `MzkyOTE3NTA1MQ==`） | 写入 `gzh.txt`，供列表接口查询该号文章 |
| **token** | 登录后台后 URL/请求中的数字令牌 | `config.json`，与 cookie 一起鉴权 |
| **cookie** | 浏览器会话 Cookie 整串 | `config.json` |
| **biz / `__biz`** | 文章页 HTML 中的公众号标识 | **不等于** 后台 fakeid，本项目不使用 |

爬虫基于 [WeChat-Article-Crawler](https://github.com/Shaoshi17/WeChat-Article-Crawler) 思路。监测名单以项目根目录 **`gzh.txt`** 与 **`公众号名字`** 为准（固定监测对象）。

---

## 2. 清单文件（爬虫直接读取）

| 文件 | 内容 | 说明 |
|------|------|------|
| **`gzh.txt`** | 每行一个 **fakeid** | 必需 |
| **`公众号名字`** | 每行一个 **名称** | 与 `gzh.txt` **按行一一对应** |

当前规模：**60** 个公众号（各 60 行）。

**对应关系示例**（第 1 行）：

```
gzh.txt[0]     = MzkyOTE3NTA1MQ==
公众号名字[0]  = FDiCareer
```

爬虫按行号 `i` 取 `gzh.txt[i]` 的 fakeid、`公众号名字[i]` 的显示名（亦作为 `公众号文章/` 下子目录名）。

---

## 3. 维护方式

### 3.1 直接编辑文本（日常）

- **增删公众号**：在 `gzh.txt` 与 `公众号名字` 各增删一行，**行号、顺序一致**。
- **改 fakeid**：只改 `gzh.txt` 对应行。
- **改文件夹名**：改 `公众号名字` 对应行。

改完后执行 `./pipeline.sh bootstrap` 或 `daily`。

### 3.2 从公众平台后台获取 fakeid（新增公众号时）

1. 登录 [微信公众平台](https://mp.weixin.qq.com/)
2. F12 → **Network** → 筛选 XHR
3. 打开素材/群发列表等页面，在请求 URL 或 JSON 中查找 **`fakeid`**
4. 追加到 `gzh.txt` 一行，名称写入 `公众号名字` 同一行号

### 3.3 会话同步（token / cookie）

**脚本**：`sync_wechat_session.py` — 只更新 `config.json`，**不修改** `gzh.txt` / `公众号名字`。

```bash
./pipeline.sh sync-session
```

---

## 4. 与爬取模块的衔接

```
gzh.txt + 公众号名字
    → wechat_crawler.py.py (bootstrap / daily / watch)
        → 运行后生成: 公众号文章/ 、 YYYYMMDD新增/ 、 history.json 等
```

---

## 5. 相关文件

| 路径 | 角色 |
|------|------|
| `gzh.txt` | fakeid 列表（固定监测清单） |
| `公众号名字` | 名称列表（与 fakeid 逐行对应） |
| `config.json` | token / cookie 与运行参数（勿公开提交） |
| `wechat_crawler.py.py` | 主爬虫 |
| `sync_wechat_session.py` | 凭证同步 |
