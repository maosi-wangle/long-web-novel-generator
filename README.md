# generateNovel

一个面向长篇网文辅助创作的多智能体原型项目。当前重点是人机协同工作台：

- 多小说管理
- 章节级 plan / review / draft 流程
- 人工审核闸门
- 章节连续性衔接
- 本地 JSON/JSONL 运行期存储

## 当前技术形态

- 后端：FastAPI
- 工作流编排：LangGraph 风格节点编排
- 前端工作台：原生 HTML + CSS + JavaScript
- 本地存储：`backend/runtime/*.json` / `*.jsonl`

当前工作台入口：

- `/workbench`
- `/docs`

## 新手先看

如果你是第一次跑这个项目，最重要的是先做这 4 步：

1. 安装依赖
2. 创建并填写根目录 `.env`
3. 启动 FastAPI
4. 打开 `/workbench`

可以直接按下面的顺序照做。

## 5 分钟跑起来

### 第 1 步：创建虚拟环境并安装依赖

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

### 第 2 步：复制 `.env.example` 为 `.env`

项目运行时会自动读取根目录 `.env`。  
如果没有 `.env`，很多配置不会生效。

在 PowerShell 中执行：

```powershell
Copy-Item .env.example .env
```

然后打开 `.env`，至少确认这些配置：

```env
API_HOST=127.0.0.1
API_PORT=9005
GRAPH_STORE_BACKEND=jsonl
USE_MOCK_LLM=1
```

如果你只是想先把 workbench 跑起来，推荐一开始先用：

```env
USE_MOCK_LLM=1
```

这样 draft 阶段会直接返回本地 mock 文本，不需要真实模型 API。

如果你要使用真实模型，再把 `.env` 改成：

```env
USE_MOCK_LLM=0
LLM_API_KEY=你的key
LLM_BASE_URL=https://你的接口地址/v1
```

### 第 3 步：启动服务

```powershell
python backend/src/novel_assist/cli/run_api.py
```

### 第 4 步：打开工作台

浏览器访问：

- `http://127.0.0.1:9005/workbench`
- `http://127.0.0.1:9005/docs`

如果你改了 `.env` 里的 `API_PORT`，这里的端口也要跟着改。

## 环境要求

- Python 3.11
- Windows PowerShell 或兼容终端

## 安装

建议先创建虚拟环境，再安装依赖：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

## 配置

项目统一从根目录 `.env` 读取运行配置。

可以先参考 `.env.example`，再根据你自己的环境调整 `.env`。

对初学者来说，最重要的结论是：

- `.env.example` 只是模板
- 真正运行时读的是 `.env`
- 你改配置，优先改 `.env`
- `run_api.py` 启动时会自动加载 `.env`

当前常用配置分三类。

### 1. API / Workbench

```env
API_HOST=127.0.0.1
API_PORT=9005
GRAPH_STORE_BACKEND=jsonl
```

说明：

- `API_HOST` / `API_PORT`：FastAPI 服务监听地址
- `GRAPH_STORE_BACKEND`：默认建议 `jsonl`

可选本地运行期文件路径：

```env
# REVIEW_AUDIT_PATH=backend/runtime/review_audit.jsonl
# CHAPTER_STATE_PATH=backend/runtime/chapter_state.json
# NOVEL_STATE_PATH=backend/runtime/novel_state.json
```

### 2. LLM

```env
USE_MOCK_LLM=0
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://api.your-provider.com/v1
LLM_MODEL_NAME=qwen3-max-preview
LLM_TEMPERATURE=0.9
LLM_TIMEOUT_SECONDS=90
LLM_MAX_RETRIES=2
```

说明：

- `USE_MOCK_LLM=1`：使用本地 mock 文本，不真正调用模型
- `USE_MOCK_LLM=0`：使用真实模型 API
- `LLM_API_KEY` / `LLM_BASE_URL`：真实 API 模式必填
- `LLM_MODEL_NAME` / `LLM_TEMPERATURE`：写作模型配置

### 3. 调试项

