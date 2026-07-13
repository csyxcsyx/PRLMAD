# PRLMAD

PRLMAD（Personalized Resource Learning Multi-Agent Demo）是一个面向「操作系统」课程的个性化学习资源生成系统。项目使用本地教材知识库、RAG 检索和科大讯飞 Spark 大模型，围绕学习画像、资源生成、学习路径、智能辅导和效果评估构建一套多智能体学习工作流。

当前版本提供 FastAPI 后端、Jinja2 页面、TailwindCSS + Alpine.js 前端，以及 SQLite 本地持久化。

## 主要功能

- 结构化学习画像：通过固定问题和丰富选项收集专业、基础、目标、薄弱点、资源偏好、可用时间等维度，降低首次使用门槛。
- 本地知识库：支持 PDF/TXT/MD 导入，扫描版 PDF 可通过 OCR 提取文本。
- RAG 检索：基于 SQLite 的中文 n-gram/词频检索，回答和资源尽量附带教材来源。
- 多智能体资源生成：并行生成讲解文档、思维导图、题库、实操案例、PPT 大纲、任务清单等资源。
- 学习路径规划：根据画像和关注知识点生成 7 天以内的学习路径。
- 智能辅导：围绕教材片段进行问答，保留辅导记录。
- 学习效果评估：从资源、辅导、路径进度等活动生成多维度评估报告。

## 系统结构

```text
PRLMAD/
├── run.py                       # 命令行入口：train/status/serve
├── requirements.txt             # Python 依赖
├── .env.example                 # 环境变量模板
├── server/                      # FastAPI 服务层
│   ├── main.py                  # 应用入口、页面路由、路由注册
│   ├── dependencies.py          # 配置、知识库、会话库、模型客户端依赖
│   ├── models/schemas.py        # 请求模型
│   ├── routers/                 # API 模块
│   │   ├── chat.py              # 旧版对话画像 SSE
│   │   ├── generate.py          # 多智能体资源生成 SSE
│   │   ├── session.py           # 会话、画像、学习路径
│   │   ├── tutor.py             # RAG 辅导
│   │   ├── evaluate.py          # 学习效果评估
│   │   └── knowledge.py         # 知识库管理
│   └── utils/sse.py             # SSE 输出工具
├── src/prlmad/                  # 核心业务库
│   ├── agents.py                # AgentOrchestrator 和智能体提示词
│   ├── spark_client.py          # Spark API 客户端
│   ├── knowledge_base.py        # SQLite 知识库与检索
│   ├── session_store.py         # SQLite 会话、画像、资源、路径、评估存储
│   ├── pdf_loader.py            # PDF/TXT/MD 加载与 OCR
│   ├── text_splitter.py         # 文本清洗与切片
│   ├── training.py              # 批量导入知识库
│   └── safety.py                # 基础内容安全检查
├── templates/                   # Jinja2 页面
├── static/js/                   # 前端状态管理和页面脚本
├── knowledge/                   # 本地教材目录
└── data/                        # SQLite 运行数据
```

## 环境要求

- Python 3.12 或更高版本
- 有效的科大讯飞 Spark API Key
- Windows PowerShell、CMD、macOS/Linux shell 均可运行，下面示例以 PowerShell 为主

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

## 配置

