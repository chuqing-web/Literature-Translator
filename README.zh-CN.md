# 文献翻译器

**用自己的语言读外文论文——版式还在，理解才在。**

面向科研人员、研究生，以及所有需要真正「读懂」文献、而不只是丢进机器翻译的人。本地优先的双语 PDF 阅读工作室：上传论文、保留原版排版、按段落对照译文、边读边批注，遇到难懂的方法节还可以直接问「论文助手」。

[English](./README.md) · [中文](./README.zh-CN.md)

---

## 界面预览

### 本地书库

上传论文、查看就绪状态，从本机书库随时打开。

![书库 — 本地论文列表](./picture/home.png)

### 左右对照双语阅读

左侧原文 PDF，右侧按版式对齐的中文译文；右侧栏可切换笔记与论文助手。

![阅读器 — 左右对照与页边笔记](./picture/reader-demo.png)

---

## 为什么做这个工具

学术 PDF 对通用翻译工具极不友好。

普通翻译器往往把整页压成一堵字墙：图漂走了、公式没了、图注贴错段。你失去了论文可读的「空间地图」——栏、图、主张与证据之间的位置关系。

文献翻译器专为 **保留版式的双语阅读** 而设计：

1. **解析** PDF，抽出带边界框的有序文本块  
2. **翻译** 这些文本块（任意兼容 OpenAI 接口的模型）  
3. **渲染** 用 pdf.js 显示原文，再按坐标贴回译文——可嵌在段落下，也可左右分栏同步滚动  

论文留在本机磁盘。密钥留在本机。服务跑在 `localhost`。

---

## 适合谁用

| 你是… | 你能得到… |
|-------|-----------|
| 需要快速过非母语论文的研究者 | 在不牺牲版式的前提下提高理解效率 |
| 正在攒阅读清单的研究生 | 本地书库：已译、已注、可反复打开 |
| 双语实验室 / 读书会 | 统一流程：翻译 → 笔记 → 讨论 |
| 在意数据落点的人 | 无云账号默认上传，数据在你自己的磁盘 |

---

## 你能做什么

### 保留版式的双语阅读

- **文内对照** — 译文出现在页面上各原文块下方，字体与行距可调  
- **左右对照** — 左原文、右译文；同页尺寸、块对齐、滚动同步  
- **按块修改** — 改掉一句误译，修改会持久保存在本地  

图与疑似公式区域保留 PDF 视觉；图注单独成块，翻译时不拆散页面。

### 本地书库

- 上传文字型 PDF  
- 查看解析 / 翻译状态  
- 随时重新打开继续读  

### 高亮、笔记与论文助手

- 高亮原文块，不破坏叠层版式  
- 将 **页边笔记** 锚定到选中块或页面  
- 与 **论文助手** 对话：默认结合选中段落，否则当前页，也可切换全文；每篇论文一条连续线程  

### 模型与密钥由你掌控

- 接入任意 **兼容 OpenAI** 的接口（云端、网关、Ollama 等本地服务）  
- 多服务商配置、厂商预设、解析后的实际请求 URL 预览  
- 密钥仅存本机并做落盘混淆，不依赖共享云账号  

### 需要时再导出

- 导出双语内容为 **Word（.docx）**，便于改稿或分享  

---

## 工作原理

```
浏览器（Vue 3 + pdf.js）
        │  REST
        ▼
本机 FastAPI :8787
        ├── SQLite（文档、文本块、译文、笔记、高亮、助手）
        ├── data/library/{doc_id}.pdf
        └── 兼容 OpenAI 的聊天接口（翻译 + 论文助手）
```

1. **上传** PDF → 存入 `data/library/`  
2. **解析**（PyMuPDF）→ 有序文本块 + 边界框写入 SQLite  
3. **翻译** 按块调用你配置的服务商  
4. **阅读** 文内叠层或左右镜像译文页  
5. **批注** 笔记 / 高亮；用限定范围的上下文 **提问** 论文助手  

---

## 功能一览

| 能力 | 说明 |
|------|------|
| 双语阅读 | 文内对照 + 左右对照，版式对齐 |
| 翻译 | 兼容 OpenAI；按块进度与重试 |
| 论文助手 | 上下文：选中段 → 当前页 → 全文 |
| 书库 | 本地列表、状态、打开 / 删除 |
| 笔记与高亮 | 锚定到块 / 页 |
| 排版 | 译文字体、字号、行高 |
| 界面语言 | 中文 / English |
| 隐私 | localhost + 本地数据；密钥不出本机 |
| 导出 | Word（.docx）双语导出 |

