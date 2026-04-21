# 小说生成器架构设计

## 1. 目标

构建一个面向长篇小说生成的多 Agent 系统，满足以下核心要求：

1. 能根据用户输入主题、风格、设定等信息生成全局大纲。
2. 在生成正文时，能够动态根据当前进度生成当前章节/片段的细纲。
3. 正文写作 Agent 只看到局部信息，不掌握完整全局规划。
4. 每篇正文写完后自动归档为 Markdown，并写入检索系统。
5. 提供基于 FAISS + BM25 的混合检索能力，供后续创作阶段调用。
6. RAG 检索与人工介入都以 tool 的形式暴露给 Agent 编排层。

## 2. 设计原则

### 2.1 上帝视角隔离

- `Outline Agent` 和 `Detail Outline Agent` 知道全局规划。
- `Writer Agent` 不知道完整全局剧情，只知道当前要写的局部目标。
- 长期一致性通过 “细纲 Agent + RAG 检索” 间接维持，而不是让正文模型直接看到全部内容。

### 2.2 分层生成

- 第一层：总纲规划
- 第二层：细纲展开
- 第三层：正文写作
- 第四层：归档与记忆写入

### 2.3 记忆外置

- 已生成正文不依赖模型隐式记忆，而是落盘并进入可检索知识库。
- 后续章节需要历史上下文时，通过 RAG tool 主动召回。

### 2.4 人在回路

- 在关键节点允许人工查看、修改、批准或重写。
- 人工介入不是旁路逻辑，而是正式 tool。

## 3. 系统总览

建议采用 Python 实现，整体分为 6 层：

1. `orchestrator`：任务编排与状态机
2. `agents`：总纲、细纲、正文三个 Agent
3. `tools`：RAG、人工介入、归档等工具
4. `memory`：FAISS、BM25、chunking、索引维护
5. `storage`：Markdown 文件、JSON 状态、配置文件
6. `llm adapters`：Qwen3.5-Flash、Embedding 模型适配

推荐目录结构如下：

```text
generateNovel3/
  design.md
  README.md
  pyproject.toml
  src/
    app.py
    config.py
    orchestrator/
      engine.py
      state.py
      workflow.py
    agents/
      outline_agent.py
      detail_outline_agent.py
      writer_agent.py
      prompts/
        outline.md
        detail_outline.md
        writer.md
    tools/
      rag_tool.py
      human_tool.py
      archive_tool.py
    memory/
      chunker.py
      embedding.py
      faiss_store.py
      bm25_store.py
      hybrid_retriever.py
      ingest.py
    storage/
      markdown_store.py
      state_store.py
    schemas/
      outline.py
      chapter.py
      scene.py
      tool_io.py
  data/
    projects/
      {project_id}/
        project.json
        outline.json
        progress.json
        chapters/
          0001.md
          0002.md
        detail_outlines/
          0001.json
          0002.json
        rag/
          faiss/
          bm25/
          meta.jsonl
```

## 4. 核心角色设计

## 4.1 Outline Agent

职责：

- 接收用户输入，或在无输入时做默认创意扩展。
- 使用 ToT（Tree of Thoughts）生成多个可能的大纲方向。
- 对候选方向进行自评估、比较与筛选。
- 产出稳定、结构化的全局大纲。

输入：

- 用户需求
- 风格偏好
- 字数规模
- 题材标签
- 可选世界观/角色设定

输出：

- 作品级别元信息
- 故事主线
- 角色表
- 世界设定
- 卷/篇/章级大纲
- 关键伏笔与回收点
- 约束规则

建议输出结构：

```json
{
  "title": "示例小说",
  "genre": ["仙侠", "成长"],
  "tone": "热血中带克制",
  "premise": "故事一句话简介",
  "world_setting": {},
  "characters": [],
  "acts": [],
  "foreshadowing": [],
  "constraints": []
}
```

### ToT 在本项目中的落地方式

不是无限制树搜索，而是“轻量化 ToT”：

1. 先生成 3 到 5 个高层故事方向。
2. 每个方向展开成简版总纲。
3. 用统一 rubric 打分：
   - 可持续连载性
   - 冲突强度
   - 人物成长空间
   - 题材贴合度
   - 伏笔回收潜力
4. 选择最优方案，必要时融合次优方案优点。
5. 输出最终大纲与被舍弃方案摘要，供调试或人工审阅。

