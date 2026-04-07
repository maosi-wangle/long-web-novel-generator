# Stage 4 代码阅读清单

这份清单不是功能宣传，而是给你按“调用链 + 分层职责”去读代码用的。

建议阅读顺序：

1. 先看 API 路由层，知道系统暴露了哪些 HTTP 入口。
2. 再看 service 层，理解每个入口到底串了哪些节点、store、状态更新。
3. 然后看 schemas，弄清每个请求体/响应体的字段合同。
4. 再看 store，理解状态怎么落盘、怎么聚合成“多小说/多章节管理”视图。
5. 最后回到 workbench，看前端是怎么把这些接口串起来的。

---

## 1. 路由层：先看入口

文件：

- [app.py](/c:/project/generateNovel/backend/src/novel_assist/api/app.py)

重点看这些路由：

- `GET /`
- `GET /healthz`
- `GET /workbench`
- `GET /novels`
- `GET /novels/{novel_id}/chapters`
- `POST /chapters/{chapter_id}/plan`
- `GET /chapters/{chapter_id}/review-task`
- `POST /chapters/{chapter_id}/review`
- `POST /chapters/{chapter_id}/draft`
- `GET /chapters/{chapter_id}/state`

你要理解的点：

- `app = FastAPI(...)` 是整个后端应用对象。
- `@app.get(...)` / `@app.post(...)` 是注册路由，不是普通函数调用。
- 路由层不直接做业务计算，而是把请求交给 `ChapterService`。
- `response_model=...` 是响应合同，FastAPI 会按 Pydantic 模型输出和校验。
- `@app.middleware("http")` 是统一 HTTP 中间件；这里做的是给 JSON 响应补 `charset=utf-8`。
- `ApiErrorException` + 异常处理器，负责把错误统一整理成 `error_code / message / detail / trace_id`。

---

## 2. Service 层：看“谁在编排谁”

文件：

- [chapter_service.py](/c:/project/generateNovel/backend/src/novel_assist/api/chapter_service.py)

这是整个 API 的编排层。可以把它理解成：

- 路由层负责“接电话”
- 节点负责“做具体业务”
- store 负责“存和查”
- service 负责“安排顺序”

### 2.1 `generate_plan`

调用链：

1. `build_initial_state()`
2. 用请求体 `overrides` 覆盖默认状态
3. `_coerce_metadata(...)` 补齐小说/章节元数据
4. 调 `plotting_node(state)`
5. 调 `rag_recall_node(state)`
6. 设置 `agenda_review_status = pending`
7. 落盘到 store

重点看：

- 这里不是跑完整 LangGraph `invoke()`，而是手动执行阶段四需要的前半段节点。
- `novel_id / novel_title / chapter_number / chapter_title` 在这里被整理成统一元数据。
- `chapter_status` 在这里会进入 `review_pending`，方便章节管理面板显示当前阶段。

### 2.2 `submit_review`

调用链：

1. 从 store 取出该章节现有状态
2. 把人工审核输入写回 state
3. 强制 `enforce_state_review_status = True`
4. 调 `human_agenda_review_gate(state)`
5. 按审核结果更新 `chapter_status`
6. 再落盘

重点看：

- 这是 HITL 审核真正写入状态的地方。
- `approved_chapter_agenda` 和 `approved_rag_recall_summary` 是“最终放行给 DraftWriter 的字段”。
- `enforce_state_review_status = True` 的作用是：API 模式下，只信当前 state 的审核状态，不再让环境变量偷偷覆盖流程。

### 2.3 `generate_draft`

调用链：

1. 先查该章节 state
2. 审核没通过就直接抛 `PermissionError`
3. 审核通过后进入 `draft_writer_node`
4. 再进 `critic_node`
5. 用 `route_after_critic(state)` 判断是重写、通过还是 abort
6. 通过时再调 `memory_harvester_node`
7. 最后更新 `chapter_status` 并落盘

重点看：

- 这里体现的是“DraftWriter + Critic + 重写上限”的后半段编排。
- `chapter_status` 会从 `drafting` 走到 `published` 或 `regenerate_required`。

### 2.4 新增的管理方法

- `list_novels()`
- `list_chapters(novel_id=...)`

作用：

- 这两个方法把底层 store 聚合出来的数据，直接提供给前端工作台做“多小说 + 章节管理”。

---

## 3. Schema 层：看字段合同

文件：

- [schemas.py](/c:/project/generateNovel/backend/src/novel_assist/api/schemas.py)

这层要重点看两件事：

1. 请求体怎么进来
2. 响应体怎么出去

