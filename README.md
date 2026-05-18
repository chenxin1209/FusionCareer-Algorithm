# FusionCareer-Algorithm
FusionCareer-The algorithms team's repository

26.4.30 task: wechat article crawl

## Resume Parser Module 简历解析模块
简历解析模块，支持从PDF及Word格式的简历中提取关键信息，如姓名、联系方式、教育背景、个人经历等。调用DeepSeek输出结构化JSO，直接匹配数据库字段。

## 文件目录结构
```
resume_parser/
├── extractors/
│ ├── init.py
│ ├── docx_extractor.py   # Word 提取：段落、表格、文本框
│ └── pdf_extractor.py   # PDF 提取：文本、表格
├── llm/
│ ├── init.py
│ └── deepseek_client.py   # DeepSeek API 封装
├── init.py
├── parser.py   # 核心解析类 ResumeParser
├── prompt.py   # 提示词模板
├── requirements.txt   # 依赖列表
└── resume_parser_example.py   # 使用示例
```

### 快速开始

#### 1. 安装依赖
```bash
pip install -r requirements.txt
```

#### 2. 配置 API Key
终端设置环境变量 DEEPSEEK_API_KEY，或在项目根目录创建 .env 文件：
```env
set DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

#### 3. 运行示例
```bash
python resume_parser_example.py
```
