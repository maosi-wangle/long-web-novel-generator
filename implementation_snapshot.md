# 当前实现快照

本文档用于记录 `generateNovel3` 当前已经实现的代码逻辑、接口、状态流转和工程约定，供后续继续开发时快速恢复上下文，避免重复检索代码。

## 1. 当前目标完成度

已完成的主链路：

1. 项目初始化
2. 全局大纲生成 `OutlineAgent`
3. 章节细纲生成 `DetailOutlineAgent`
4. 正文生成 `WriterAgent`
5. 章节 Markdown 归档
6. 写后自动 RAG 入库
7. 项目状态推进

尚未完成：

1. `request_human_intervention` tool 的实际调用后端
2. 更细粒度的 agent tool 权限控制
3. 自动循环 runner

## 2. 当前主流程

当前 CLI 驱动的标准流程如下：

1. `init-project`
2. `generate-outline`
3. `generate-detail-outline`
4. `write-chapter`
5. 回到 `generate-detail-outline` 进入下一章

注意：

- 目前是显式命令驱动，不是一个自动循环 runner。
- `write-chapter` 完成后会自动归档 Markdown，并把状态推进到“下一章待细纲”。
- `write-chapter` 完成后还会自动执行：
  - 正文抽取
  - 500 字切块
  - 100 字 overlap
  - embedding
  - FAISS 重建
  - BM25 重建
- 当前索引策略是“按当前项目全量 chunk 重建”，优先保证章节重写后的索引一致性。
- `DetailOutlineAgent` 现在会在生成细纲前自动做一次历史正文检索。
- `WriterAgent` 现在也会在写正文前自动做一次历史正文检索。

## 3. 关键文件职责

### 3.1 入口与配置

- `src/app.py`
  - Typer CLI 入口
  - 暴露所有命令
- `src/config.py`
  - 项目路径约定
  - `.env` 加载
  - DashScope 兼容接口配置读取
- `src/llm/compatible_client.py`
  - OpenAI-compatible `chat/completions` 调用
  - 支持普通文本和 JSON 返回
  - 当前直接用 `urllib.request`

### 3.2 编排层

- `src/orchestrator/state.py`
  - `ProjectState`
  - `WorkflowStatus`
  - `GenerationStage`
- `src/orchestrator/workflow.py`
  - 项目加载与保存
  - 大纲/细纲/章节归档状态推进
  - 默认章节选择逻辑

### 3.3 Agent 层

- `src/agents/outline_agent.py`
  - 轻量 ToT
  - 先候选方向，再评分，再最终总纲
- `src/agents/detail_outline_agent.py`
  - 基于当前章节定位和当前进度生成细纲
  - 产出 `internal_reasoning_package` 和 `writer_packet`
- `src/agents/writer_agent.py`
  - 仅根据局部写作包生成正文
  - 不接触完整总纲

### 3.4 Schema 与存储

- `src/schemas/outline.py`
  - 总纲相关结构
- `src/schemas/chapter.py`
  - 细纲、局部写作包、章节产物结构
- `src/schemas/memory.py`
  - chunk 元数据
  - ingest 结果结构
- `src/schemas/project.py`
  - 项目元信息
- `src/storage/state_store.py`
  - `project.json` / `outline.json` / `progress.json` / `detail_outlines/*.json`
- `src/storage/markdown_store.py`
  - 章节 Markdown 落盘
  - 最近章节文本读取

### 3.5 Memory 与 Tool

- `src/memory/chunker.py`
  - 500 字切块
  - 100 字 overlap
  - chunk 元信息生成
- `src/memory/embedding.py`
  - `sentence-transformers`
  - 默认模型 `shibing624/text2vec-base-chinese`
- `src/memory/faiss_store.py`
  - 写入 / 读取 FAISS 索引
- `src/memory/bm25_store.py`
  - 写入 BM25 文档集
  - 查询时动态构建 `BM25Okapi`
- `src/memory/hybrid_retriever.py`
  - dense / sparse / hybrid 检索融合
- `src/memory/ingest.py`
  - 从归档 Markdown 提取正文
  - 统一重建项目索引
