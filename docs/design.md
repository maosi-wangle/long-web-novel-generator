# 模块化多智能体小说生成系统架构设计（v4.3 - 人机协同版）

## 0. 产品定位（必须统一认知）
本系统**不是完备的自动小说生产器**，而是“人工快速小说生成辅助系统”。

- 目标是加速作者工作流，而不是替代作者决策。
- 任何章节进入初稿生成前，必须经过人工审阅细纲与 RAG 召回设定。
- 后续必须支持前后端协作：前端承担审阅交互，后端承担工作流编排与状态管理。

---

## 核心特性
1. **上帝视角建图（Top-down Worldbuilding）**：提前生成世界观与未来宿命并入库。
2. **掩码注意力（Masked Attention）**：编剧可见全局，写手只见经人工确认后的局部上下文。
3. **人机协同硬闸门（Human-in-the-Loop Gate）**：细纲与相关设定必须人工审核后才可进入 DraftWriter。
4. **接口契约化（Interface Driven）**：状态、函数签名、路由决策均类型化，便于前后端与多节点协同开发。
5. **可切换存储后端（Storage Backend Swappable）**：本地可用 JSONL 快速跑通，面向工程化场景可切换到关系型数据库，体现 SQL 与事务边界设计。

---

## 1. 第 0 阶段：创世初始化（World Initialization）
在正文生成前，优先运行“创世智能体网络”，产出并持久化以下资产至 GraphRAG：

- **世界观法则（World Bible）**：境界划分、能力上限、地理与移动规则。
- **角色命运拓扑（Character & Destiny Topology）**：关键角色关系、不可提前触发的宿命事件、阶段性里程碑。

---

## 2. 全局状态契约（State Payload）
**文件**：`novel_state.py`

```python
from typing import Literal, TypedDict

Phase = Literal["起", "承", "转", "合"]
ReviewStatus = Literal["pending", "approved", "rejected", "edited"]
RouteDecision = Literal["NeedHumanReview", "Rejected", "Approved", "Abort"]


class RagEvidence(TypedDict, total=False):
    source_id: str
    title: str
    snippet: str
    score: float


class NovelState(TypedDict, total=False):
    # ===== 版本治理预留字段（v4.4 预留） =====
    chapter_id: str
    version_id: str
    parent_version_id: str
    chapter_status: str

    # ===== 上帝视角字段（编剧/质检可见） =====
    world_rules: str
    global_outline: str
    future_waypoints: str
    guidance_from_future: str
    current_arc: str

    # ===== 章节执行字段 =====
    current_phase: Phase
    memory_l0: str
    previous_chapter_ending: str
    chapter_agenda: str

    # ===== RAG 召回与人工审阅字段（v4.3 关键） =====
    rag_recall_summary: str
    rag_evidence: list[RagEvidence]
    agenda_review_status: ReviewStatus
    agenda_review_notes: str
    approved_chapter_agenda: str
    approved_rag_recall_summary: str

    # ===== 产物与控制字段 =====
    draft: str
    draft_word_count: int
    critic_feedback: str
    error: str
    rewrite_count: int
    max_rewrites: int

    model_name: str
    temperature: float
    use_mock_llm: bool
```

### 2.1 人工审核最小约束（必须）
- `agenda_review_status != "approved"` 时，禁止进入 `DraftWriter`。
- `DraftWriter` 只允许读取 `approved_chapter_agenda` 与 `approved_rag_recall_summary`（非原始版本）。

### 2.2 章节版本治理预留（v4.4 预留）
- 当前系统以“线性章节工作流”为主，但后续必须支持“中途回改”与“版本分叉”。
- 为避免未来大规模返工，状态层先预留以下最小字段：
  - `version_id`：当前章节状态所属的版本 ID。
  - `parent_version_id`：当前版本来源的父版本 ID，用于后续分叉/回改。
  - `chapter_status`：章节生命周期状态，用于后续 dirty / regenerate_required 等治理状态。