复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`：

```text
SPARK_API_KEY=Bearer 你的APIpassword
SPARK_BASE_URL=https://spark-api-open.xf-yun.com/agent/v1/chat/completions
SPARK_MODEL=spark-x
SPARK_USER_ID=prlmad-demo-user
SPARK_ENABLE_WEB_SEARCH=false
SPARK_TRUST_ENV_PROXY=false
PRLMAD_DATA_DIR=data
PRLMAD_DB_PATH=data/knowledge.sqlite3
PRLMAD_KNOWLEDGE_DIR=knowledge
PRLMAD_OCR_MODE=auto
PRLMAD_OFFLINE_FALLBACK=false
```

常用配置说明：

| 变量 | 说明 |
| --- | --- |
| `SPARK_API_KEY` | Spark API 鉴权信息，可带或不带 `Bearer ` 前缀 |
| `SPARK_BASE_URL` | Spark Chat Completions 接口地址 |
| `SPARK_MODEL` | 模型名称 |
| `SPARK_TRUST_ENV_PROXY` | 是否读取系统代理，默认建议 `false`，避免本机无效代理导致 `WinError 10061` |
| `PRLMAD_DATA_DIR` | SQLite 数据目录 |
| `PRLMAD_DB_PATH` | 知识库 SQLite 文件路径 |
| `PRLMAD_KNOWLEDGE_DIR` | 教材文件目录 |
| `PRLMAD_OCR_MODE` | OCR 策略：`off`、`auto`、`on` |
| `PRLMAD_OFFLINE_FALLBACK` | Spark 不可用时是否启用本地演示兜底；真实联调建议 `false`，课堂演示可改为 `true` |

在启动 Web 服务前，可以先单独检查 Spark-X2-Flash 是否可用：

```powershell
python run.py check-spark --timeout 30
```

成功时会看到类似输出：

```text
Checking Spark-X2-Flash connection...
OK
Spark-X2-Flash 连接成功。
```

## 启动

手动启动 Web 服务：

```powershell
python run.py serve
```

指定端口：

```powershell
python run.py serve --host 127.0.0.1 --port 8000
```

关闭热重载：

```powershell
python run.py serve --no-reload
```

浏览器访问：

```text
http://127.0.0.1:8000
```

## 关闭服务

如果是在当前终端里启动的服务，直接按：

```text
Ctrl+C
```

如果忘记服务在哪个终端启动，可以在 PowerShell 中查看 8000 端口对应进程：

```powershell
Get-NetTCPConnection -LocalPort 8000 | Select-Object LocalAddress,LocalPort,State,OwningProcess
```

然后关闭对应 PID：

```powershell
Stop-Process -Id <OwningProcess>
```

例如：

```powershell
Stop-Process -Id 12345
```

## 导入知识库

把教材放入 `knowledge/` 目录，例如：

```text
knowledge/操作系统概念.pdf
```

批量导入：

```powershell
python -B run.py train --course 操作系统 --ocr-mode auto
```

命令行会显示进度条，包括 PDF 文本提取、OCR 页进度、文本切片和 SQLite 索引写入。训练默认是增量模式：

- 知识库里没有的教材会从第 1 页导入。
- 已完整导入的教材会直接跳过。
- 已部分导入的教材会从上一轮最大页码的下一页继续导入。

如果确认教材是文本型 PDF，比如当前《操作系统概念》可以正常提取文字，最快方式是关闭 OCR：

```powershell
python -B run.py train --course 操作系统 --ocr-mode off
```

扫描版 PDF 才需要 `--ocr-mode auto` 或 `--ocr-mode on`。整本扫描版教材首次 OCR 可能耗时较长，只要进度条仍在变化就表示程序仍在处理。

仅导入前 N 页，便于快速测试：

```powershell
python -B run.py train --course 操作系统 --max-pages 100
```

导入完整教材时不要传 `--max-pages`，否则知识库只会覆盖前 N 页。训练完成前，旧知识库记录仍会保留，因此另开终端运行 `status` 看到的页数不会立刻变化。

如果希望删除已有记录并从第 1 页重新构建，使用：

```powershell
python -B run.py train --course 操作系统 --ocr-mode off --force-rebuild
```

查看知识库状态：

```powershell
python -B run.py status
```

状态输出会显示 `pages=已导入起止页/PDF总页数`，例如 `pages=1-100/627 (partial)` 表示只导入了前 100 页。

也可以在网页的「知识库管理」页面中导入单个文件、训练整个目录或测试检索。网页训练使用流式进度，会显示当前页码、切片写入进度和最终结果。

## 使用流程

1. 打开首页后创建学习会话。
2. 在「学习画像」中按步骤选择学习背景、目标、基础、薄弱点、学习方式、实践状态和时间动机，保存学习画像。
3. 在「资源生成」中输入知识点并选择至少 5 种资源类型。
4. 在「学习路径」中生成或查看当前会话的路径。
5. 在「智能辅导」中围绕课程知识提问。
6. 在「效果评估」中生成综合学习报告。
7. 在「知识库管理」中检查文档数量、切片数量和检索效果。

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 服务健康检查 |
| `POST` | `/api/session` | 创建会话 |
| `GET` | `/api/sessions` | 会话列表 |
| `GET` | `/api/session/{session_id}` | 会话详情 |
| `PUT` | `/api/profile/{session_id}` | 更新学习画像 |
| `POST` | `/api/chat/stream` | 兼容旧版对话画像 SSE；当前页面优先使用 `PUT /api/profile/{session_id}` 保存结构化画像 |
| `GET` | `/api/chat/history/{session_id}` | 对话历史 |
| `POST` | `/api/generate/stream` | 资源生成 SSE |
| `GET` | `/api/generate/list/{session_id}` | 已生成资源 |
| `POST` | `/api/learning-path/generate` | 生成学习路径 |
| `GET` | `/api/learning-path/{session_id}` | 获取学习路径 |
| `POST` | `/api/tutor/stream` | 智能辅导 SSE |
| `GET` | `/api/tutor/logs/{session_id}` | 辅导记录 |
| `POST` | `/api/evaluate/comprehensive` | 综合评估 |
| `GET` | `/api/evaluate/history/{session_id}` | 评估历史 |
| `POST` | `/api/knowledge/train` | 批量训练知识库 |
| `POST` | `/api/knowledge/train/stream` | 批量训练知识库并返回 SSE 进度 |
| `POST` | `/api/knowledge/search` | 知识库检索 |
| `GET` | `/api/knowledge/status` | 知识库状态 |

## 常见问题

### 页面按钮没有反应

确认页面可以加载 CDN 资源，包括 TailwindCSS、Alpine.js、Marked 和 ECharts。若运行在离线环境，需要把这些前端库下载到本地并修改 `templates/base.html`。

### 流式输出中断或没有内容

优先检查 `.env` 中的 `SPARK_API_KEY` 是否有效。后端会通过 SSE 返回错误信息，浏览器开发者工具的 Network 面板可以看到 `/api/chat/stream` 或 `/api/generate/stream` 的事件流。

如果页面提示 `WinError 10061`，说明后端进程无法连接到 `SPARK_BASE_URL` 指向的服务。本项目调试时发现一个常见原因是系统环境变量中存在无效代理，例如 `HTTP_PROXY=http://127.0.0.1:9`，Python 请求会先连这个代理端口，结果被拒绝。默认建议：

