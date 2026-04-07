# 前端工作台使用指南

## 目的
这份文档说明如何使用阶段四工作台 `/workbench`，以及前端应如何理解后端接口契约。

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
- 生成计划
- 获取审核任务
- 提交审核结果
- 生成初稿

主要区域：
- Chapter Control
- Review Desk
- Evidence Cards
- Draft & Critic

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

### 1. 生成计划
点击 `Generate Plan`

调用接口：
- `POST /chapters/{chapter_id}/plan`

预期结果：
- `agenda_review_status = pending`
- `rag_recall_summary` 有值
- `rag_evidence` 有值
- 返回 `recall_trace_id`

### 2. 获取审核任务
点击 `Fetch Review Task`

调用接口：
- `GET /chapters/{chapter_id}/review-task`

预期结果：
- 返回当前审核页需要的数据
- 返回最新召回事件快照
- 返回最新审核事件快照

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

审核未通过时的预期结果：
- HTTP `409`
- 返回统一错误对象，且 `error_code = HUMAN_REVIEW_REQUIRED`

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
1. 先把 `/plan` 和 `/review-task` 展示稳定下来
2. 再实现审核提交 UI
3. 用 `agenda_review_status === "approved"` 控制 draft 按钮是否可操作
4. 再补开发者模式里的原始状态和请求/响应日志
5. 工作流稳定后再优化样式与导航
