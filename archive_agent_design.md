# Archive Agent Design

## 1. 目标

`ArchiveAgent` 的职责不是写正文，也不是规划剧情，而是将“已完成章节”转换为可长期使用的结构化记忆与状态增量。

核心目标：

- 从章节正文中提取结构化记忆
- 更新硬状态与时间线
- 更新未闭合伏笔、支线和任务状态
- 做连续性与硬约束审计
- 作为长期记忆写入的唯一可信入口

本设计必须与 [context_budget_design.md](./context_budget_design.md) 一致，并为后续的上下文预算系统提供稳定输入。

## 2. 先回答两个关键问题

### 2.1 会不会和 DetailOutline / Writer 重叠

会有“字段层面的重叠”，但不应该有“职责层面的重叠”。

当前系统里已有一些类似信息：

- `DetailOutlineAgent`
  - 负责生成 `writer_packet`
  - 会生成局部 continuity notes、forbidden reveals、scene briefs
- `WriterAgent`
  - 负责输出 `ChapterArtifact`
  - 会输出：
    - `summary`
    - `new_facts`
    - `foreshadow_candidates`
    - `referenced_chunks`

这些信息对运行阶段有用，但它们不应该直接成为长期状态系统的“权威来源”。

结论：

- `DetailOutlineAgent` 与 `WriterAgent` 可以继续输出“运行时辅助字段”
- `ArchiveAgent` 才是长期记忆、状态更新、时间线更新、伏笔状态更新的唯一权威提取器

### 2.2 会不会和 context budget design 冲突

不冲突，反而是天然上下游关系。

关系如下：

- `context_budget_design`
  - 解决“如何消费长期记忆”
- `ArchiveAgent`
  - 解决“如何生产长期记忆”

也就是说：

- `ArchiveAgent` 是 memory producer
- `ContextAssembler` / `ContextBudgetManager` 是 memory consumer

因此推荐顺序是正确的：

1. 先做 `context budget` 的 schema、装配器、预算器
2. 再做 `ArchiveAgent`
3. 最后把 `ArchiveAgent` 产出的 memory 接入 context assembler

前提是：先把 memory interface 定清楚。

## 3. 设计原则

### 3.1 单一权威写入者

长期记忆相关数据只能由 `ArchiveAgent + ArchiveOrchestrator` 写入。

包括：

- `chapter_memory`
- `arc_memory`
- `character_state`
- `world_state`
- `open_loops`
- `timeline`
- `sticky_constraints` 的结构化归档部分

### 3.2 其他 Agent 只提供运行时信号，不直接改长期状态

- `DetailOutlineAgent` 只负责当前章规划
- `WriterAgent` 只负责当前章正文
- 两者都不直接更新长期状态文件

### 3.3 长期状态更新必须是增量 patch

`ArchiveAgent` 不直接全量重写状态，而是输出 patch。

真正落盘由 `ArchiveOrchestrator` 合并。

### 3.4 章节抽取与状态写入解耦

章节抽取和状态落盘是两步：

1. `ArchiveAgent` 提取结构化结果
2. `ArchiveOrchestrator` 校验、merge、写盘

### 3.5 先兼容当前系统，再替换旧字段用途

短期内：

- `WriterAgent.summary/new_facts/foreshadow_candidates` 可以保留

长期：

- 上下文预算系统优先读取 `ArchiveAgent` 产物
- `WriterAgent` 的辅助字段只作为低信任运行时信息

## 4. 职责边界

## 4.1 DetailOutlineAgent

负责：

- 当前章细纲
- 当前章局部推进策略
- `writer_packet`

不负责：

- 更新长期状态
- 更新角色快照
- 更新世界状态
- 关闭或推进正式伏笔条目
- 更新时间线

## 4.2 WriterAgent

负责：

- 生成正文
- 生成本章运行时辅助字段

不负责：

- 写入长期记忆
- 更新状态文件
- 维护 open loops
- 正式做连续性审计结论

## 4.3 ArchiveAgent

负责：

- 从已归档正文提取结构化 memory
- 生成状态 patch
- 生成时间线 patch
- 生成 open loops patch
- 生成 constraint check report

不负责：

- 改写正文
- 决定后续剧情
- 解决 review

## 4.4 ArchiveOrchestrator

负责：

- 调用 `ArchiveAgent`
- 校验输出 schema
- 检查 patch 冲突
- merge 写盘
- 触发 RAG ingest / rebuild

## 5. 去重与解耦方案

这是本设计最关键的部分。

## 5.1 保留现有输出，但改变语义

当前 `WriterAgent` 的这些字段：