### 3.1 计划请求/响应

- `PlanRequest`
- `PlanResponse`

新增重点字段：

- `novel_id`
- `novel_title`
- `chapter_number`
- `chapter_title`
- `chapter_status`

理解方式：

- `PlanRequest` 是“前端允许提交什么字段”
- `PlanResponse` 是“后端承诺返回什么字段”

### 3.2 审核相关合同

- `ReviewTaskResponse`
- `ReviewRequest`
- `ReviewResponse`

重点字段：

- `agenda_review_status`
- `approved_chapter_agenda`
- `approved_rag_recall_summary`
- `latest_recall_event`
- `latest_review_event`

### 3.3 初稿与状态

- `DraftResponse`
- `ChapterStateResponse`

重点看：

- `DraftResponse` 里既有正文，也有 `critic_feedback`、`rewrite_count`、`chapter_status`
- `ChapterStateResponse` 直接把完整 state 暴露给开发者模式

### 3.4 多小说管理合同

- `NovelSummary`
- `NovelListResponse`
- `ChapterSummary`
- `ChapterListResponse`

这四个模型是本次新增的重点。

你读的时候要注意：

- 小说列表接口只关心“小说层摘要”
- 章节列表接口只关心“单部小说下的章节摘要”
- 页面展示不直接拿原始 state 拼，而是通过这组专门的管理响应模型来展示

---

## 4. Store 层：看状态如何落盘、如何聚合

文件：

- [graph_store.py](/c:/project/generateNovel/backend/src/novel_assist/stores/graph_store.py)
- [jsonl_graph_store.py](/c:/project/generateNovel/backend/src/novel_assist/stores/jsonl_graph_store.py)
- [neo4j_graph_store.py](/c:/project/generateNovel/backend/src/novel_assist/stores/neo4j_graph_store.py)
- [factory.py](/c:/project/generateNovel/backend/src/novel_assist/stores/factory.py)

### 4.1 `GraphStore`

这里要看“抽象接口”的意义：

- 上层 service 不关心你底层是 JSONL 还是 Neo4j
- 它只依赖同一套方法签名

这次新增的方法：

- `list_novels()`
- `list_chapters(novel_id=...)`

这就是“存储抽象接口”的具体体现。

### 4.2 `JsonlGraphStore`

这是当前真正跑起来的本地实现。

建议重点读这些方法：

- `_read_state_map()`
- `_write_state_map()`
- `save_chapter_state(...)`
- `get_review_task(...)`
- `list_novels()`
- `list_chapters(...)`

你要理解的逻辑：

- `chapter_state.json` 仍然是以 `chapter_id` 为主键存整章状态。
- 多小说管理不是新建一套复杂数据库，而是从现有章节状态里聚合视图。
- `list_novels()` 做的是“按 `novel_id` 分组”，统计章节数、最近章节等摘要。
- `list_chapters()` 做的是“筛出某小说下的章节”，再按 `chapter_number` 排序。

### 4.3 `Neo4jGraphStore`

当前还是适配层思路：

- 审计事件可以写 Neo4j
- 章节快照和管理视图暂时继续走 JSONL fallback

也就是说：

- 现在已经把“多小说/章节管理”挂到抽象层了
- 以后真要切 Neo4j，只需要补这个实现，不用重写 service 和前端

---

## 5. 状态定义：看 NovelState 现在承载什么

文件：

- [novel_state.py](/c:/project/generateNovel/backend/src/novel_assist/state/novel_state.py)

这次新增的元数据字段：

- `novel_id`
- `novel_title`
- `chapter_number`
- `chapter_title`

之前已有、现在开始真正发挥作用的字段：

- `chapter_status`
- `version_id`
- `parent_version_id`

你要这样理解：

- `NovelState` 不是“某个节点私有字段”
- 它是所有节点共享的统一状态合同
- 谁读什么字段、谁写什么字段，都要围绕它展开

本次和章节管理最相关的是：

- `novel_id / novel_title`：把章节挂到某部小说下面
- `chapter_number / chapter_title`：让章节能被排序和展示
- `chapter_status`：让工作台能看见当前在“待审 / 已审 / 起草中 / 已产出”等哪个阶段

---

## 6. 前端工作台：看页面如何消费这些接口

文件：

- [workbench.html](/c:/project/generateNovel/backend/src/novel_assist/api/workbench.html)

建议从上到下读：

### 6.1 先看 HTML 分区

主要区块：

- `Novel Shelf`
- `Chapter Shelf`
- `Chapter Control`
- `Review Desk`
- `Evidence Cards`
- `Draft & Critic`
- `Unified Error Format`
- `Developer Console`