## 4.2 Detail Outline Agent

职责：

- 根据当前项目进度，从全局大纲中定位当前应写位置。
- 使用 CoT 分析当前章节的目标、冲突、信息披露和情感节奏。
- 结合已写内容和召回上下文，生成当前章节/场景细纲。
- 负责把全局信息“翻译”为 Writer Agent 能使用的局部写作任务。

输入：

- 全局大纲
- 当前进度状态
- 已完成章节摘要
- RAG 检索结果
- 用户追加指令

输出：

- 当前章节目标
- 本章场景列表
- 每个场景的出场角色
- 冲突推进点
- 必须提及的信息
- 不能写出的信息
- 结尾钩子
- 给 Writer Agent 的局部写作包

建议输出拆成两层：

1. `internal_reasoning_package`
   - 仅供系统使用
   - 包含全局对齐、伏笔映射、长期节奏判断
2. `writer_packet`
   - 仅供 Writer Agent
   - 不暴露完整总纲
   - 只包含当前正文需要的信息

### CoT 在本项目中的落地方式

CoT 不直接暴露给最终正文模型，而是在细纲层内部使用，用来完成：

- 当前进度判断
- 章节目标拆解
- 场景顺序安排
- 信息显露控制
- 与前文一致性检查

## 4.3 Writer Agent

职责：

- 根据 `writer_packet` 直接生成正文。
- 不接触完整大纲，不持有全局真相。
- 仅在必要时通过工具获取局部历史记忆。

模型要求：

- 使用 `Qwen3.5-Flash`

输入：

- 当前章节基础信息
- 当前场景细纲
- 写作风格要求
- 必须保留的角色口吻/世界规则
- 可选 RAG 检索结果摘要

输出：

- 章节 Markdown 正文
- 章节摘要
- 新增事实清单
- 可回收伏笔候选

Writer Agent 的关键约束：

1. 不能看到完整全局大纲。
2. 不能自己决定长期主线改写。
3. 如遇信息缺失，优先调用 tool，而不是自行脑补重大设定。

## 5. 状态流转

建议采用显式状态机而不是隐式脚本串联。

核心状态：

```json
{
  "project_id": "demo_project",
  "status": "drafting",
  "current_act_index": 0,
  "current_chapter_index": 3,
  "current_scene_index": 0,
  "outline_version": 1,
  "detail_outline_version": 4,
  "last_completed_chapter": 2,
  "pending_human_review": false
}
```

主流程：

1. 初始化项目
2. 生成总纲
3. 人工审阅总纲（可选）
4. 基于当前进度生成细纲
5. 为 Writer Agent 组装局部写作包
6. 写出正文
7. 归档 Markdown
8. 对正文做 chunking 并写入向量/BM25 索引
9. 更新项目进度
10. 进入下一章节循环

## 6. 数据边界与上下文隔离

这是本项目最重要的设计点之一。

### 6.1 Agent 可见性矩阵

| 数据 | Outline Agent | Detail Outline Agent | Writer Agent |
|---|---|---|---|
| 用户需求 | 可见 | 可见 | 仅局部映射后可见 |
| 全局大纲 | 可见 | 可见 | 不可见 |
| 当前细纲 | 不需要 | 可见 | 可见 |
| 已写正文全文 | 可见（可选） | 可见（通过摘要/RAG） | 不直接可见 |
| RAG 检索结果 | 可选 | 可见 | 可见，但仅局部 |
| 长期伏笔计划 | 可见 | 可见 | 不可见 |

### 6.2 Writer Packet 设计

`writer_packet` 是传给正文模型的唯一主输入载体，建议包含：

```json
{
  "chapter_id": 12,
  "chapter_title": "夜渡寒江",
  "chapter_goal": "主角首次确认内奸存在",
  "scene_briefs": [
    {
      "scene_id": 1,
      "location": "渡口",
      "characters": ["林澈", "船夫"],
      "objective": "通过对话埋下异常线索",
      "must_include": ["船票上的旧印章", "风雨将至"],
      "avoid": ["直接点明内奸身份"]
    }
  ],
  "style_rules": [],
  "continuity_notes": [],
  "retrieved_context": []
}
```

## 7. RAG 设计

## 7.1 写入时机

每篇正文完成后立即写入 RAG。

写入链路：