- `summary`
- `new_facts`
- `foreshadow_candidates`

短期继续保留，但语义改为：

- “写作阶段的自报告”
- 不是最终长期记忆
- 可以作为 `ArchiveAgent` 的辅助输入
- 不能直接写入 `state/*`

## 5.2 建立权威层级

建议采用以下信任级别：

| 来源 | 用途 | 信任级别 |
|---|---|---|
| `ChapterArtifact.markdown_body` | 正文证据 | 高 |
| `DetailOutline` | 原计划对照 | 高 |
| `WriterAgent.summary/new_facts/...` | 辅助提取线索 | 中 |
| `ArchiveAgent` 输出 | 结构化长期记忆候选 | 高 |

也就是说：

- `WriterAgent.new_facts` 可以帮助 `ArchiveAgent` 少漏
- 但最终写入的 `ChapterMemory.new_facts` 由 `ArchiveAgent` 决定

## 5.3 明确“谁产物进入 context budget”

进入 `context budget` 的长期记忆只来自：

- `chapter_memory`
- `arc_memory`
- `state/*`

不直接读取：

- `WriterAgent.summary`
- `WriterAgent.foreshadow_candidates`
- `DetailOutlineAgent.internal_reasoning_package`

这样上下文消费层不会和运行时字段绑死。

## 5.4 抽取接口统一，写入接口统一

即使未来还有别的 agent 输出辅助摘要，也必须经过：

- `ArchiveAgent.extract_*`
- `ArchiveOrchestrator.apply_*`

才允许进入长期记忆。

## 6. 与 Context Budget 的接口对齐

`context_budget_design.md` 里定义了未来要消费的数据：

- `chapter_memory`
- `arc_memory`
- `character_state`
- `world_state`
- `open_loops`
- `timeline`
- `sticky_constraints`

所以 `ArchiveAgent` 的输出必须直接对齐这些结构。

换句话说：

- `ContextAssembler` 不应该自己从正文重新抽取 memory
- `ContextAssembler` 只消费 `ArchiveAgent` 的标准产物

## 6.1 先做 Context Budget 也没问题

先实现 `context budget` 时，可以先做 provider 接口：

- `ChapterMemoryProvider`
- `ArcMemoryProvider`
- `CharacterStateProvider`
- `WorldStateProvider`
- `OpenLoopProvider`
- `StickyConstraintProvider`

在 `ArchiveAgent` 未完成前，可以先提供 fallback：

- 从已有 `chapter markdown`
- 从已有 `detail outline`
- 从已有 `rag hits`

临时构造简化 memory。

等 `ArchiveAgent` 完成后，再把 provider 切到正式 memory 文件。

这意味着：

- 先做 context budget 不会返工
- 只要接口先定好，后面替换 provider 即可

## 7. 输入

`ArchiveAgent` 每章处理时建议输入：

- `project_id`
- `project state`
- `chapter_id`
- `ChapterArtifact`
- `DetailOutline`
- 最近 1-2 章 `chapter_memory`
- 当前：
  - `character_state`
  - `world_state`
  - `open_loops`
  - `timeline`
  - `sticky_constraints`

辅助输入：

- `WriterAgent` 自报告字段
  - `summary`
  - `new_facts`
  - `foreshadow_candidates`

## 8. 输出

建议第一版输出 6 个结果。

### 8.1 ChapterMemory

章节级结构化胶囊。

### 8.2 CharacterStatePatch

角色状态增量更新，而不是完整快照。

### 8.3 WorldStatePatch

世界状态增量更新。

### 8.4 TimelinePatch

时间线事件与状态变化。

### 8.5 OpenLoopPatch

未闭合伏笔、冲突、任务状态的新增/推进/关闭。

### 8.6 ConstraintCheckReport

用于审计：

- 是否违背硬约束
- 是否提前揭示
- 是否时间线冲突
- 是否角色状态矛盾

## 9. Patch 模型

推荐所有 patch 都带以下通用字段：

```json
{
  "op": "add | update | close | remove",
  "entity_id": "xxx",
  "field": "xxx",
  "old_value": null,
  "new_value": null,
  "chapter_id": 5,
  "reason": "从本章正文抽取",
  "source_evidence": [
    "正文中的一句原文"
  ],
  "confidence": 0.92
}
```

这样方便：

- merge
- 回滚
- 人工审查
- debug

## 10. 状态文件

与 `context_budget_design.md` 保持一致：

```text
data/projects/{project_id}/
  chapter_memory/
    0001.json
  arc_memory/
    arc_01.json
  state/
    character_state.json
    world_state.json
    open_loops.json
    timeline.json
    sticky_constraints.json
  archive_reports/
    0001_constraint_check.json
    0001_archive_patch.json
```

