# generateNovel3

多 Agent 中文小说生成器工程骨架。

当前仓库已具备：

- 项目目录初始化
- 项目元数据与进度状态落盘
- 总纲与细纲结构化 schema
- DashScope 兼容接口配置与 `.env` 加载
- Outline Agent 的轻量 ToT 总纲生成链路
- Detail Outline Agent 的章节分析与 `writer_packet` 生成链路
- Writer Agent 的章节正文生成与 Markdown 归档
- 写后自动 chunking / embedding / FAISS / BM25 入库
- RAG 检索工具与 CLI
- Human review tool，可挂起/恢复总纲、细纲、正文流程
- 章节 Markdown 归档
- 后续接入 Agent / RAG 的编排入口

## 当前目录

```text
src/
  app.py
  config.py
  orchestrator/
  schemas/
  storage/
```

## 快速开始

安装依赖后可使用 CLI：

```bash
generate-novel init-project demo_project --title "示例小说"
generate-novel show-state demo_project
generate-novel generate-outline demo_project --brief "一个关于宗门衰落与重建的长篇仙侠"
generate-novel show-outline demo_project
generate-novel generate-detail-outline demo_project
generate-novel show-detail-outline demo_project
generate-novel write-chapter demo_project
generate-novel show-chapter demo_project --chapter-id 1
generate-novel ingest-chapter demo_project --chapter-id 1
generate-novel rag-search demo_project "莫长老"
generate-novel write-chapter demo_project --chapter-id 1 --require-review
generate-novel list-reviews demo_project --status pending
generate-novel resolve-review demo_project --review-id review_0001 --decision approve
```

也可以直接运行：

```bash
python -m src.app init-project demo_project --title "示例小说"
```

## 当前范围

本次已接入总纲阶段，尚未接入：

- 人工介入 tool 的交互式后端

注意：

- 当前 human tool 已支持本地 review 文件、待处理队列和 CLI 解决流程
- 还没有接 Web UI 或消息通知

## RAG 默认配置

项目默认使用：

```env
EMBEDDING_MODEL=shibing624/text2vec-base-chinese
CHUNK_SIZE=500
CHUNK_OVERLAP=100
DENSE_WEIGHT=0.65
SPARSE_WEIGHT=0.35
```

当前实现采用“每次 ingest 重新构建当前项目索引”的 MVP 策略，优先保证重写章节时索引不会脏。

这些模块的接口与数据边界已在 [design.md](design.md) 中确认，并在本轮骨架代码里预留了 schema 与 workflow 入口。

## 环境变量

项目会自动读取仓库根目录下的 `.env`：

```env
DASHSCOPE_API_KEY=your_key
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OUTLINE_MODEL=qwen3.6-plus
DETAIL_OUTLINE_MODEL=qwen3.6-plus
WRITER_MODEL=qwen3.6-plus
```
