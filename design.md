# 模块化多智能体小说生成系统架构设计 (v3.0 - LangGraph 生态版)
**核心特性：状态机图表 (StateGraph) + 渐进式揭露记忆 (Progressive Disclosure) + 三级节奏控制 (Pacing Control)**

## 1. 架构总览与技术栈选型
系统摒弃了早期的自定义 Redis Pub/Sub 事件驱动模型，全面拥抱 **LangChain / LangGraph** 生态。通过“有向无环/有环图 (Graph)”和“全局状态机 (State)”来管理复杂的 Agent 交互与长文本流转，彻底解决长篇连载中的上下文过载、幻觉以及多章节状态同步问题。

* **调度编排**：`LangGraph` (替代自建主控与消息总线)
* **工具链与检索**：`LangChain` 核心库 (替代手搓的 API 请求与数据库查询)
* **状态与持久化**：`LangGraph Checkpointer` (如 SQLiteSaver，替代 Redis 临时黑板)



---

## 2. 核心机制一：三级大纲与节奏控制 (Three-Tier Outline & Pacing)
利用状态流转机制，系统对小说进行宏观、中观、微观三层控制，防止 Agent “贪心生成”（局部最优导致全局崩盘）。

* **宏观层：全书大纲 (Global Logline)**
    * **定位**：故事的终极方向。开书时生成，固化在全局 State 中。
* **中观层：剧情弧线与阶段 (Story Arc & Phase)**
    * **定位**：解决“行文节奏”。将小说切分为多个卷宗。
    * **动态属性**：包含 `current_phase`（起/铺垫、承/发展、转/高潮、合/尾声）。此状态随图表流转而更新，直接约束引擎的笔法。
* **微观层：单章细纲 (Chapter Agenda)**
    * **定位**：解决“本章演什么”。作为单次 Graph 执行的输入动态推演，阅后即焚。

---

## 3. 核心机制二：三级渐进式记忆系统 (Three-Tier Memory mapping)
彻底抛弃“全量上下文注入”，采用 LangGraph 和 LangChain 组件实现按需供给的记忆流：

* **L0: 常驻工作台 (The Core Context) —— 【State 自动推 PUSH】**
    * **技术映射**：由 LangGraph 的 `TypedDict` 或 `Pydantic` 定义的全局 `NovelState`。
    * **机制**：配合 `Checkpointer`，每次节点流转自动携带。包含全书主线、当前卷宗目标及阶段、上一章结尾动作。
* **L1: 语义与图谱检索 (Semantic & Graph Retrieval) —— 【ToolNode 按需拉 PULL】**
    * **技术映射**：LangChain `@tool` 装饰器 + 本地 VectorStore (如 FAISS/Chroma)。
    * **机制**：通过 Function Calling 触发。解决名词、道具、人物最新状态设定的幻觉问题。Agent 自主调用 `query_setting` 工具获取精准设定。
* **L2: 原文深潜 (Deep Git Retrieval) —— 【ToolNode 精准拉 PULL】**
    * **技术映射**：LangChain `DocumentLoader` + `TextSplitter`。
    * **机制**：提取精确的历史对话或场景原文，实现神级伏笔回收。

---

## 4. 核心工作流节点 (Node) 定义

在 LangGraph 架构下，原有的模块转化为 Graph 中的计算节点（Nodes），通过边（Edges）定义数据流向。

### 节点 1：情节引擎 (Plotting Node)
* **职责**：宏观调度器。读取 `NovelState` 中的 L0 记忆，结合上一章的剧情，推演本章的细纲 (`Agenda`)，并决策是否流转当前卷的 `current_phase`。
* **输出**：更新 State 中的 `agenda` 和 `current_phase`。

### 节点 2：初稿生成引擎 (Draft Writer Node)
* **职责**：受节奏严格约束的智能作家。
* **内部机制**：绑定了 L1/L2 查询工具的大模型。读取 State，遇到知识盲区时触发条件边（Conditional Edge），进入 `ToolNode` 查询资料，获取结果后生成逻辑严密的初稿文本。
* **输出**：更新 State 中的 `draft_text`。

### 节点 3：知识工具节点 (Tool Node)
* **职责**：被初稿引擎触发的独立执行单元。运行具体的 LangChain `@tool` 逻辑，访问数据库并返回设定数据，将其作为 `tool_message` 塞回上下文对话历史中。

### 节点 4：文风渲染与归档节点 (Polisher & Commit Node)
* **职责**：润色初稿文本，提取本章摘要覆盖 `NovelState` 中的“上一章结尾”，触发 Checkpointer 持久化保存，为下一章生成做准备。