这几个区块分别对应：

- 小说管理
- 章节管理
- 章节计划输入
- 人工审核输入
- RAG 证据展示
- 初稿与 Critic 输出
- 错误统一展示
- 请求/响应/state 调试

### 6.2 再看 JS 状态流

重点函数：

- `loadNovels()`
- `loadChapters(...)`
- `applyNovelSelection(...)`
- `applyChapterSelection(...)`
- `apiRequest(...)`
- `fetchState()`
- `renderEvidence(...)`

你要理解的点：

- 小说和章节现在都以“卡片列表”显示
- 点击小说卡会触发加载章节列表
- 点击章节卡会把该章节信息装填到工作台输入框
- `apiRequest(...)` 是统一请求入口，顺便把最后一次 request/response 打到开发者面板里

### 6.3 为什么叫“卡片”

这里的“卡片”没有特殊框架含义。

它只是 UI 上一个独立的信息块，用来承载一条小说摘要或一条章节摘要。这样做的好处是：

- 一眼就能区分对象边界
- 后续加按钮、状态标记、版本信息更方便
- 页面结构和后端的 `NovelSummary / ChapterSummary` 模型天然对应

---

## 7. 节点层：本次没有重写，但要知道它们在 API 中怎么被用

文件：

- [plot_planner.py](/c:/project/generateNovel/backend/src/novel_assist/nodes/plot_planner.py)
- [rag_recall.py](/c:/project/generateNovel/backend/src/novel_assist/nodes/rag_recall.py)
- [human_review_gate.py](/c:/project/generateNovel/backend/src/novel_assist/nodes/human_review_gate.py)
- [draft_writer.py](/c:/project/generateNovel/backend/src/novel_assist/nodes/draft_writer.py)
- [critic_reviewer.py](/c:/project/generateNovel/backend/src/novel_assist/nodes/critic_reviewer.py)
- [memory_harvester.py](/c:/project/generateNovel/backend/src/novel_assist/nodes/memory_harvester.py)

本阶段你要用 service 视角去看它们：

- `generate_plan()` 会调用 `plotting_node + rag_recall_node`
- `submit_review()` 会调用 `human_agenda_review_gate`
- `generate_draft()` 会调用 `draft_writer_node + critic_node + memory_harvester_node`

也就是说：

- 节点还是业务原子模块
- API 阶段只是把原本 LangGraph 内的执行路径，拆成了更适合 HTTP 调试的服务编排

---

## 8. 测试：用来反向理解功能是否闭环

文件：

- [test_stage4_fastapi.py](/c:/project/generateNovel/backend/tests/integration/test_stage4_fastapi.py)

推荐读法：

### 8.1 `test_hitl_end_to_end`

看完整闭环：

1. 打开工作台
2. 生成计划
3. 取审核任务
4. 审核前尝试 draft，预期 409
5. 提交 approved 审核
6. 生成 draft
7. 拉完整 state

### 8.2 `test_multi_novel_and_chapter_management_routes`

这是本次新增的核心测试。

它验证：

- 多个章节可以归属于不同小说
- `/novels` 能正确聚合出小说列表
- `/novels/{novel_id}/chapters` 能按章节号排序返回章节

### 8.3 `test_uniform_error_payloads`

它验证：

- 404 业务错误是否统一返回
- 422 参数校验错误是否统一返回

---

## 9. 一条推荐的“读代码路径”

如果你现在准备自己顺一遍，推荐按这条线走：

1. [app.py](/c:/project/generateNovel/backend/src/novel_assist/api/app.py)
2. [schemas.py](/c:/project/generateNovel/backend/src/novel_assist/api/schemas.py)
3. [chapter_service.py](/c:/project/generateNovel/backend/src/novel_assist/api/chapter_service.py)
4. [graph_store.py](/c:/project/generateNovel/backend/src/novel_assist/stores/graph_store.py)
5. [jsonl_graph_store.py](/c:/project/generateNovel/backend/src/novel_assist/stores/jsonl_graph_store.py)
6. [novel_state.py](/c:/project/generateNovel/backend/src/novel_assist/state/novel_state.py)
7. [workbench.html](/c:/project/generateNovel/backend/src/novel_assist/api/workbench.html)
8. [test_stage4_fastapi.py](/c:/project/generateNovel/backend/tests/integration/test_stage4_fastapi.py)

这样读的好处是：

- 先从“接口入口”建立全局图
- 再看“中间编排”
- 再看“底层持久化”
- 最后看“页面怎么消费这些能力”

这条路线最不容易迷路。