- 这些字段当前阶段不强行接入主流程逻辑，只作为后续章节管理、版本控制、回改传播的结构性预留。

---

## 3. 节点定义与函数签名

### Node A：编剧节点（Plotting Node）- 【全知】
**文件**：`plot_planner.py`

```python
def plotting_node(state: NovelState) -> dict:
    """
    读取 world_rules/global_outline/future_waypoints/current_arc/current_phase/memory_l0
    产出 chapter_agenda（候选细纲）
    """
    ...
```

### Node B：设定召回节点（RAG Recall Node）- 【全知】
**文件**：`rag_recall.py`

```python
def rag_recall_node(state: NovelState) -> dict:
    """
    基于 chapter_agenda + 当前上下文检索相关设定。
    产出 rag_recall_summary 与 rag_evidence。
    """
    ...
```

### Node C：人工审核闸门（Human Agenda Review Gate）- 【强制人工】
**文件**：`human_review_gate.py`

```python
def human_agenda_review_gate(state: NovelState) -> dict:
    """
    由前端人工审阅 chapter_agenda + rag_recall_summary + rag_evidence。
    人工可通过、驳回、编辑。
    产出:
      - agenda_review_status
      - agenda_review_notes
      - approved_chapter_agenda
      - approved_rag_recall_summary
    """
    ...
```

### Node D：初稿写手（Draft Writer Node）- 【掩码】
**文件**：`draft_writer.py`

```python
def build_draft_prompt(state: NovelState) -> str:
    """
    严格只读:
      current_phase, memory_l0, previous_chapter_ending,
      approved_chapter_agenda, approved_rag_recall_summary
    禁止读取: world_rules, future_waypoints（掩码约束）
    """
    ...


def draft_writer_node(state: NovelState) -> dict:
    ...
```

### Node E：时空质检员（Critic Node）- 【全知】
**文件**：`critic_reviewer.py`

```python
def critic_node(state: NovelState) -> dict:
    """
    校验 draft 是否违反 world_rules/future_waypoints。
    合格返回 error=""；不合格返回 error 与 critic_feedback。
    """
    ...
```

### Node F：历史沉淀机（Memory Harvester Node）
**文件**：`memory_harvester.py`

```python
def memory_harvester_node(state: NovelState) -> dict:
    """
    章节通过后提取实体关系、更新 previous_chapter_ending 并写入 GraphRAG。
    """
    ...
```

---

## 4. 路由规则（LangGraph Routing）
**文件**：`workflow.py`

```python
from langgraph.graph import END, START, StateGraph

workflow = StateGraph(NovelState)

workflow.add_node("PlotPlanner", plotting_node)
workflow.add_node("RagRecall", rag_recall_node)
workflow.add_node("HumanAgendaReview", human_agenda_review_gate)
workflow.add_node("DraftWriter", draft_writer_node)
workflow.add_node("CriticReviewer", critic_node)
workflow.add_node("MemoryHarvester", memory_harvester_node)

workflow.add_edge(START, "PlotPlanner")
workflow.add_edge("PlotPlanner", "RagRecall")
workflow.add_edge("RagRecall", "HumanAgendaReview")


def route_after_human_review(state: NovelState) -> RouteDecision:
    status = state.get("agenda_review_status", "pending")
    if status in {"pending", "edited"}:
        return "NeedHumanReview"
    if status == "rejected":
        return "Rejected"
    return "Approved"


workflow.add_conditional_edges(
    "HumanAgendaReview",
    route_after_human_review,
    {
        "NeedHumanReview": "HumanAgendaReview",  # 等待或继续人工编辑
        "Rejected": "PlotPlanner",               # 人工打回重做细纲
        "Approved": "DraftWriter",              # 人工放行后才能生成初稿
    },
)

workflow.add_edge("DraftWriter", "CriticReviewer")


def route_after_critic(state: NovelState) -> RouteDecision:
    if state.get("error"):
        if state.get("rewrite_count", 0) >= state.get("max_rewrites", 3):
            return "Abort"
        return "Rejected"
    return "Approved"


workflow.add_conditional_edges(
    "CriticReviewer",
    route_after_critic,
    {
        "Rejected": "DraftWriter",
        "Approved": "MemoryHarvester",
        "Abort": END,
    },
)

workflow.add_edge("MemoryHarvester", END)
app = workflow.compile()
```

