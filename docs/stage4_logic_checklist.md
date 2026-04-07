# 阶段四代码阅读清单

## 这份文档的用途
这不是面向汇报的阶段总结，而是面向“看代码理解业务逻辑”的阅读地图。

建议阅读目标：
- 先弄清楚请求从哪里进来
- 再看请求如何被编排
- 再看单个节点做了什么
- 最后看状态如何存取、如何返回给前端

换句话说，这份清单服务的不是“记住做了什么”，而是“按什么顺序读代码最容易看懂”。

## 推荐阅读顺序

### 1. 从 HTTP 入口开始看
先看 [app.py](/c:/project/generateNovel/backend/src/novel_assist/api/app.py)

你需要重点理解：
- `app = FastAPI(...)`
- `@app.middleware("http")`
- `@app.get(...)` / `@app.post(...)`
- 每个路由函数到底调用了谁

这一层的角色：
- 接收 HTTP 请求
- 做请求/响应模型绑定
- 把异常翻译成统一错误格式
- 调用 `ChapterService`

这一层不要试图找具体业务细节，因为它主要不是干业务的。

### 2. 再看接口契约
接着看 [schemas.py](/c:/project/generateNovel/backend/src/novel_assist/api/schemas.py)

你需要重点理解：
- 请求模型有哪些字段
- 响应模型有哪些字段
- 哪些字段是给前端看的，哪些是给调试看的
- `ApiErrorResponse` 为什么要统一

这一层的角色：
- 定义“接口输入输出长什么样”
- 让你读代码时知道：路由函数里的 `payload` 和返回值到底是什么结构

建议阅读方法：
- 看一个路由，就立刻对照它用到的 request/response schema
- 不要单独孤立地看 schema

### 3. 再看业务编排层
然后看 [chapter_service.py](/c:/project/generateNovel/backend/src/novel_assist/api/chapter_service.py)

这是阶段四里最关键的阅读文件之一，因为它最能体现“业务步骤顺序”。

重点方法：
- `generate_plan`
- `get_review_task`
- `get_chapter_state`
- `submit_review`
- `generate_draft`

你要重点问自己这几个问题：
- 它从哪里拿 state
- 它调用了哪些 node
- 它什么时候存状态
- 它什么时候抛异常
- 它为什么不直接 `workflow.invoke()`

这一层的角色：
- 手动模拟并拆分 LangGraph 工作流
- 让 API 变成 `/plan -> /review -> /draft` 这种分段式 HITL 流程

## 按方法阅读 service

### `generate_plan`
阅读位置：[chapter_service.py](/c:/project/generateNovel/backend/src/novel_assist/api/chapter_service.py)

阅读重点：
1. `build_initial_state()` 建默认状态
2. `overrides` 覆盖默认字段
3. 重置审核相关字段
4. 调 `plotting_node`
5. 调 `rag_recall_node`
6. 设置 `HumanReviewRequired`
7. 存储章节状态

这条链路对应的 API：
- `POST /chapters/{chapter_id}/plan`

### `get_review_task`
阅读重点：
- 它不自己组装数据
- 它直接委托给 store 层

这条链路对应的 API：
- `GET /chapters/{chapter_id}/review-task`

你读这里时，要顺手跳到：
- [jsonl_graph_store.py](/c:/project/generateNovel/backend/src/novel_assist/stores/jsonl_graph_store.py)

### `get_chapter_state`
阅读重点：
- 它是开发者模式调试入口
- 直接取原始状态快照

这条链路对应的 API：
- `GET /chapters/{chapter_id}/state`

### `submit_review`
阅读重点：
1. 先查章节状态
2. 把前端传来的审核结果写进 state
3. 强制 `enforce_state_review_status = True`
4. 调 `human_agenda_review_gate`
5. 保存更新后的 state

这条链路对应的 API：
- `POST /chapters/{chapter_id}/review`

### `generate_draft`
阅读重点：
1. 查章节状态
2. 检查是否已审核通过
3. 调 `draft_writer_node`
4. 调 `critic_node`
5. 用 `route_after_critic` 决定是否继续
6. 通过时调 `memory_harvester_node`
7. 保存状态

这条链路对应的 API：
- `POST /chapters/{chapter_id}/draft`

这条方法是“代码上最接近 workflow 的手动编排版本”。

## 再往下看节点

### 先看状态契约
在看 node 之前，先看 [novel_state.py](/c:/project/generateNovel/backend/src/novel_assist/state/novel_state.py)