1. 章节正文保存为 `.md`
2. 对正文做标准化清洗
3. 按 500 字 chunk
4. 使用重叠切片
5. 计算 embedding
6. 写入 FAISS
7. 同步写入 BM25
8. 保存 chunk 元信息

## 7.2 Chunk 策略

需求中已指定单 chunk 500 字，建议：

- `chunk_size = 500` 中文字符
- `chunk_overlap = 100` 中文字符

说明：

- 500 字足够保留段落连续性。
- 100 字重叠可以减少场景切断带来的召回断裂。
- 若章节中有标题或分节，优先按分节边界切，再回退到字符切片。

Chunk 元数据建议：

```json
{
  "chunk_id": "0003_02",
  "project_id": "demo_project",
  "chapter_id": 3,
  "scene_hint": "渡口对话",
  "source_file": "chapters/0003.md",
  "char_start": 500,
  "char_end": 1000,
  "summary": "林澈在渡口察觉异常印章",
  "entities": ["林澈", "船夫", "旧印章"],
  "facts": [
    "船票使用旧制印章",
    "林澈对船夫产生怀疑"
  ]
}
```

## 7.3 Embedding

指定模型：

- `shibing624/text2vec-base-chinese`

建议封装为独立服务适配层：

- 统一对外接口：`embed_texts(texts: list[str]) -> list[list[float]]`
- 后续若模型替换，只改适配器不改上层

## 7.4 混合检索

采用 Hybrid Retrieval：

- Dense：FAISS
- Sparse：BM25

融合策略建议：

1. 分别取 FAISS top-k 与 BM25 top-k
2. 做去重
3. 使用加权分数融合
4. 返回给调用方

推荐初始公式：

```text
hybrid_score = 0.65 * dense_score + 0.35 * sparse_score
```

后续可调参数：

- 回忆剧情时提高 dense 权重
- 精确查找专有名词时提高 sparse 权重

## 7.5 RAG tool 暴露形式

RAG 必须作为 tool，而不是后台偷偷注入。

建议接口：

```python
rag_search(
    query: str,
    top_k: int = 5,
    search_mode: str = "hybrid",
    chapter_scope: tuple[int, int] | None = None,
    entity_filter: list[str] | None = None,
) -> RagSearchResult
```

返回结构：

```json
{
  "query": "主角此前什么时候第一次见过旧印章",
  "hits": [
    {
      "chunk_id": "0003_02",
      "score": 0.87,
      "chapter_id": 3,
      "text": "……",
      "summary": "林澈在渡口察觉异常印章"
    }
  ]
}
```

## 8. 人工介入 Tool 设计

人工介入应是标准工具调用，适用于：

- 审核总纲
- 修改细纲
- 批准正文
- 指定必须保留/删除内容
- 在剧情冲突时人工裁决

建议接口：

```python
request_human_intervention(
    stage: str,
    reason: str,
    payload: dict
) -> HumanInterventionResult
```

典型 `stage`：

- `outline_review`
- `detail_outline_review`
- `chapter_review`
- `canon_conflict_resolution`

返回结构建议：

```json
{
  "approved": true,
  "edited_payload": {},
  "instruction": "保留这段师徒冲突，但弱化直白说明",
  "operator": "user",
  "timestamp": "2026-04-21T12:00:00+08:00"
}
```

## 9. 归档设计

每篇正文必须存为 Markdown。

建议命名：

- `data/projects/{project_id}/chapters/0001.md`
- `data/projects/{project_id}/chapters/0002.md`

建议 Markdown 模板：

```md
# 第 12 章 夜渡寒江

## 元信息

- chapter_id: 12
- outline_version: 1
- detail_outline_version: 4
- created_at: 2026-04-21T12:00:00+08:00

## 正文

这里是正文内容……

## 章节摘要

林澈在渡口确认有人借旧制印章传递消息，但尚未锁定内奸身份。

## 新增事实

- 船票使用旧印章
- 林澈开始怀疑内部有人通敌

## 伏笔候选

- 船夫提到“三天前也有人问过同样的问题”
```

## 10. 编排层设计

推荐由 `orchestrator` 统一负责流程，不让 Agent 彼此直接调用。

原因：

1. 更容易控制上下文边界
2. 更容易记录状态
3. 更容易插入人工审核
4. 更容易重试失败节点

建议核心接口：