- `src/tools/rag_tool.py`
  - 对外暴露 ingest / search 工具接口

## 4. 项目目录约定

单个项目当前落盘格式：

```text
data/projects/{project_id}/
  project.json
  outline.json
  progress.json
  chapters/
    0001.md
  detail_outlines/
    0001.json
  rag/
    faiss/
    bm25/
    meta.jsonl
```

注意：

- `rag/` 目录现在已经被真正使用，包含：
  - `rag/meta.jsonl`
  - `rag/faiss/index.faiss`
  - `rag/faiss/mapping.json`
  - `rag/bm25/documents.json`

## 5. 当前状态机逻辑

定义位置：

- `src/orchestrator/state.py`

主要状态值：

- `initialized`
- `outline_ready`
- `detail_outline_ready`
- `drafting`
- `chapter_archived`
- `waiting_human_review`
- `completed`
- `failed`

当前实际使用的推进方式：

1. 初始化项目后：
   - `status = initialized`
   - `current_stage = outline`
2. 保存总纲后：
   - `status = outline_ready`
   - `current_stage = detail_outline`
3. 保存细纲后：
   - `status = detail_outline_ready`
   - `current_stage = writer`
4. 写完并归档章节后：
   - 如果不是最后一章：
     - `status = outline_ready`
     - `current_stage = detail_outline`
   - 如果已经是最后一章：
     - `status = completed`
     - `current_stage = archive`

补充说明：

- 这里的 `outline_ready` 在章节归档后表示“下一章可继续从大纲进入细纲阶段”，不是重新生成总纲。
- 当前 `drafting` / `chapter_archived` 状态没有实际进入主流程，后续可以根据需要细化。

## 6. 当前 CLI 接口

定义位置：

- `src/app.py`

当前命令：

### 6.1 项目与状态

- `python -m src.app init-project <project_id> --title ...`
- `python -m src.app show-state <project_id>`

### 6.2 总纲

- `python -m src.app generate-outline <project_id> --brief "..."`
- `python -m src.app show-outline <project_id>`

### 6.3 细纲

- `python -m src.app generate-detail-outline <project_id> [--chapter-id N] [--brief "..."]`
- `python -m src.app show-detail-outline <project_id> [--chapter-id N]`

### 6.4 正文

- `python -m src.app write-chapter <project_id> [--chapter-id N] [--brief "..."]`
- `python -m src.app show-chapter <project_id> --chapter-id N`

### 6.5 RAG

- `python -m src.app ingest-chapter <project_id> --chapter-id N`
- `python -m src.app rebuild-rag <project_id>`
- `python -m src.app rag-search <project_id> "<query>"`

默认章节选择规则：

- 如果 `current_chapter_index > last_completed_chapter`，优先继续当前待写章节
- 否则默认选择 `last_completed_chapter + 1`

## 7. Agent 逻辑说明

### 7.1 OutlineAgent

定义位置：

- `src/agents/outline_agent.py`

当前实现逻辑：

1. `_generate_candidates()`
   - 生成 3 到 5 个故事方向候选
2. `_evaluate_candidates()`
   - 对候选进行评分
   - 已确认 `extra_brief` 会传入此阶段
3. `_finalize_outline()`
   - 生成最终 `NovelOutline`
4. `_normalize_outline()`
   - 强制将全书 `chapter_id` 改成全局连续编号

当前设计要点：

- 使用轻量 ToT，而不是完整树搜索
- 模型返回的 `discarded_directions` 不可信，当前直接在代码中覆盖为评分次优方案

### 7.2 DetailOutlineAgent

定义位置：

- `src/agents/detail_outline_agent.py`

当前实现逻辑：

1. `_resolve_target_chapter()`
   - 按项目状态或显式 `chapter_id` 选择当前章
2. `_build_chapter_context()`
   - 提取：
     - 当前 act
     - 当前章
     - 上一章
     - 下一章
     - 最近已写章节局部文本
     - 全局伏笔
     - 全局约束
     - 核心角色
3. `_analyze_chapter()`
   - 生成章节职责分析
4. `_draft_detail_outline()`
   - 生成 `DetailOutline`
