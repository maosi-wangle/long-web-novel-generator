# 模块化多智能体小说生成系统架构设计 (v3.0 - LangGraph & GraphRAG 生态版)
**核心特性：状态机图表 (StateGraph) + 图谱检索增强 (GraphRAG) + 三级节奏控制 (Pacing Control)**

## 1. 架构总览与技术栈选型
系统全面拥抱 **LangChain / LangGraph** 生态，并通过 **GraphRAG（图谱检索增强生成）** 彻底解决长篇连载中的上下文过载、设定冲突（吃书）以及“挖坑不填”的致命痛点。

* **调度编排**：`LangGraph` (替代早期自建的 Redis Pub/Sub 主控与消息总线)
* **状态与持久化**：`LangGraph Checkpointer` (如 SQLiteSaver，自带记忆快照与回滚)
* **动态图谱与逻辑推演**：`GraphRAG` / `Neo4j` / `NetworkX` (管理剧情线与伏笔网络)
* **工具链交互**：`LangChain Core Tools` (将图谱查询与本地检索封装为 Agent 工具)

[Image of LangGraph architecture integrating state management and external GraphRAG tool nodes]

---

## 2. 核心机制一：三级大纲与节奏控制 (Three-Tier Outline & Pacing)
利用 LangGraph 的状态流转机制，对小说进行宏观、中观、微观三层约束，防止 Agent “贪心生成”（单章滥用高潮导致全书崩溃）。

* **宏观层：全书大纲 (Global Logline)**
    * **定位**：故事的终极方向。开书时生成，固化在全局 State 中。
* **中观层：剧情弧线与阶段 (Story Arc & Phase)**
    * **定位**：解决“行文节奏”。将小说切分为多个卷宗。
    * **动态属性**：包含 `current_phase`（起/铺垫、承/发展、转/高潮、合/尾声）。此状态随图表流转而动态更新，直接约束初稿引擎的笔法。
* **微观层：单章细纲 (Chapter Agenda)**
    * **定位**：解决“本章演什么”。作为单次 Graph 执行的输入动态推演，阅后即焚。

---

## 3. 核心机制二：基于 GraphRAG 的三级渐进式记忆系统
彻底抛弃传统的“全量上下文注入”或“纯文本相似度检索”，采用基于知识图谱的按需供给：

* **L0: 常驻工作台 —— 【State 自动推 PUSH】**
    * **机制**：由 LangGraph 定义的全局 `NovelState`。配合 Checkpointer 每次节点流转时自动携带。包含全书主线、当前卷宗目标及阶段、上一章结尾动作。
* **L1: 剧情与伏笔图谱检索 —— 【GraphRAG 按需拉 PULL】**
    * **图谱本体定义 (Ontology)**：
        * **实体节点**：`Character` (角色), `Item` (道具), `Event` (事件), `Mystery` (伏笔/谜团)。
        * **关系边线**：`PARTICIPATED_IN` (参与), `CAUSED_BY` (导致), `FORESHADOWS` (埋下伏笔), `RESOLVED_BY` (解开谜团)。
    * **机制**：Agent 遇到知识盲区或需要填坑时，自主调用图谱工具（如 `query_unresolved_foreshadowing`），顺着图谱路径提取多线交织的准确设定与待回收伏笔。
* **L2: 原文深潜检索 —— 【Document 向量精准拉 PULL】**
    * **机制**：通过 LangChain `DocumentLoader` + `TextSplitter`。Agent 需要极度精确的台词回溯时调用，提取精确的历史对话原文。

[Image of a knowledge graph mapping character relationships, plot events, and foreshadowing clues for a novel]

---

## 4. 核心工作流节点 (Node) 定义
在 LangGraph 架构下，原有的微服务模块转化为 Graph 中的计算节点（Nodes），通过边（Edges）和条件路由（Conditional Edges）定义数据流向。

### 节点 1：图谱与情节引擎 (Plotting & Graph Node)
* **职责**：宏观调度器与图谱分析师。
* **核心动作**：读取 `NovelState` 中的 L0 记忆，对 Graph