```python
class NovelWorkflow:
    def create_project(self, user_input: dict) -> ProjectState: ...
    def generate_outline(self, project_id: str) -> OutlineResult: ...
    def generate_detail_outline(self, project_id: str) -> DetailOutlineResult: ...
    def write_chapter(self, project_id: str) -> ChapterDraftResult: ...
    def archive_chapter(self, project_id: str, chapter_id: int) -> ArchiveResult: ...
    def advance_progress(self, project_id: str) -> ProjectState: ...
```

## 11. Tool 调用策略

### 11.1 Detail Outline Agent 可调用

- `rag_search`
- `request_human_intervention`

### 11.2 Writer Agent 可调用

- `rag_search`
- `request_human_intervention`

但要做权限约束：

- Writer Agent 的 `rag_search` 默认只允许查询历史正文与当前必要设定
- 不允许 Writer Agent 直接索取完整总纲

### 11.3 Outline Agent 可调用

- `request_human_intervention`

一般不需要访问 RAG，除非支持基于旧项目复用世界观。

## 12. Prompt 与结构化输出

建议三个 Agent 全部采用：

1. 系统提示词模板
2. 明确输入 schema
3. 结构化 JSON 输出
4. 失败时自动重试和修复解析

原因：

- 长篇项目最怕自由文本接口失控
- 结构化输出更适合状态推进和数据存档

建议：

- Outline Agent 输出 JSON
- Detail Outline Agent 输出 JSON
- Writer Agent 输出：
  - Markdown 正文
  - JSON 元数据

## 13. 异常与回退机制

需要提前设计以下失败场景：

### 13.1 细纲与前文冲突

处理方式：

1. Detail Outline Agent 先做一致性检查
2. 若冲突可修正，则重生细纲
3. 若冲突涉及主线，触发人工介入

### 13.2 正文偏离细纲

处理方式：

1. Writer 输出后做章节自检
2. 若偏离较轻，自动修订
3. 若偏离严重，退回重新生成

### 13.3 检索召回不准

处理方式：

1. 同时保留 dense 与 sparse 结果
2. 记录查询日志
3. 后续迭代融合权重与 chunk 策略

### 13.4 Embedding 服务不可用

处理方式：

1. 先落 Markdown 和元数据
2. 将向量化任务标记为待补写
3. 后台或下次启动时补建索引

## 14. MVP 范围

第一阶段建议只做最小闭环：

1. 创建项目
2. 生成总纲
3. 生成单章细纲
4. 生成单章正文
5. Markdown 存档
6. 正文入库到 FAISS + BM25
7. 下一章可通过 RAG 检索上一章内容

MVP 暂不做：

- 多用户并发
- Web UI
- 自动长程重规划
- 世界观跨作品复用
- 多模型路由

## 15. 推荐技术栈

推荐使用：

- Python 3.11+
- `pydantic`：schema 与状态定义
- `faiss-cpu`：向量检索
- `rank-bm25` 或等价实现：BM25
- `sentence-transformers`：embedding 接入
- `markdown` 或简单模板：章节归档
- `orjson`：高性能 JSON 存储

LLM 适配层建议自建统一接口：

```python
class LLMClient(Protocol):
    def generate(self, messages: list[dict], **kwargs) -> dict: ...
```

这样后续替换供应商时，Agent 层不用跟着改。

## 16. 后续开发顺序

推荐按以下顺序实现：

1. 定义 schema 与项目目录约定
2. 实现存储层与状态层
3. 实现 Outline Agent
4. 实现 Detail Outline Agent
5. 实现 Writer Agent
6. 实现 Markdown 归档
7. 实现 chunking + embedding + FAISS
8. 实现 BM25 与混合检索
9. 实现 tool 权限控制
10. 加入人工介入节点

## 17. 本设计的关键结论

1. 总纲、细纲、正文必须严格分层，尤其要保持正文 Agent 的“局部视角”。
2. ToT 放在总纲阶段，CoT 放在细纲阶段，不直接暴露给正文阶段。
3. 正文完成后必须立即 Markdown 归档并进入混合检索记忆库。
4. RAG 与人工介入都应成为标准 tool，由编排层统一控制。
5. 编排层必须用显式状态推进，避免脚本式串联导致上下文和进度失控。

---

如果按这份设计继续开发，下一步最适合先落的是：

- `pyproject.toml`
- `src/schemas/*`
- `src/orchestrator/state.py`
- `src/storage/*`

也就是先把“状态、目录、数据结构”打牢，再接三个 Agent 和 RAG。