5. `_normalize_detail_outline()`
   - 重新对齐：
     - `chapter_id`
     - `title`
     - `chapter_goal`
     - `scene_id`

当前输出边界：

- `internal_reasoning_package`
  - 允许带全局对齐信息
- `writer_packet`
  - 只保留局部章节信息
  - 是后续 Writer 的唯一主输入

RAG 接入规则：

- Detail 阶段的检索上界是 `min(last_completed_chapter, target_chapter_id - 1)`
- 也就是永远只允许检索当前章之前的历史正文
- 如果存在真实 RAG 命中，`writer_packet.retrieved_context` 会被真实命中覆盖，不信任模型自由编写

### 7.3 WriterAgent

定义位置：

- `src/agents/writer_agent.py`

当前实现逻辑：

1. 接收：
   - `project`
   - `detail_outline`
   - `extra_brief`
2. 实际发送给模型的内容只包含：
   - 项目风格层信息
   - `writer_packet`
   - `ending_hook`
   - `user_constraints`
3. 返回结构：
   - `ChapterArtifact`
4. `_normalize_artifact()`
   - 强制回填当前章号和标题
   - 补全 `referenced_chunks`

当前最重要的边界：

- Writer 不读取总纲
- Writer 不直接拿 `internal_reasoning_package`
- Writer 只能用 `writer_packet`

补充：

- 当前 `write-chapter` 命令在 `archive_chapter()` 之后会立即调用 `RagTool(project_id).ingest_archived_chapter(chapter_id)`。
- 这就是当前“写完即入库”的实际落点。
- Writer 在真正发请求给模型前，还会再执行一次 history-only 的 `rag_search`
- Writer 的检索范围固定为 `chapter_scope=(1, chapter_id - 1)`

### 7.4 RagTool / MemoryIngestor / HybridRetriever

定义位置：

- `src/tools/rag_tool.py`
- `src/memory/ingest.py`
- `src/memory/hybrid_retriever.py`

当前实现逻辑：

1. `MemoryIngestor.ingest_archived_chapter()`
   - 读取归档章节 Markdown
   - 解析 `## 正文`
   - 按 500 / 100 切块
   - 用 `shibing624/text2vec-base-chinese` 生成 embedding
   - 重写 `meta.jsonl`
   - 重建 FAISS
   - 重建 BM25 文档集
2. `RagTool.search()`
   - 接收 `RagSearchRequest`
   - 调用 `HybridRetriever.search()`
3. `HybridRetriever.search()`
   - dense：FAISS 内积检索
   - sparse：BM25
   - hybrid：按 `0.65 * dense + 0.35 * sparse` 融合

当前注意点：

- 为了支持重写同一章后的索引覆盖，当前 ingest 采用“全量重建”策略，而不是增量 append。
- 当前 `entity_filter` 基于 chunk 内抽取出的简单词项，不是专门 NER。

## 8. 核心 Schema 约定

### 8.1 NovelOutline

定义位置：

- `src/schemas/outline.py`

关键字段：

- `title`
- `genre`
- `tone`
- `premise`
- `world_setting`
- `characters`
- `acts`
- `foreshadowing`
- `constraints`
- `discarded_directions`

### 8.2 DetailOutline

定义位置：

- `src/schemas/chapter.py`

关键字段：

- `chapter_id`
- `title`
- `chapter_goal`
- `internal_reasoning_package`
- `writer_packet`
- `ending_hook`
- `user_constraints`

### 8.3 WriterPacket

定义位置：

- `src/schemas/chapter.py`

关键字段：

- `chapter_id`
- `chapter_title`
- `chapter_goal`
- `scene_briefs`
- `style_rules`
- `continuity_notes`
- `forbidden_reveals`
- `retrieved_context`

### 8.4 ChapterArtifact

定义位置：

- `src/schemas/chapter.py`

关键字段：

- `chapter_id`
- `title`
- `markdown_body`
- `summary`
- `new_facts`
- `foreshadow_candidates`
- `referenced_chunks`

## 9. 环境变量与模型配置

当前使用：

- DashScope OpenAI-compatible 接口

环境变量定义位置：