---

## 运行环境

- **Windows** 推荐使用一键脚本 `scripts/start.ps1`  
- **Python 3.11+**（后端）  
- **Node.js 18+**（Vite 前端）  
- **文字型 PDF**（可选中文字）。扫描件 / 纯图 PDF 本版本会标记为不支持，尚无 OCR  
- **兼容 OpenAI 的 API**（或本地模型服务），用于翻译与论文助手  

---

## 快速开始

### 推荐方式（Windows）

在仓库根目录执行：

```powershell
.\scripts\start.ps1
```

会启动 API 与前端，并打开 **http://127.0.0.1:5173/** 。

**关闭浏览器标签页会自动停止前后端**（心跳 + 关闭信标）。

若希望不依赖浏览器标签、保持进程常驻：

```powershell
$env:LT_AUTO_SHUTDOWN = "0"
.\scripts\start.ps1
```

### 手动启动

**后端**

```bash
cd apps/api
python3.11 -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8787
```

**前端**（另开终端）

```bash
cd apps/web
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

打开 http://127.0.0.1:5173/ → **设置** 添加服务商 → **书库** 上传 PDF → **翻译** → 开始阅读。

---

## 五分钟上手

1. **配置服务商** — 设置 → 选预设或填写 Base URL / 模型 / API 密钥 → 测试 → 设为默认  
2. **上传论文** — 书库 → 上传 PDF（优先可选中文字的学术 PDF）  
3. **开始翻译** — 打开阅读器 → 翻译；查看按页 / 按块进度  
4. **选择视图** — 文内对照，或左右对照  
5. **深入理解** — 选中难懂段落 → 笔记或论文助手 → 问这段方法在主张什么  

---

## 配置说明

### 翻译服务商

在 **设置** 中可以：

- 使用厂商预设，或完全自定义兼容 OpenAI 的 Base URL  
- 预览实际聊天补全请求 URL  
- 对非标准网关开启 **完整 URL 模式**  
- 保存多个配置并切换默认项  

API 密钥只保存在本地 `data/`（本机密钥文件落盘混淆）。

### 阅读偏好

- 默认阅读模式：文内 / 左右  
- 译文排版：字体、字号、行高  
- 界面语言：中文 / English  

### 运行时数据

| 路径 | 内容 |
|------|------|
| `data/lit.db` | SQLite：文档、块、译文、笔记、助手等 |
| `data/library/` | 上传的 PDF |
| `data/` 密钥文件 | API 密钥本地加密材料 |

`data/` 已加入 gitignore，请当作你的私人书库对待。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3、Vite、TypeScript、pdf.js、Vue Router |
| 后端 | FastAPI、SQLAlchemy、aiosqlite、PyMuPDF、httpx |
| 存储 | SQLite + 磁盘 PDF |
| AI | 兼容 OpenAI 的 Chat Completions（翻译 + 论文助手） |
| 导出 | python-docx |

---

## 产品原则

- **版式即语义** — 译文必须尊重文字在页面上的位置  
- **本地优先** — 论文与密钥默认留在本机  
- **模型无关** — 按预算、延迟或实验室策略自选接口  
- **阅读优于灌字** — 笔记、高亮与限定上下文的助手，服务的是理解，而不只是转换  

---

## 当前限制

- 无云账号 / 多用户同步  
- 无扫描件 OCR（会给出明确的不支持状态）  
- 论文助手为请求–响应（v1 无流式）；每文档一条线程  
- 本版本不做图理解 / 视觉问答，也不做向量 RAG  
- Word 导出为尽力而为的结构导出，非 PDF 像素级复刻  

---

## 仓库结构

```
Literature Translator/
├── apps/
│   ├── api/          # FastAPI 后端
│   └── web/          # Vue 3 前端
├── scripts/          # start.ps1 与诊断脚本
├── docs/             # 设计说明与实现计划
└── data/             # 运行时数据库与 PDF（本地，gitignore）
```

---

## 参与贡献

欢迎改进解析质量、阅读体验、服务商兼容性与文档的 Issue / PR。请保持产品文案、代码与文档不出现本项目刻意回避的第三方产品中文品牌名。

---

## 许可

本项目采用 [Apache License, Version 2.0](./LICENSE) 开源许可。

```
Copyright 2026 chenqicheng

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```