---

## 5. 前后端协作边界（v4.3 新增）

### 5.1 后端职责
- 执行 LangGraph 工作流、维护 `NovelState`、持久化审阅记录。
- 提供 API：触发生成、拉取待审任务、提交审阅结论、继续执行图。
- 对“未审核不可写作”做强制校验（服务端兜底，不依赖前端自觉）。
- 存储层必须通过统一抽象隔离底层实现，允许本地 JSONL、Neo4j、SQLite/PostgreSQL 并存。

### 5.2 前端职责
- 展示细纲候选、RAG 召回证据、相关设定来源片段。
- 提供人工操作：通过、驳回、编辑细纲；填写审阅备注。
- 审核通过后再触发“进入初稿生成”。

### 5.3 推荐最小 API（示意）
- `POST /chapters/{id}/plan`：生成细纲候选 + RAG 召回。
- `GET /chapters/{id}/review-task`：获取待人工审核内容。
- `POST /chapters/{id}/review`：提交 `approved/rejected/edited` 及备注。
- `POST /chapters/{id}/draft`：仅当审核通过时允许执行。

---

## 6. 关系型数据库与事务设计（v4.4 新增）

### 6.1 为什么要补 SQL / 事务层

当前 JSONL 方案适合 MVP，但它本质上更像“本地状态快照文件”，不擅长表达以下工程能力：

- 同一部小说下 `chapter_number` 的唯一约束
- 多张表之间的一致性写入
- 审计事件与业务状态的原子提交
- 并发更新时的冲突控制
- 面向面试与生产化的 SQL 查询能力展示

因此，设计上必须预留一个关系型数据库后端，用来承载：

- 小说主数据
- 章节主数据
- 审核 / 召回审计事件
- 章节状态快照

### 6.2 存储后端分层原则

推荐存储分层如下：

- `GraphStore`：统一抽象接口，不让 service 层直接依赖某一种数据库。
- `JsonlGraphStore`：本地开发 / 零依赖 MVP。
- `Neo4jGraphStore`：图谱 / 审计事件增强。
- `SqliteGraphStore` 或 `PostgresGraphStore`：关系型业务主存储，重点体现 SQL 与事务。

原则：

1. 业务编排层只依赖 `GraphStore` 接口。
2. 关系型数据库负责“事务性业务真相”。
3. 图数据库负责“图关系与可扩展知识网络”。
4. JSONL 只保留为本地快速演示 fallback，不应成为长期唯一主存储。

### 6.3 推荐关系表设计

#### 表 1：`novels`

用途：保存小说主信息。