```text
SPARK_TRUST_ENV_PROXY=false
PRLMAD_OFFLINE_FALLBACK=false
```

这样应用会直连 Spark，并且不会用本地兜底掩盖真实连接问题。

如果你确实需要代理访问外网，请确认代理服务正在运行，再改为：

```text
SPARK_TRUST_ENV_PROXY=true
```

若只是课堂演示，不想被外部 API 状态影响流程，可临时启用：

```text
PRLMAD_OFFLINE_FALLBACK=true
```

排查顺序建议：

```powershell
Resolve-DnsName spark-api-open.xf-yun.com
Test-NetConnection spark-api-open.xf-yun.com -Port 443
python run.py check-spark --timeout 30
```

### 知识库检索为空

先运行：

```powershell
python run.py status
```

如果文档数或切片数为 0，请重新执行 `python -B run.py train --course 操作系统 --ocr-mode auto`。扫描版 PDF 需要安装 OCR 相关依赖，并且首次导入可能比较慢。

网页端「知识库管理」会显示当前后端实际读取的 SQLite 路径、文件大小和教材目录。如果页面显示 0，但你确认之前已经导入过，优先检查：

- `.env` 中的 `PRLMAD_DB_PATH` 是否指向已经训练好的数据库。
- 修改 `.env` 后是否已经重启 `python run.py serve`。
- 页面提示的备用知识库文件是否才是你之前训练出来的文件。

为了避免误把空的默认库当成可用知识库，后端在 `data/knowledge.sqlite3` 为空且 `data/knowledge_active.sqlite3` 已有切片时，会自动读取 `knowledge_active.sqlite3`。知识库管理页会显示这一点。

如果状态显示 `partial`，说明只导入了部分页。常见原因是之前使用过 `--max-pages`。重新完整导入时使用：

```powershell
python -B run.py train --course 操作系统 --ocr-mode auto
```

不要添加 `--max-pages`。

### 编译或导入时出现 `PermissionError` 写入 `__pycache__`

某些 Windows 环境会限制 `.pyc` 写入。可以临时禁用字节码：

```powershell
$env:PYTHONDONTWRITEBYTECODE=1
python -B run.py status
```

## 开发建议

- 后端修改后先运行 `python -B -c "from server.main import app; print(app.title)"` 做导入烟测。
- 前端改动后启动 `python run.py serve --no-reload`，再检查浏览器控制台和 Network 面板。
- 浏览器运行时所需的 CSS、字体和前端库已提交到 `static/`，正常启动只需要 Python，不依赖 Node 或外网 CDN。
- 如需修改 Tailwind 类名或升级前端库，请使用 Node.js 20+ 和 pnpm，依次运行 `pnpm install --frozen-lockfile` 与 `pnpm run check`；构建后的静态文件需要一并提交。
- `pnpm run check:assets` 会阻止重新引入外部运行依赖、未经过安全渲染的 `x-html`，以及过大的首屏关键资源。
- `data/` 保存本地 SQLite 运行数据和已导入的知识库索引，默认不提交到 Git。
- `knowledge/` 保存本地教材文件，默认不提交到 Git，避免把大 PDF 上传到 GitHub。
- 协作者首次使用时需要自行准备教材文件，并通过 `python -B run.py train --course 操作系统 --ocr-mode off` 或网页端知识库管理页面构建本地知识库。