```env
SHOW_DRAFT_SYSTEM_PROMPT=0
SHOW_DRAFT_PROMPT=0
MAX_REWRITES=3
AUTO_APPROVE_REVIEW=0
CRITIC_FORCE_FAIL=0
```

说明：

- `SHOW_DRAFT_SYSTEM_PROMPT` / `SHOW_DRAFT_PROMPT`：打印 prompt 便于调试
- `MAX_REWRITES`：Critic 驳回后的最大重写次数
- `AUTO_APPROVE_REVIEW`：仅调试用，不建议在 workbench 流程中依赖
- `CRITIC_FORCE_FAIL`：强制制造 Critic 失败场景

## 启动方式

推荐使用下面这个启动入口：

```powershell
python backend/src/novel_assist/cli/run_api.py
```

这个脚本会先加载根目录 `.env`，再启动 API 服务。

启动后访问：

- `http://127.0.0.1:9005/workbench`
- `http://127.0.0.1:9005/docs`

如果你修改了 `.env` 里的端口，请按实际端口访问。

## Mock / Real 模式怎么切

只改 `.env` 里的 `USE_MOCK_LLM` 即可：

```env
USE_MOCK_LLM=1
```

表示 draft 阶段走本地 mock。

```env
USE_MOCK_LLM=0
```

表示 draft 阶段调用真实模型 API。

一个非常重要的细节：

- `USE_MOCK_LLM` 会在你点击 `Generate Plan` 时写进章节 state
- 所以切换 mock / real 之后，想让某个章节使用新模式，最好重新对该章节执行一次 `Generate Plan`

如果你是第一次使用，建议：

1. 先用 `USE_MOCK_LLM=1` 跑通整条 workbench 流程
2. 确认页面、章节管理、审核流程都正常
3. 再切到 `USE_MOCK_LLM=0` 测真实 API

## Workbench 使用流程

### 0. 创建小说

在 `Novel Shelf` 填写：

- `Novel ID`
- `Novel Title`

然后点击 `创建小说`。

### 1. 准备章节

两种方式：

- 直接手动填写 `Chapter ID / Chapter Number / Chapter Title`
- 点击 `准备下一章`，让页面按当前小说最后一章自动生成下一章编号

### 2. Generate Plan

填写：

- `Chapter Agenda`
- `World Rules`
- `Future Waypoints`
- `Guidance From Future`

然后点击 `Generate Plan`。

这一步会：

- 生成待审细纲
- 生成 RAG 召回摘要与证据
- 把章节状态落盘

如果当前章节号大于 1，后端还会尝试自动继承上一章的连续性字段，例如：

- `previous_chapter_ending`
- `world_rules`
- `future_waypoints`
- `guidance_from_future`

### 3. Fetch Review Task

点击 `Fetch Review Task`，把审核相关字段与证据同步到页面。

### 4. Submit Review

设置：

- `Review Decision`
- `Review Notes`
- 可选的 `Approved Agenda`
- 可选的 `Approved Recall Summary`

然后点击 `Submit Review`。

### 5. Generate Draft

只有当 `agenda_review_status === "approved"` 时，页面才允许点击 `Generate Draft`。

生成后会在右侧看到：

- `Draft Preview`
- `Critic Feedback`

## 运行期文件

默认会写到：

- `backend/runtime/chapter_state.json`
- `backend/runtime/novel_state.json`
- `backend/runtime/review_audit.jsonl`

这些属于本地运行期状态，不建议提交到 Git。

## 测试

目前最直接的一组回归测试：

```powershell
python backend/tests/integration/test_stage4_fastapi.py
```

它会覆盖：

- workbench 页面可访问
- plan / review / draft 闭环
- 多小说与多章节管理
- 空小说创建
- 续章上下文继承
- 统一错误返回

## 主要目录

```text
backend/
  src/novel_assist/
    api/        FastAPI 路由与 workbench
    nodes/      章节规划、召回、审核、写作、质检节点
    stores/     JSONL / Neo4j 存储抽象
    state/      全局状态契约
  tests/        集成测试与单测
docs/           设计说明、前端手册、代码阅读清单
```