```sql
CREATE TABLE novels (
    novel_id TEXT PRIMARY KEY,
    novel_title TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

#### 表 2：`chapters`

用途：保存章节主信息与当前生命周期状态。

```sql
CREATE TABLE chapters (
    chapter_id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    chapter_title TEXT NOT NULL,
    chapter_status TEXT NOT NULL,
    agenda_review_status TEXT NOT NULL,
    recall_trace_id TEXT DEFAULT '',
    review_trace_id TEXT DEFAULT '',
    draft_word_count INTEGER NOT NULL DEFAULT 0,
    version_id TEXT DEFAULT '',
    parent_version_id TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(novel_id),
    UNIQUE (novel_id, chapter_number)
);
```

这里的 `UNIQUE (novel_id, chapter_number)` 很关键，它能直接体现：

- 同一部小说内部章节号不能重复
- “准备下一章”与后端续章逻辑的数据库约束基础

#### 表 3：`chapter_snapshots`

用途：保存章节完整状态快照，用于恢复、调试和版本治理预留。

```sql
CREATE TABLE chapter_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id TEXT NOT NULL,
    version_id TEXT DEFAULT '',
    snapshot_json TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chapter_id) REFERENCES chapters(chapter_id)
);
```

这里刻意保留 `snapshot_json`，因为当前系统的 `NovelState` 字段较多、演化较快。  
这能在“关系结构化主表 + JSON 快照灵活扩展”之间取得平衡。

#### 表 4：`recall_events`

用途：保存每次 RAG / GraphRAG 召回事件，作为 append-only 审计表。

```sql
CREATE TABLE recall_events (
    trace_id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL,
    chapter_agenda TEXT NOT NULL,
    rag_recall_summary TEXT NOT NULL,
    rag_evidence_json TEXT NOT NULL,
    recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chapter_id) REFERENCES chapters(chapter_id)
);
```

#### 表 5：`review_events`

用途：保存人工审核事件，保留审核链路。

```sql
CREATE TABLE review_events (
    trace_id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL,
    recall_trace_id TEXT NOT NULL,
    agenda_review_status TEXT NOT NULL,
    agenda_review_notes TEXT NOT NULL,
    approved_chapter_agenda TEXT NOT NULL,
    approved_rag_recall_summary TEXT NOT NULL,
    recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chapter_id) REFERENCES chapters(chapter_id)
);
```

### 6.4 推荐索引设计

为了体现 SQL 设计能力，至少应加这些索引：

```sql
CREATE INDEX idx_chapters_novel_id ON chapters(novel_id);
CREATE INDEX idx_chapters_novel_number ON chapters(novel_id, chapter_number);
CREATE INDEX idx_recall_events_chapter_id ON recall_events(chapter_id);
CREATE INDEX idx_review_events_chapter_id ON review_events(chapter_id);
```

意义：

- `list_chapters(novel_id)` 会稳定按章节号排序
- `get_review_task(chapter_id)` 能快速拉到最新审核 / 召回链路

### 6.5 关键 SQL 查询示例

#### 查询某小说的章节列表

```sql
SELECT
    chapter_id,
    novel_id,
    chapter_number,
    chapter_title,
    chapter_status,
    agenda_review_status,
    draft_word_count,
    updated_at
FROM chapters
WHERE novel_id = :novel_id
ORDER BY chapter_number ASC, chapter_id ASC;
```

#### 查询上一章

```sql
SELECT chapter_id, chapter_number, chapter_title
FROM chapters
WHERE novel_id = :novel_id
  AND chapter_number < :chapter_number
ORDER BY chapter_number DESC
LIMIT 1;
```

#### 聚合小说列表

```sql
SELECT
    n.novel_id,
    n.novel_title,
    COUNT(c.chapter_id) AS chapter_count,
    MAX(c.updated_at) AS latest_updated_at
