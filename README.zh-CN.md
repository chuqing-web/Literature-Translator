# 文献翻译器

**用自己的语言读外文论文——版式还在，理解才在。**

面向科研人员、研究生，以及所有需要真正「读懂」文献、而不只是丢进机器翻译的人。本地优先的双语 PDF 阅读工作室：上传论文、保留原版排版、按段落对照译文、边读边批注，遇到难懂的方法节还可以直接问「论文助手」。

**仓库地址：** [github.com/chuqing-web/Literature-Translator](https://github.com/chuqing-web/Literature-Translator) · [Issues](https://github.com/chuqing-web/Literature-Translator/issues) · 许可 [Apache-2.0](./LICENSE)

[English](./README.md) · [中文](./README.zh-CN.md)

```bash
git clone https://github.com/chuqing-web/Literature-Translator.git
cd Literature-Translator
```

---

## 界面预览

### 本地书库

上传论文、查看就绪状态，从本机书库随时打开。

![书库 — 本地论文列表](./picture/home.png)

### 左右对照双语阅读

左侧原文 PDF，右侧按版式对齐的中文译文；右侧栏可切换笔记与论文助手。

![阅读器 — 左右对照与页边笔记](./picture/reader-demo.png)

### 服务商设置

接入任意兼容 OpenAI 的接口：厂商预设、Base URL、模型、API 密钥、实际请求 URL 预览，以及翻译前的连通性测试。

![设置 — 翻译服务商配置](./picture/settings-page.png)

### 论文助手

基于选中段落、当前页或全文提问；每篇论文一条连续线程，与笔记同栏切换。

![论文助手 — 限定上下文的问答](./picture/paper-assistant.png)

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

| 依赖 | 版本 | 用途 |
|------|------|------|
| 操作系统 | 推荐 Windows 10/11 | 可一键运行 `scripts/start.ps1`；macOS / Linux 用手动步骤 |
| Git | 2.x | 克隆仓库 |
| Python | **3.11+**（推荐 3.11 或 3.12） | FastAPI 后端 |
| Node.js | **18+**（推荐 20 LTS） | Vite + Vue 前端 |
| npm | 随 Node.js 安装 | 前端依赖 |
| PDF | **文字型**（可选中文字）学术 PDF | 扫描件 / 纯图 PDF 本版不支持（尚无 OCR） |
| AI 接口 | 任意 **兼容 OpenAI** 的 Chat Completions | 翻译 + 论文助手（云端或本地，如 Ollama 网关） |

若不想使用云端密钥，可自行准备本地模型服务。

---

## 从零部署（详细流程）

如果你是第一次在这台机器上跑本项目，请按下面逐步操作。命令默认仓库根目录为：

`C:\Projects\Literature-Translator`

路径不同请自行替换。macOS / Linux 使用对应 shell 命令（虚拟环境激活路径不同）。

### 第 0 步 — 安装系统工具

#### 0.1 Git

1. 下载 Git for Windows：https://git-scm.com/download/win  
2. 按默认选项安装。  
3. 验证：

```powershell
git --version
```

#### 0.2 Python 3.11+

1. 从 https://www.python.org/downloads/ 下载 Python 3.11 或 3.12  
2. **重要：** 安装时勾选 **“Add python.exe to PATH”**  
3. 验证（任选其一）：

```powershell
python --version
# 或
py -3.11 --version
```

应显示 `Python 3.11.x` 或 `3.12.x`。若 `python` 指向微软商店占位程序，后续步骤请改用 `py -3.11`。

#### 0.3 Node.js 18+

1. 从 https://nodejs.org/ 下载 **LTS** 安装包  
2. 默认安装（已含 npm）  
3. 验证：

```powershell
node --version
npm --version
```

### 第 1 步 — 获取源码

若本地已有项目目录，可跳到第 2 步。

```powershell
cd C:\Projects
git clone https://github.com/chuqing-web/Literature-Translator.git
cd Literature-Translator
```

或将发行包解压到 `C:\Projects\Literature-Translator` 后进入该目录。

确认目录结构大致如下：

```text
Literature-Translator/
├── apps/
│   ├── api/
│   └── web/
├── scripts/
│   └── start.ps1
├── picture/
├── README.md
└── README.zh-CN.md
```

### 第 2 步 — 创建数据目录（首次）

运行时数据写在 `data/`（已 gitignore）。若目录不存在，先创建：

```powershell
cd "C:\Projects\Literature-Translator"
New-Item -ItemType Directory -Force -Path .\data\library | Out-Null
```

首次启动 API 时，还会自动创建 `data/lit.db` 与本机密钥文件。

### 第 3 步 — 后端：虚拟环境与 Python 依赖

```powershell
cd "C:\Projects\Literature-Translator\apps\api"

# 创建虚拟环境（优先 3.11）
py -3.11 -m venv .venv
# 若失败可改用：
# python -m venv .venv

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -r requirements.txt
```

确认 uvicorn 可用：

```powershell
.\.venv\Scripts\uvicorn.exe --version
```

### 第 4 步 — 前端：安装 npm 依赖

```powershell
cd "C:\Projects\Literature-Translator\apps\web"
npm install
```

### 第 5 步 — 启动服务

#### 方式 A — 一键启动（Windows，推荐）

在**仓库根目录**执行：

```powershell
cd "C:\Projects\Literature-Translator"
.\scripts\start.ps1
```

若 PowerShell 禁止运行脚本：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

然后再执行 `.\scripts\start.ps1`。

脚本会：

1. 若缺少 `apps/api/.venv`，则创建并安装 `requirements.txt`  
2. 若缺少 `apps/web/node_modules`，则执行 `npm install`  
3. 启动 API：**http://127.0.0.1:8787**  
4. 启动前端：**http://127.0.0.1:5173**  
5. 自动打开浏览器  

**默认行为：** 关闭浏览器标签页会停止前后端（心跳 / 离开信标）。

若希望不依赖浏览器标签、进程常驻：

```powershell
$env:LT_AUTO_SHUTDOWN = "0"
.\scripts\start.ps1
```

#### 方式 B — 手动启动（两个终端）

**终端 1 — API**

```powershell
cd "C:\Projects\Literature-Translator\apps\api"
$env:LT_AUTO_SHUTDOWN = "0"
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8787
```

另开窗口做健康检查：

```powershell
curl.exe http://127.0.0.1:8787/api/health
```

返回 JSON 中应包含 `"status":"ok"`。

**终端 2 — 前端**

```powershell
cd "C:\Projects\Literature-Translator\apps\web"
npm run dev -- --host 127.0.0.1 --port 5173
```

浏览器打开 **http://127.0.0.1:5173/** 。

#### macOS / Linux（手动）

```bash
# 后端
cd apps/api
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
LT_AUTO_SHUTDOWN=0 uvicorn app.main:app --host 127.0.0.1 --port 8787

# 前端（第二个终端）
cd apps/web
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

### 第 6 步 — 首次在界面中配置

1. 打开 http://127.0.0.1:5173/  
2. 进入 **设置**  
3. 添加服务商：
   - 选择厂商预设，**或**填写自定义 Base URL  
   - 填写 **模型名** 与 **API 密钥**（本地 Ollama 类服务若忽略密钥，可填占位符）  
   - 非标准网关可开启 **完整 URL 模式**  
   - 点击 **测试**，再设为 **默认**  
4. 回到 **书库** → **上传 PDF**（优先可选中文字的学术 PDF）  
5. 打开文档 → **翻译** → 等待按块进度  
6. 选择 **文内对照** 或 **左右对照**  
7. 选中段落 → 使用 **笔记** 或 **论文助手**  

### 第 7 步 — 验收部署是否成功

| 检查项 | 方法 | 预期 |
|--------|------|------|
| API 存活 | `curl.exe http://127.0.0.1:8787/api/health` | `"status":"ok"` |
| 前端存活 | 打开 http://127.0.0.1:5173/ | 书库界面正常 |
| 服务商 | 设置 → 测试 | 成功 |
| 解析 | 上传文字型 PDF | 状态变为可阅读 / 就绪 |
| 翻译 | 阅读器 → 翻译 | 文本块出现目标语言译文 |
| 本地落盘 | 查看 `data/library/` 与 `data/lit.db` | 存在 PDF 与 SQLite |

### 端口与环境变量

| 项目 | 默认 | 覆盖方式 |
|------|------|----------|
| API | `127.0.0.1:8787` | `LT_API_HOST` / `LT_API_PORT`（环境变量前缀 `LT_`） |
| 前端（Vite） | `127.0.0.1:5173` | `npm run dev` 传 `--port` |
| 自动关闭 | 开启 | `$env:LT_AUTO_SHUTDOWN = "0"` |
| 数据目录 | `<仓库>/data` | `LT_DATA_DIR` |

若 8787 或 5173 已被占用，请先结束占用进程或改端口。

### 常见问题排查

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 找不到 `python` / `py` | Python 未进 PATH | 重装并勾选 Add to PATH，或使用 `python.exe` 全路径 |
| 找不到 `npm` | 未装 Node | 安装 Node.js LTS 后重开终端 |
| 找不到 `uvicorn` | 虚拟环境未建 / 依赖未装 | 重做第 3 步 |
| `start.ps1` 执行策略错误 | PowerShell 策略过严 | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| 端口被占用 | 其他程序占用 8787/5173 | `Get-NetTCPConnection -LocalPort 8787,5173` 后结束对应 PID |
| 访问 API 健康检查出现代理 **502** | 系统 HTTP 代理劫持了 localhost | 设置 `NO_PROXY=127.0.0.1,localhost`，或对本地地址关闭代理 |
| 前端能开但接口失败 | API 未启动 / 地址不对 | 确认终端 1 在跑；访问 `/api/health` |
| PDF 显示不支持 | 扫描件 / 纯图 PDF | 换用可选中文字的 born-digital PDF |
| 翻译报错 | 密钥 / 模型 / Base URL 错误 | 在设置中修正后重新测试 |
| 中文或公式显示被裁切 | 叠层与密排公式冲突 | 优先左右对照；公式区域保留 PDF 原图 |

### 停止服务

- **一键模式：** 关闭应用浏览器标签（自动关机），或结束启动用的 PowerShell。  
- **手动模式：** 在各终端按 `Ctrl+C`。  
- 也可先 `Get-NetTCPConnection -LocalPort 8787,5173`，再按 PID 结束进程。

### `git pull` 之后如何更新

```powershell
cd "C:\Projects\Literature-Translator\apps\api"
.\.venv\Scripts\pip.exe install -r requirements.txt

cd "C:\Projects\Literature-Translator\apps\web"
npm install
```

然后按第 5 步重新启动。

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
- 论文助手为 **每文档一条线程**（当前界面已支持流式回复）  
- 本版本不做图理解 / 视觉问答，也不做向量 RAG  
- Word 导出为尽力而为的结构导出，非 PDF 像素级复刻  

---

## 仓库结构

```
Literature-Translator/
├── apps/
│   ├── api/          # FastAPI 后端
│   └── web/          # Vue 3 前端
├── scripts/          # start.ps1 与诊断脚本
├── picture/          # README 截图
├── docs/             # 设计说明与实现计划
└── data/             # 运行时数据库与 PDF（本地，gitignore）
```

---

## 参与贡献

欢迎改进解析质量、阅读体验、服务商兼容性与文档的 Issue / PR：

- [提交 Issue](https://github.com/chuqing-web/Literature-Translator/issues)
- [提交 Pull Request](https://github.com/chuqing-web/Literature-Translator/pulls)

请保持产品文案、代码与文档不出现本项目刻意回避的第三方产品中文品牌名。

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
