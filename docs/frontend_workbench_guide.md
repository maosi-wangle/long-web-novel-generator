# 前端工作台使用指南

## 目的
这份文档说明如何使用阶段四工作台 `/workbench`，以及前端应如何理解后端接口契约。

## 当前实现方式
当前 workbench 不是单独的前端工程，也没有引入 React、Vue、Gradio 或 Streamlit。

- 页面文件是 `backend/src/novel_assist/api/workbench.html`
- 样式使用原生 CSS
- 交互使用原生浏览器 JavaScript + `fetch`
- 页面由 FastAPI 通过 `GET /workbench` 直接返回

## 启动后端
在项目根目录执行：

```powershell
$env:API_PORT="9005"
python backend/src/novel_assist/cli/run_api.py
```

启动后访问：

- `http://127.0.0.1:9005/workbench`
- `http://127.0.0.1:9005/docs`

## 工作台模式

### 使用者模式
适用于正常章节工作流。

主要操作：
- 创建小说
- 准备下一章
- 生成计划
- 获取审核任务
- 提交审核结果
- 生成初稿

主要区域：
- Chapter Control
- Review Desk
- Evidence Cards
- Draft & Critic

界面行为补充：
- `Chapter Shelf` 在章节很多时会启用内部滚动，避免整页被几百章列表无限拉长

### 开发者模式
适用于前后端联调和问题排查。

额外可见内容：
- 最近一次请求载荷
- 最近一次响应载荷
- 原始章节状态
- 统一错误对象

额外操作：
- `Inspect Raw State`

## 核心使用流程

### 0. 创建空小说（可选）
填写 `Novel ID` 与 `Novel Title`，点击 `创建小说`

调用接口：
- `POST /novels`

预期结果：
- 新小说即使还没有章节，也会出现在 `Novel Shelf`
- `GET /novels/{novel_id}/chapters` 会返回空章节列表
- 之后可以继续为这部小说创建第一章

### 1. 生成计划
点击 `Generate Plan`

调用接口：
- `POST /chapters/{chapter_id}/plan`

预期结果：
- `agenda_review_status = pending`
- `rag_recall_summary` 有值
- `rag_evidence` 有值
- 返回 `recall_trace_id`
- 当章节号大于 `1` 且同小说下已有上一章时，后端会自动继承上一章的连续性上下文，例如 `previous_chapter_ending`

### 1.5 准备下一章
点击 `准备下一章`

当前页面行为：
- 如果当前小说下已有章节，页面会以“最后一章”为基准，自动递增 `chapter_number`
- 会为你生成下一个默认 `chapter_id`
- 会清空新章的 `chapter_agenda`、证据、草稿、审核结果
- 会保留当前小说的设定字段，便于继续往下写
- 真正点击 `Generate Plan` 时，后端还会继续自动补齐上一章衔接字段

### 2. 获取审核任务
点击 `Fetch Review Task`

调用接口：
- `GET /chapters/{chapter_id}/review-task`

预期结果：
- 返回当前审核页需要的数据
- 返回最新召回事件快照
- 返回最新审核事件快照
- 当前页面会同步回填 `Review Notes`、`Approved Agenda`、`Approved Recall Summary`

### 3. 提交审核
设置以下字段：
- `Review Decision`
- `Review Notes`
- 可选填写 `Approved Agenda`
- 可选填写 `Approved Recall Summary`

然后点击 `Submit Review`

调用接口：
- `POST /chapters/{chapter_id}/review`

预期结果：
- `agenda_review_status` 更新
- 返回 `review_trace_id`
- `approved_*` 字段被填充

### 4. 生成初稿
点击 `Generate Draft`

调用接口：
- `POST /chapters/{chapter_id}/draft`

审核通过后的预期结果：
- `draft`
- `draft_word_count`
- `critic_feedback`
- `rewrite_count`
- 当前页面会把 `draft` 和 `critic_feedback` 同步展示到右侧面板

审核未通过时的预期结果：
- HTTP `409`
- 返回统一错误对象，且 `error_code = HUMAN_REVIEW_REQUIRED`

当前页面行为：
- 当 `agenda_review_status !== "approved"` 时，`Generate Draft` 按钮应保持禁用
- 当切换章节卡片时，页面应从 `GET /chapters/{chapter_id}/state` 回填该章节已保存的表单字段与输出结果
- 当切换小说卡片时，页面会清空当前章节选择与右侧章节输出区，避免把上一章的数据误看成当前小说的数据
- 当点击 `准备下一章` 时，页面会按当前小说的最后一章生成下一章编号，避免因为选中旧章节而重复占用章节号

## 前端需要重点理解的字段

### `agenda_review_status`
- 含义：当前审核状态，只表达这一件事
- 合法值：
  - `pending`
  - `approved`
  - `rejected`
  - `edited`

### `approved_chapter_agenda`
- 含义：最终允许进入 `DraftWriter` 的细纲
- 为空表示：
  - 还没审核
  - 或审核未通过

### `audit_warning`
- 含义：审计写入告警
- 这不自动等于业务失败

### `error`
- 含义：当前步骤的业务错误信息
- 在 draft 响应中，它表示初稿生成是否成功完成

## 统一错误格式
前端应当按如下统一结构处理业务错误和校验错误：

```json
{
  "error_code": "REQUEST_VALIDATION_ERROR",
  "message": "Request validation failed.",
  "detail": [...],
  "trace_id": ""
}
```

前端处理建议：
- 逻辑分支优先根据 `error_code`
- 用户提示优先显示 `message`
- `detail` 只在开发者模式中展示

## 为什么证据用卡片展示
这里的“卡片”不是特定框架组件要求，只是把每条证据用一个独立信息块展示：

- 标题
- 证据片段
- 分数
- 来源 ID

这样比直接打印 JSON 更适合人工审核，因为阅读速度更快、信息层次更清晰。

## 推荐前端开发顺序
1. 先把 `/novels`、`POST /novels`、`/plan` 和 `/review-task` 展示稳定下来
2. 再实现审核提交 UI
3. 用 `agenda_review_status === "approved"` 控制 draft 按钮是否可操作
4. 切换章节时，用 `/state` 回填当前章节的已保存输入、审核字段和 draft/critic 输出
5. 切换小说时，显式处理“未选章节”的页面状态
6. 再补开发者模式里的原始状态和请求/响应日志
7. 再把 `latest_recall_event` 和 `latest_review_event` 以更清晰的方式展示出来
8. 工作流稳定后再优化样式与导航