FROM novels n
LEFT JOIN chapters c ON c.novel_id = n.novel_id
GROUP BY n.novel_id, n.novel_title
ORDER BY latest_updated_at DESC NULLS LAST, n.novel_id ASC;
```

这里建议保留部分显式 SQL，而不是把所有查询都完全交给 ORM 隐藏掉。  
原因很简单：这个项目加 SQL 的目的之一，就是明确体现你对查询、聚合、索引和事务的理解。

### 6.6 事务边界（最重要）

#### 事务 A：创建小说 `create_novel`

必须原子完成：

1. 检查 `novel_id` 是否已存在
2. 插入 `novels`
3. 提交事务

如果唯一键冲突，则整体回滚并返回业务错误。

#### 事务 B：生成计划 `generate_plan`

必须原子完成：

1. upsert `chapters`
2. 写入 `chapter_snapshots`
3. 写入 `recall_events`
4. 更新 `chapters.recall_trace_id`
5. 提交事务

如果只写成功了章节状态，但召回事件没写成功，就会出现“页面能看到计划，但审计链路断裂”的脏状态。  
因此这一步必须在一个事务里完成。

#### 事务 C：提交审核 `submit_review`

必须原子完成：

1. 更新 `chapters.agenda_review_status`
2. 更新 `chapters.review_trace_id`
3. 写入 `review_events`
4. 写入 `chapter_snapshots`
5. 提交事务

这样才能保证：

- 当前章节状态
- 最新审核 trace
- 审核审计记录

三者始终一致。

#### 事务 D：落盘初稿 `generate_draft`

这里要特别注意：  
**LLM 网络调用不应该包在长事务里。**

推荐分两段：

1. 先读取章节并校验 `agenda_review_status == approved`
2. 在事务外调用 `DraftWriter + Critic`
3. 再开启一个短事务，只负责持久化：
   - `chapters.chapter_status`
   - `draft_word_count`
   - 最新 snapshot
   - `previous_chapter_ending` 的连续性结果

理由：

- 模型调用可能耗时几十秒
- 如果一直占着数据库事务，会造成锁持有过久、吞吐下降、并发冲突变严重

这也是一个非常适合面试时讲清楚的事务设计点。

### 6.7 并发控制建议

至少要考虑这两类并发问题：

#### 问题 1：同一小说并发创建第 N 章

解决：

- 数据库层使用 `UNIQUE (novel_id, chapter_number)`
- 应用层捕获唯一键冲突，返回“章节号已存在”

#### 问题 2：多人同时审核同一章节

解决：

- 初步可用 `updated_at` 或 `version_id` 做乐观锁
- 提交审核时要求“基于哪一个版本提交”
- 如果版本不一致，则拒绝覆盖并提示刷新

这部分正好与前面预留的：

- `version_id`
- `parent_version_id`

形成闭环。

### 6.8 与当前代码结构的映射建议

建议新增：

- `sqlite_graph_store.py`
- 或 `postgres_graph_store.py`

并在 `factory.py` 中支持：

```python
GRAPH_STORE_BACKEND=sqlite
GRAPH_STORE_BACKEND=postgres
```

当前推荐策略：

- 本地零依赖演示：`jsonl`
- 关系型数据库 / SQL / 事务展示：`sqlite`
- 图谱扩展：`neo4j`

这样这个项目就能同时体现：

- 原型快速搭建能力
- 工程化数据库建模能力
- SQL 与事务设计能力
- 多存储后端抽象能力

---

## 6.9 可选的 BAML 接入层（后续增强，不作为当前阶段前置依赖）

### 6.9.1 为什么只作为“可选增强层”

BAML 适合解决的问题，不是工作流编排，也不是持久化，而是：

- Prompt 以函数形式管理
- LLM 结构化输出有明确 schema
- 同一类提示词可单测、可回归、可多语言复用

因此它更像：

- `LLM 契约层`

而不是：

- `HTTP 路由层`
- `工作流状态机层`
- `存储层`

当前系统里：

- FastAPI 负责对外接口与前后端联调
- ChapterService 负责业务编排
- LangGraph 负责节点状态流转
- GraphStore 负责持久化与查询

即使未来引入 BAML，这四层职责也不改变。  
BAML 只应作为“节点内部调用 LLM 时的提示词与结构化输出定义层”接入，而不应替代 FastAPI / LangGraph / Store。

### 6.9.2 当前项目里最适合接入 BAML 的位置

#### 场景 A：PlotPlanner 结构化规划

当 `PlotPlanner` 从当前占位逻辑升级为真实 LLM 规划器后，推荐让 BAML 产出固定结构，例如：

- `chapter_agenda`
- `beats`
- `foreshadowing`
- `risk_points`

这样可避免 service / node 层自己手写文本解析。

#### 场景 B：CriticReviewer 结构化审稿

当 `CriticReviewer` 从规则演示升级为 LLM 审稿器后，推荐让 BAML 返回固定结构，例如：

- `passed: bool`
- `violations: list[str]`
- `rewrite_advice: str`
- `severity: str`

这是当前项目最值得优先试点 BAML 的节点，因为它天然需要“稳定的结构化判断结果”。

#### 场景 C：RAG Recall 的摘要与证据归并

若未来 `RagRecall` 不再只是拼装 evidence，而是需要 LLM 对召回证据进行筛选、聚合与摘要，可让 BAML 输出：

- `rag_recall_summary`
- `selected_evidence`
- `coverage_gaps`

#### 场景 D：Memory Harvester 的结构化提取

如果后续要从已通过章节中稳定提取：

- 人物
- 关系
- 新设定
- 下一章 continuity 提示

则 BAML 也很适合承担这类“从正文提取结构化信息”的工作。

### 6.9.3 当前不建议用 BAML 的位置

以下部分不应由 BAML 接管：

- FastAPI 路由与 Pydantic API schema
- LangGraph workflow / routing
- GraphStore / JsonlGraphStore / Neo4jGraphStore
- 事务边界与数据库读写

原因很简单：

- BAML 的职责是“定义和约束 LLM 调用”
- 它不负责 HTTP 服务
- 不负责状态机编排
- 不负责持久化一致性

### 6.9.4 接入策略建议

推荐采用“渐进式接入”：

1. 当前阶段不把 BAML 设为项目必选依赖。
2. 等出现 2 到 3 个“真实 LLM + 稳定结构化输出”节点后，再正式引入。
3. 第一个试点节点优先选择 `CriticReviewer`，其次是升级后的 `PlotPlanner`。
4. `DraftWriter` 正文生成本身仍可保留现有调用方式；BAML 更适合其外围结构化产物，而不是长篇正文主输出。

### 6.9.5 设计原则

若后续接入 BAML，应遵守：

1. BAML 文件只描述提示词函数、输入输出 schema 与测试样例。
2. 节点仍通过 Python 封装 BAML 调用结果，再写回 `NovelState`。
3. 工作流跳转仍由 LangGraph 决定，不把路由逻辑写进 BAML。
4. API 返回合同仍以 Pydantic schema 为准，不让前端直接依赖 BAML 内部结构。

这样可以保证：

- LLM 契约清晰
- 系统分层不被打乱
- 后续切换模型或提示词时改动范围可控

## 7. DoD（验收清单）
- 文档明确系统定位为“人工快速生成辅助”，非全自动生产器。
- 细纲生成后、初稿生成前存在强制人工审核节点。
- 人工审核对象至少包含：`chapter_agenda` + `rag_recall_summary` + `rag_evidence`。
- 后端存在“未审核不可进入 DraftWriter”的硬约束。
- 路由存在重写上限与 `Abort` 分支，避免无限循环。
- 存在关系型数据库后端设计，至少覆盖 `novels / chapters / chapter_snapshots / recall_events / review_events`。
- 关键写路径定义了明确事务边界，而不是“状态写一点、审计写一点”地分散提交。
- 同小说内部章节号具备数据库唯一约束。
- LLM 网络调用不在长事务内持锁执行。

## Agenda 命名更新（方案二）

- `chapter_agenda_draft`：作者/前端输入的草稿细纲，作为 PlotPlanner 的输入。
- `chapter_agenda`：PlotPlanner 产出的正式细纲，供 RAG recall、人工审核、后续放行使用。
- Workbench 中输入框对应 `chapter_agenda_draft`，只读展示框对应 `chapter_agenda`。
- `approved_chapter_agenda` 仍表示“人工审核后最终放行给 DraftWriter 的细纲”。
## Frontend Status

The standalone workbench frontend is currently paused. The active runtime surface is backend-only:

- FastAPI routes
- ChapterService orchestration
- store persistence
- node-level runners such as un_stage1.py, un_stage2.py, un_plot_planner.py`r
