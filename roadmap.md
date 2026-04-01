# 🚀 小说生成系统 v2.0 开发路线图 (Roadmap)

**核心理念**：黑板模式 (Blackboard) + 三级渐进式记忆 (Three-Tier Memory)

---

## 📌 第一阶段：智能体化与“单兵作战” (基础通电)
**目标**：实现 Agent 的类封装，调通 L0 级（常驻上下文）的自动化写作流程。

* [ ] **1.1 抽象 `BaseAgent` 基类**
    * 统一集成 `NovelBlackboard` 实例。
    * 标准化 `listen()` 监听逻辑与 `dispatch()` 事件分发方法。
* [ ] **1.2 接入大模型生成引擎 (The Brain)**
    * 集成 `dashscope` (通义千问) 或 OpenAI 接口。
    * 封装统一的 LLM 调用工具类，支持流式输出与错误重试。
* [ ] **1.3 L0 级推送循环测试**
    * 实现 `WriterAgent` 监听 `AGENDA_READY` 事件。
    * **L0 数据流**：读取 `Workspace.Memory` (主线) + `Workspace.Agenda` (细纲) -> 生成正文。
    * **输出**：将正文写入 `Workspace.Draft`，并触发 `DRAFT_READY` 事件。

---

## 📂 第二阶段：档案库与工具箱 (L1 语义检索)
**目标**：赋予 Agent “查字典”的能力，解决设定冲突与幻觉问题。

* [ ] **2.1 静态设定数据库 (Plot/Character Repository)**
    * 在 Redis 中建立 `hash:characters` 和 `hash:world_settings`。
    * 存储格式：结构化 JSON（包含人物性格、道具功能、地理规则）。
* [ ] **2.2 Function Calling 桥接层**
    * 定义工具规范：`query_character_info(name)` / `query_location_setting(place)`。
    * 实现 **ReAct 思考循环**：Agent 分析细纲 -> 发现生僻设定 -> 触发 Action 检索 -> 获取 Observation。
* [ ] **2.3 L1 检索闭环验证**
    * 测试场景：细纲提到“主角拔出了【斩龙剑】”，Agent 必须先查询该武器特效，再描写战斗画面。

---

## 🌲 第三阶段：图谱驱动与动态状态 (核心逻辑升级)
**目标**：让世界具有“变量”，处理复杂的人际关系与即时动机。

* [ ] **3.1 动态角色矩阵 (Character API)**
    * 实现属性动态更新（如：好感度、心理阴影值、受损状态）。
    * Agent 写作前拉取：`query_character_state("主角")` 获取当前心境。
* [ ] **3.2 伏笔池管理 (Plot API)**
    * 建立 `suspense_pool`，记录尚未回收的剧情线。
    * Prompt 策略：强迫 Agent 在特定场景检查是否有可回收的伏笔。
* [ ] **3.3 状态回写与一致性检查**
    * 章节结束后，主控 Agent 异步更新 Redis 中的角色状态（如：张三在此章断了左臂）。

---

## 🛠️ 第四阶段：版本控制与原文深潜 (L2 Git 检索)
**目标**：实现神级伏笔回收，保证长篇行文的绝对连贯与“宿命感”。

* [ ] **4.1 Git 自动化流水线集成**
    * 实现每一章生成后的自动 `git add/commit`。
    * 在 Redis 中维护 Commit Hash 与章节索引的映射表。
* [ ] **4.2 向量化索引 (Vector DB)**
    * 接入 ChromaDB 或本地向量库。
    * 对历史文本进行切片（Chunking），实现基于语义的原文段落检索。
* [ ] **4.3 原文深潜工具 (Deep Retrieval)**
    * 开发 `fetch_history_dialogue` 工具。
    * Agent 思考：*“我想看看三年前他在雪山到底说了什么”* -> 系统返回精准原文片段。

---

## 🎭 第五阶段：审美渲染与多分支管理
**目标**：提升文学性，支持“平行时空”写作。

* [ ] **5.1 文风渲染模块 (Style API)**
    * 基于 RAG 提取特定作家的风格语料库（Few-shot）。
    * 对 `Workspace.Draft` 进行二次迭代润色，优化修辞与节奏。
* [ ] **5.2 分支剧情管理**
    * 利用 Git Branch 功能，支持生成多个版本的剧情走向供用户预览。

---

### 📅 当前进度追踪
- [x] **基础设施**：Redis 黑板系统通电完成。
- [x] **通信协议**：Pub/Sub 事件机制验证通过。
- [>] **正在进行**：1.1 抽象 BaseAgent 基类。