重点理解：
- 全局共享 state 长什么样
- 哪些字段属于：
  - 追踪字段
  - 上帝视角字段
  - 审核字段
  - 产物字段
  - 运行配置

如果这里没看明白，后面的节点会越看越乱。

### 再看各 node
建议顺序：

1. [plot_planner.py](/c:/project/generateNovel/backend/src/novel_assist/nodes/plot_planner.py)
- 负责生成或刷新 `chapter_agenda`
- 会重置审核相关字段

2. [rag_recall.py](/c:/project/generateNovel/backend/src/novel_assist/nodes/rag_recall.py)
- 负责生成 `rag_recall_summary`
- 负责构造 `rag_evidence`
- 负责写召回审计事件

3. [human_review_gate.py](/c:/project/generateNovel/backend/src/novel_assist/nodes/human_review_gate.py)
- 负责根据审核状态生成 `approved_*`
- 负责写审核审计事件

4. [draft_writer.py](/c:/project/generateNovel/backend/src/novel_assist/nodes/draft_writer.py)
- 负责审核后写稿
- 负责构造 prompt
- 负责阻止未审核状态进入写稿

5. [critic_reviewer.py](/c:/project/generateNovel/backend/src/novel_assist/nodes/critic_reviewer.py)
- 负责规则检查
- 负责维护 `rewrite_count`

6. [memory_harvester.py](/c:/project/generateNovel/backend/src/novel_assist/nodes/memory_harvester.py)
- 负责章节通过后的轻量记忆沉淀

## 路由与状态机怎么读
看完 node 之后，再回去看：
- [routing.py](/c:/project/generateNovel/backend/src/novel_assist/state/routing.py)
- [workflow.py](/c:/project/generateNovel/backend/src/novel_assist/graph/workflow.py)

这样你会更容易理解：
- `route_after_human_review`
- `route_after_critic`
- 为什么 workflow 是自动机
- 为什么 service 是 workflow 的分段手动编排版

如果你一开始就先看 workflow，很容易只看到图，不知道每个节点实际改了哪些字段。

## 最后看存储层
建议最后看 `stores`

阅读顺序：
1. [graph_store.py](/c:/project/generateNovel/backend/src/novel_assist/stores/graph_store.py)
2. [factory.py](/c:/project/generateNovel/backend/src/novel_assist/stores/factory.py)
3. [jsonl_graph_store.py](/c:/project/generateNovel/backend/src/novel_assist/stores/jsonl_graph_store.py)
4. [neo4j_graph_store.py](/c:/project/generateNovel/backend/src/novel_assist/stores/neo4j_graph_store.py)

为什么最后看：
- 因为 store 解决的是“怎么存”
- 只有在你先知道“业务流里什么时候要存、什么时候要取”之后，再看 store 才不会抽象过头

重点理解：
- `save_chapter_state`
- `get_chapter_state`
- `get_review_task`
- `persist_rag_recall_event`
- `persist_human_review_event`

## 阶段四新增代码你要重点看的点

### 1. `/workbench`
文件：
- [app.py](/c:/project/generateNovel/backend/src/novel_assist/api/app.py)
- [workbench.html](/c:/project/generateNovel/backend/src/novel_assist/api/workbench.html)

你要看的是：
- 页面动作是怎么映射到 API 的
- 使用者模式和开发者模式差别在哪

### 2. 统一错误返回
文件：
- [app.py](/c:/project/generateNovel/backend/src/novel_assist/api/app.py)
- [schemas.py](/c:/project/generateNovel/backend/src/novel_assist/api/schemas.py)

你要看的是：
- 自定义异常怎么定义
- 异常处理器怎么挂到 FastAPI
- 为什么错误不再直接返回一个随意字符串

### 3. 状态查看接口
文件：
- [app.py](/c:/project/generateNovel/backend/src/novel_assist/api/app.py)
- [chapter_service.py](/c:/project/generateNovel/backend/src/novel_assist/api/chapter_service.py)

你要看的是：
- 开发者模式如何拿到完整 state
- 为什么这个接口对调试阶段四特别有用

## 最后给你的阅读方法建议
不要按“目录树从上到下”机械读，建议按下面顺序跳着看：

1. 一个 API 路由
2. 这个路由用到的 schema
3. 这个路由调用的 service 方法
4. 这个 service 方法调用的 node
5. 这个 service 方法调用的 store
6. 最后再回头看 workflow/routing

这样你每次都能顺着一条真实调用链读，不容易迷路。