- `.env`
- `src/config.py`

当前字段：

```env
DASHSCOPE_API_KEY=...
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OUTLINE_MODEL=qwen3.5-flash
DETAIL_OUTLINE_MODEL=qwen3.5-flash
WRITER_MODEL=qwen3.5-flash
EMBEDDING_MODEL=shibing624/text2vec-base-chinese
CHUNK_SIZE=500
CHUNK_OVERLAP=100
DENSE_WEIGHT=0.65
SPARSE_WEIGHT=0.35
```

读取函数：

- `load_local_env()`
- `get_llm_settings()`

## 10. 已有示例产物

当前仓库内已有实际跑通样例：

- `data/projects/outline_demo/project.json`
- `data/projects/outline_demo/progress.json`
- `data/projects/outline_demo/outline.json`
- `data/projects/outline_demo/detail_outlines/0001.json`
- `data/projects/outline_demo/chapters/0001.md`
- `data/projects/outline_demo/rag/meta.jsonl`
- `data/projects/outline_demo/rag/faiss/index.faiss`
- `data/projects/outline_demo/rag/bm25/documents.json`

说明：

- 该项目已经完成：
  - 总纲生成
  - 第 1 章细纲生成
  - 第 1 章正文生成与归档
  - 第 1 章 RAG 入库
  - `rag-search` 检索验证

当前 `outline_demo` 的状态大意：

- 第 1 章已完成
- 当前系统准备进入下一章细纲生成

## 11. 当前已知注意点

### 11.1 PowerShell 输出可能出现中文乱码

在当前环境里，用 PowerShell 直接 `Get-Content` 某些 Python 文件时，中文 prompt 文本可能显示为乱码，但文件本身是正常 UTF-8 落盘的。

影响：

- 终端查看源码时可能看起来乱码
- 实际运行时模型调用和 Markdown 文件是正常的

### 11.2 Markdown 模板已正常输出中文

当前实际归档出的章节 Markdown 已经是正常中文内容，说明最终落盘逻辑没有被乱码破坏。

### 11.3 状态命名后续可以细化

当前 `archive_chapter()` 写完非最后一章后，状态直接回到：

- `status = outline_ready`
- `current_stage = detail_outline`

这在语义上够用，但将来可能需要更精确的状态名，例如：

- `ready_for_next_detail_outline`

### 11.4 目前没有自动重试 / JSON 修复循环

当前 Agent 都依赖模型一次性输出合法 JSON。

虽然后处理有少量 normalize，但还没有实现：

- JSON 修复重试
- 字段缺失自动补写
- schema 校验失败后的 fallback

这属于后续可增强项。

### 11.5 RAG 当前是 CLI / tool 可用，但还没被 Agent 真正调用

这部分已经完成：

- `DetailOutlineAgent` 会在细纲阶段主动调用 `rag_search`
- `WriterAgent` 会在正文阶段主动调用 `rag_search`

当前剩余问题不是“能否检索”，而是：

- 后续是否要做成更显式的 tool-call 日志
- 是否要把检索 query 和命中结果持久化成调试记录

## 12. 下一步开发建议

最推荐的下一步是继续把 tool 层补完整：

1. 补 `tools/human_tool.py`
2. 做 agent tool 权限控制
3. 记录每次检索 query / hits 作为调试日志
4. 让 Detail / Writer 在必要时做多轮检索，而不是固定一次

之后再接：

1. 自动循环 runner
2. JSON 修复与重试
3. 更细的状态机

## 13. 如果后续上下文丢失，优先看哪里

建议按这个顺序恢复现场：

1. 本文件 `implementation_snapshot.md`
2. `design.md`
3. `src/app.py`
4. `src/orchestrator/workflow.py`
5. `src/agents/outline_agent.py`
6. `src/agents/detail_outline_agent.py`
7. `src/agents/writer_agent.py`
8. `src/memory/*`
9. `src/tools/rag_tool.py`
10. `data/projects/outline_demo/`

如果只想快速继续开发，不想重新读全仓库：

1. 先看本文件第 3、5、6、7、12 节
2. 再直接实现 `memory/*` 和 `tools/rag_tool.py`