建议新增一份 patch 落盘记录：

- `archive_reports/{chapter_id}_archive_patch.json`

这样后续修历史章时可以重放或回溯。

## 11. MCP 设计

## 11.1 MCP Resources

建议暴露：

- `project://{project_id}/state`
- `project://{project_id}/chapter/{chapter_id}`
- `project://{project_id}/detail-outline/{chapter_id}`
- `project://{project_id}/memory/recent`
- `project://{project_id}/state/character`
- `project://{project_id}/state/world`
- `project://{project_id}/state/open-loops`
- `project://{project_id}/state/timeline`
- `project://{project_id}/state/sticky-constraints`

## 11.2 MCP Tools

建议最小工具集：

- `archive.extract_chapter_memory`
- `archive.extract_character_state_patch`
- `archive.extract_world_state_patch`
- `archive.extract_timeline_patch`
- `archive.extract_open_loop_patch`
- `archive.check_constraints`
- `archive.apply_archive_result`
- `archive.rebuild_arc_memory`
- `rag.ingest_chapter`

更稳一点的方案是只暴露两个写入工具：

- `archive.propose_archive_result`
- `archive.apply_archive_result`

其中：

- `ArchiveAgent` 只负责 propose
- `ArchiveOrchestrator` 调用 apply

## 12. 工作流

建议流程：

1. `WriterAgent` 输出 `ChapterArtifact`
2. `workflow.archive_chapter()` 保存正文 markdown
3. `ArchiveOrchestrator.run_for_chapter(chapter_id)`
4. 读取当前章、细纲、状态与最近 memory
5. 调用 `ArchiveAgent`
6. 获得：
   - `ChapterMemory`
   - patches
   - `ConstraintCheckReport`
7. 校验 patch
8. merge 到：
   - `state/*`
   - `chapter_memory/*`
9. 触发：
   - `rag.ingest_chapter`
   - `maybe_rollup_arc_memory`
10. 若约束违规严重，则：
   - 自动标记 review 建议
   - 或要求人工介入

## 13. 约束审计策略

`ConstraintCheckReport` 建议分级：

- `info`
- `warning`
- `high`
- `blocking`

示例：

```json
{
  "violations": [
    {
      "type": "forbidden_reveal",
      "severity": "high",
      "message": "疑似提前揭示师尊真实身份",
      "evidence": [
        "……"
      ],
      "suggested_action": "request_review"
    }
  ]
}
```

处理建议：

- `info`: 只记录
- `warning`: 记录并提示
- `high`: 进入 review note
- `blocking`: 触发强制人工介入

## 14. 与现有代码的最小接入点

最适合接入的地方是当前：

- [app.py](/abs/path/C:/project/generateNovel3/src/app.py)
- [workflow.py](/abs/path/C:/project/generateNovel3/src/orchestrator/workflow.py)
- [human_tool.py](/abs/path/C:/project/generateNovel3/src/tools/human_tool.py)
- [rag_tool.py](/abs/path/C:/project/generateNovel3/src/tools/rag_tool.py)

推荐新增：

- `src/agents/archive_agent.py`
- `src/orchestrator/archive_orchestrator.py`
- `src/schemas/archive.py`
- `src/storage/memory_store.py`
- `src/tools/archive_tool.py`

## 15. 推荐实现顺序

为了避免和 context budget 互相卡住，推荐顺序如下。

### Phase 1

先实现 `context budget` 基础设施：

- memory schema
- provider interface
- context assembler
- budget manager

### Phase 2

实现 `ArchiveAgent` 的 schema 和 patch 模型：

- `ChapterMemory`
- `CharacterStatePatch`
- `WorldStatePatch`
- `TimelinePatch`
- `OpenLoopPatch`
- `ConstraintCheckReport`

### Phase 3

实现 `ArchiveAgent` 与 `ArchiveOrchestrator`

### Phase 4

将 context assembler 的 provider 切换到正式 memory 文件

## 16. 最终结论

`ArchiveAgent` 与 `DetailOutlineAgent` / `WriterAgent` 的确存在字段层面的重叠，但只要做这三个约束，就不会冲突：

1. `DetailOutlineAgent` / `WriterAgent` 的相关字段只算运行时辅助信息
2. 长期 memory/state 只能由 `ArchiveAgent` 生产
3. `ContextBudget` 只消费 `ArchiveAgent` 产物，不直接消费 writer/detail 的辅助字段

因此当前路线没有冲突：

- 先做 `context budget`
- 再做 `archive agent`

而且这样是最稳的顺序。
