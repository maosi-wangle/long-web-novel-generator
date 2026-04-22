# Context Budget Design

## 1. 目标

本设计用于解决 `DetailOutlineAgent` 与 `WriterAgent` 在长篇连载场景下的上下文膨胀问题。

目标：

- 为不同 Agent 设定明确的上下文预算，而不是无限追加历史内容。
- 在预算充足时，优先使用正常上下文、RAG 命中、人工反馈。
- 在预算逼近上限时，优先裁剪或压缩低优先级上下文，避免核心设定丢失。
- 将“章节正文”逐步转换为结构化记忆，而不是长期依赖原文拼接。
- 保证 Writer 不读取完整全局大纲，只读取受控上下文。
- 为后续 function calling / MCP 暴露标准化的上下文组装与压缩能力。

非目标：

- 不追求把所有历史章节都塞进 prompt。
- 不追求单纯的自然语言摘要。
- 不让每个 Agent 自己决定如何随意裁剪上下文。

## 2. 设计原则

### 2.1 分层而不是堆叠

上下文分为多个层级，每层有独立预算与优先级。

### 2.2 先结构化，再压缩

章节归档时即生成结构化记忆；预算超限时优先使用结构化记忆，而不是临时压缩整章原文。

### 2.3 硬状态永不主动丢弃

角色状态、世界规则、未闭合伏笔、禁止揭示、人工 sticky 约束属于高优先级“硬记忆”，不参与普通裁剪。

### 2.4 RAG 是补充，不是主记忆

RAG 命中优先用于补充细节和原文证据，预算紧张时最先降级或移除。

### 2.5 Detail 与 Writer 的可见上下文不同

- `DetailOutlineAgent` 可以读取全局大纲切片。
- `WriterAgent` 不读取完整总纲，只读取 `writer_packet`、必要状态、局部历史和少量 RAG。

### 2.6 上下文由统一组件组装

禁止每个 Agent 各自手工拼 prompt。上下文必须通过统一的 `ContextAssembler` 和 `ContextBudgetManager` 产出。

## 3. 适用对象

### 3.1 DetailOutlineAgent

用途：

- 为目标章节生成细纲
- 维持章节级剧情推进
- 控制伏笔推进与回收节奏

可见信息：

- 当前章节对应的大纲切片
- 当前 act 摘要
- 最近章节结构化记忆
- 关键历史状态
- 未闭合伏笔
- 人工 sticky 约束
- 少量 RAG 命中

### 3.2 WriterAgent

用途：

- 只根据局部执行包写正文
- 避免全知视角和越界剧透

可见信息：

- `writer_packet`
- 当前章必要约束
- 最近章节结构化记忆
- 角色/世界/时间线必要状态
- 与当前 scene 强相关的少量 RAG 命中
- 人工 sticky 约束

不可见信息：

- 完整全局大纲
- 与当前章无关的大量历史正文
- Detail Agent 的完整内部推理

## 4. 上下文层级

统一拆分为 5 层。

### L0 System / Role

内容：

- system prompt
- schema 说明
- 调用规范

特点：

- 必选
- 不可压缩
- 不参与裁剪

### L1 Current Task Context

内容：

- 当前章目标
- 当前章节标题
- 当前 act 切片
- `writer_packet`
- `forbidden_reveals`
- 当前任务需要的最近上下文

特点：

- 必选
- 可轻微压缩，但不主动丢弃

### L2 Sticky Constraints

内容：

- 人工反馈
- 多章持续约束
- 必须推进的伏笔
- 必须避免的剧情方向

特点：

- 高优先级
- 不主动丢弃
- 仅允许做字段级压缩

### L3 Structured Memory

内容：

- 章节胶囊
- arc 胶囊
- 角色状态
- 世界状态
- 时间线
- 未闭合伏笔表

特点：

- 主历史记忆层
- 可做层级降级
- 不直接依赖原文

### L4 Retrieval Evidence

内容：

- RAG 命中原文片段
- RAG 压缩片段

特点：

- 低优先级
- 优先压缩
- 优先丢弃

## 5. 优先级模型

建议引入固定优先级。

| 优先级 | 名称 | 示例 | 可压缩 | 可丢弃 |
|---|---|---|---|---|
| P0 | 核心框架 | system、schema、当前任务必要字段 | 否 | 否 |
| P1 | 强约束 | sticky constraints、forbidden reveals、未闭合关键伏笔 | 是 | 否 |
| P2 | 硬状态 | character/world/timeline/open loops | 是 | 否 |
| P3 | 结构化历史 | chapter memory、arc memory | 是 | 条件可丢弃较旧项 |
| P4 | 压缩检索结果 | compact rag hits | 是 | 是 |
| P5 | 原始检索片段 | 原始 chunk 文本 | 是 | 是 |

预算超限时的处理顺序：

1. 删除 P5
2. 压缩或删除 P4
3. 将 P3 从章节胶囊降级为 arc 胶囊
4. 极限情况下只保留最近章节胶囊和关键状态
5. P0-P2 不主动移除

## 6. Token 预算

### 6.1 预算不是单一总量，而是分桶

每个 Agent 使用单独预算配置。

### 6.2 建议预算

#### DetailOutlineAgent

建议总预算：`24k`

| 桶 | 预算 |
|---|---:|
| L0 system / schema | 3k |
| L1 current task | 5k |
| L2 sticky constraints | 3k |
| L3 structured memory | 7k |
| L4 retrieval evidence | 3k |
| safety margin | 3k |

#### WriterAgent

建议总预算：`16k`

| 桶 | 预算 |
|---|---:|
| L0 system / schema | 2.5k |
| L1 writer packet | 5k |
| L2 sticky constraints | 2.5k |
| L3 structured memory | 3k |
| L4 retrieval evidence | 2k |
| safety margin | 1k |

### 6.3 安全阈值

定义三个区间：

- `normal`: 使用完整预算的 0% - 75%
- `warning`: 75% - 90%
- `critical`: 90% - 100%

在不同区间采用不同降级策略：

- `normal`: 正常使用上下文，不触发压缩
- `warning`: 压缩 RAG，减少历史原文
- `critical`: 强制只保留结构化记忆，丢弃所有低优先级原文

## 7. 结构化记忆模型

### 7.1 章节胶囊 Chapter Memory

每章归档后，额外生成：

`data/projects/{project_id}/chapter_memory/0004.json`

建议结构：

```json
{
  "chapter_id": 4,
  "title": "旧日同窗",
  "one_line_summary": "主角在逃亡途中重遇旧友，建立临时同盟，但暴露了残卷线索。",
  "key_events": [
    "主角与旧日同窗重逢",
    "确认敌方已追踪到残卷气息",
    "决定转道黑水渡口"
  ],
  "new_facts": [
    "旧日同窗认识敌方外门执事",
    "残卷会在特定灵气波动下产生共鸣"
  ],
  "character_state_updates": [
    {
      "character": "主角",
      "change": "开始主动利用残卷作为诱饵"
    }
  ],
  "relationship_updates": [
    {
      "pair": ["主角", "旧日同窗"],
      "change": "从试探转为有限合作"
    }
  ],
  "world_state_updates": [
    "黑水渡口附近出现敌方巡查"
  ],
  "timeline_markers": [
    "逃离宗门后第3日"
  ],
  "locations_visited": [
    "山道驿站",
    "黑水渡口外"
  ],
  "foreshadowing_opened": [
    {
      "id": "fh_013",
      "setup": "残卷在黑水附近产生异常反应",
      "expected_payoff_window": "第6-8章"
    }
  ],
  "foreshadowing_progressed": [],
  "foreshadowing_closed": [],
  "unresolved_conflicts": [
    "敌方是否已经锁定主角真实路线"
  ],
  "important_quotes_or_rules": [
    "残卷在水属性灵气附近会产生异常共鸣"
  ],
  "importance_score": 0.78
}
```

### 7.2 Arc 胶囊 Arc Memory

多章合并后生成：

`data/projects/{project_id}/arc_memory/arc_01.json`

建议结构：

```json
{
  "arc_id": "arc_01",
  "chapter_range": [1, 5],
  "arc_summary": "主角从宗门覆灭中逃出，确认敌人追杀动机与残卷有关，并建立第一批盟友。",
  "must_remember": [
    "宗门残卷是敌方追杀核心目标",
    "旧日同窗已知主角真实身份",
    "黑水渡口线索仍未解"
  ],
  "open_foreshadowing_ids": [
    "fh_003",
    "fh_013"
  ],
  "major_character_changes": [
    "主角开始主动承担重建宗门责任"
  ],
  "major_relationship_changes": [
    "主角与旧日同窗从猜疑转为合作"
  ],
  "major_world_changes": [
    "敌方势力公开在外围布控"
  ],
  "open_conflicts": [
    "敌方上层为什么执着残卷"
  ]
}
```

### 7.3 硬状态存储

建议独立维护以下状态文件：

- `state/character_state.json`
- `state/world_state.json`
- `state/open_loops.json`
- `state/timeline.json`
- `state/sticky_constraints.json`

这些文件属于 P1/P2，不依赖章节摘要存在。

### 7.3.1 角色状态的时效性

`character_state` 不能只保存“最新状态文本”，因为角色状态是具有时效性的。

必须同时保留三层信息：

1. `current snapshot`
2. `state change log`
3. `effective range`

推荐设计：

- `character_state.json` 保存当前可直接给 Agent 使用的最新快照
- `timeline.json` 保存章节级事件时间线
- 每个 `chapter_memory` 中保存本章产生的 `character_state_updates`

建议结构：

```json
{
  "characters": [
    {
      "name": "主角",
      "current_status": {
        "realm": "炼气七层",
        "injury": "右臂轻伤，未痊愈",
        "equipment": ["残卷", "断剑"],
        "public_identity": "流亡弟子",
        "hidden_identity": "宗门残卷持有者",
        "mental_state": "高度警惕"
      },
      "last_updated_in_chapter": 8,
      "active_flags": [
        "被追杀",
        "不可信任陌生修士"
      ]
    }
  ]
}
```

同时在 `timeline.json` 中记录变化何时发生：

```json
{
  "entries": [
    {
      "chapter_id": 8,
      "entity": "主角",
      "field": "injury",
      "old_value": "无明显外伤",
      "new_value": "右臂轻伤，未痊愈",
      "reason": "第8章渡口冲突受伤"
    }
  ]
}
```

这样：

- Agent 默认读取 `current_status`
- 若需要追溯“这个状态什么时候变的”，再查 `timeline`
- 若需要理解该章新增了什么，再查 `chapter_memory`

### 7.3.2 更新机制

角色状态不应靠覆盖全文重写，而应走“增量更新”。

推荐在每章归档后执行：

1. 从正文与章节胶囊中抽取 `character_state_updates`
2. 对 `character_state.json` 做字段级 merge
3. 将变更写入 `timeline.json`
4. 若新状态只在短时间有效，则写入 `effective_until`

短期状态建议结构：

```json
{
  "name": "主角",
  "temporary_status": [
    {
      "field": "injury",
      "value": "右臂轻伤，影响挥剑",
      "effective_from_chapter": 8,
      "effective_until_chapter": null
    }
  ]
}
```

当后续章节恢复伤势时，不是简单删除，而是写入新的更新：

- chapter 10: `injury -> 基本恢复`

随后由状态更新器把旧临时状态标记失效，或更新其 `effective_until_chapter=9`。

### 7.3.3 给 Agent 的读取规则

- `DetailOutlineAgent`：
  - 读取角色最新快照
  - 读取最近若干章的关键状态变化
- `WriterAgent`：
  - 默认只读取当前快照
  - 若当前章依赖近期状态变化，再附带最近 1-2 条 timeline 变化

这样可以避免把完整角色历史全塞进 prompt，同时又保留时效性。

### 7.4 Sticky Constraints

建议结构：

```json
{
  "items": [
    {
      "id": "sc_001",
      "source": "human_review",
      "scope": "chapter_5_to_7",
      "priority": "high",
      "instruction": "第5到第7章不要揭示师尊真实身份",
      "rationale": "保留后续反转空间",
      "active": true
    }
  ]
}
```

## 8. RAG 降级策略

### 8.1 默认策略

RAG 命中不应直接整段塞入 prompt，而应先转换为压缩命中。

建议结构：

```json
{
  "chunk_id": "chunk_0008_02",
  "chapter_id": 8,
  "why_relevant": "提到残卷共鸣机制，与当前章节冲突升级直接相关",
  "compressed_quote": "残卷在水属性灵气附近会产生异常共鸣，且可能暴露持有者位置"
}
```

### 8.2 降级顺序

1. 保留 `compressed_quote`
2. 删除低相关度 hit
3. 删除重复 hit
4. 删除整段原文 chunk

### 8.3 永不长期缓存原始 RAG 片段

原始 RAG 片段只用于当前次调用，不应该进入长期主上下文记忆层。

## 9. 正文压缩策略

### 9.1 不直接依赖自由摘要

正文压缩应优先变成结构化章节胶囊，而不是一句自然语言摘要。

### 9.2 超预算时的正文处理

当上下文超过阈值时：

1. 最近 1-2 章可保留章节胶囊
2. 更旧章节只保留 arc 胶囊
3. 如仍超限，再保留：
   - 未闭合伏笔
   - 关键事件
   - 角色状态变化
   - 世界规则变化

### 9.3 紧急压缩模式

如果历史章节尚未存在结构化胶囊，则可以调用 LLM 压缩。

压缩要求：

- 保留伏笔
- 保留重要事件
- 保留人物关系变化
- 保留能力/伤势/装备/身份变化
- 丢弃风格性描写、重复情绪、非关键对白

所有压缩结果必须输出为 Pydantic 结构化对象，而不是自由文本。

## 10. Detail 与 Writer 的上下文包

### 10.1 DetailOutlineContext

建议结构：

```json
{
  "project_meta": {},
  "current_chapter": {},
  "current_act": {},
  "recent_memories": [],
  "arc_memories": [],
  "character_state": {},
  "world_state": {},
  "open_loops": [],
  "sticky_constraints": [],
  "rag_hits": [],
  "budget_report": {}
}
```

字段说明：

- `current_chapter`: 当前章大纲切片
- `current_act`: 当前 act 摘要
- `recent_memories`: 最近 1-3 章章节胶囊
- `arc_memories`: 更旧章节的 arc 胶囊
- `open_loops`: 当前仍未闭合伏笔和冲突
- `rag_hits`: 少量压缩后的检索结果

### 10.2 WriterContext

建议结构：

```json
{
  "project_meta": {},
  "writer_packet": {},
  "recent_memories": [],
  "character_state": {},
  "world_state": {},
  "open_loops": [],
  "sticky_constraints": [],
  "rag_hits": [],
  "budget_report": {}
}
```

字段说明：

- 不含完整总纲
- 不含完整 Detail Agent 推理
- `writer_packet` 是 Writer 的主执行包

## 11. 统一组件设计

### 11.1 ContextAssembler

职责：

- 从不同来源收集候选上下文
- 生成 `DetailOutlineContext` / `WriterContext`

输入源：

- `project state`
- `outline slice`
- `detail outline`
- `chapter memory`
- `arc memory`
- `sticky constraints`
- `RAG results`
- `human review notes`

### 11.2 ContextBudgetManager

职责：

- 估算 token
- 按优先级裁剪
- 决定是否触发压缩

每个上下文项建议带元信息：

```json
{
  "source": "rag",
  "priority": "P4",
  "compressible": true,
  "droppable": true,
  "token_estimate": 380,
  "payload": {}
}
```

### 11.3 MemoryCompressor

职责：

- 将章节正文压缩为章节胶囊
- 将多章胶囊合并为 arc 胶囊
- 将长 RAG 命中压缩为短结构化命中

### 11.4 MemoryUpdater

职责：

- 在章节归档后更新：
  - `chapter_memory`
  - `character_state`
  - `world_state`
  - `open_loops`
  - `timeline`
- 在满足条件时合成 `arc_memory`

## 12. 生命周期

### 12.1 章节归档后

在 `archive_chapter -> chunking -> embedding -> FAISS/BM25` 之后，增加：

1. `extract_chapter_memory`
2. `update_character_state`
3. `update_world_state`
4. `update_open_loops`
5. `update_timeline`
6. `maybe_rollup_arc_memory`

### 12.2 review approve 后

若章节被人工编辑并重新归档，需要重新生成：

- `chapter_memory`
- `state/*`
- RAG 索引

### 12.3 detail / writer 调用前

统一经过：

1. `ContextAssembler.collect_candidates`
2. `ContextBudgetManager.estimate`
3. `ContextBudgetManager.downgrade_if_needed`
4. 输出最终上下文包

## 13. 压缩与降级算法

### 13.1 正常模式

使用：

- 最近章节胶囊
- 当前 act 胶囊
- 少量压缩 RAG
- 所有 active sticky constraints

### 13.2 Warning 模式

执行：

1. 只保留 top-k 压缩 RAG
2. 删除所有原始 chunk 文本
3. 最近章节只保留 1-2 章章节胶囊
4. 更旧内容切换为 arc 胶囊

### 13.3 Critical 模式

执行：

1. 删除全部原始 RAG
2. 删除低分压缩 RAG
3. recent memories 只保留最近 1 章章节胶囊
4. 历史只保留 arc 胶囊
5. 必保：
   - sticky constraints
   - character/world/timeline state
   - open loops
   - 当前任务包

## 14. 结构化输出要求

所有压缩、抽取、汇总过程都应优先使用 Pydantic schema，并通过 `instructor` 约束返回结构。

优先适用场景：

- `chapter -> chapter_memory`
- `chapter_memory[] -> arc_memory`
- `rag hits -> compact_rag_hits`
- `review note -> sticky_constraint`
- `chapter -> character/world/open_loop updates`

禁止：

- 仅返回自然语言摘要再靠字符串解析

## 15. 建议新增 Schema

建议新增这些 Pydantic 模型：

- `ChapterMemory`
- `ArcMemory`
- `CharacterState`
- `WorldState`
- `OpenLoopItem`
- `TimelineEntry`
- `StickyConstraint`
- `CompactRagHit`
- `DetailOutlineContext`
- `WriterContext`
- `ContextItem`
- `ContextBudgetReport`

## 16. 建议新增目录

```text
data/projects/{project_id}/
  chapter_memory/
    0001.json
    0002.json
  arc_memory/
    arc_01.json
  state/
    character_state.json
    world_state.json
    open_loops.json
    timeline.json
    sticky_constraints.json
```

## 17. 建议新增工具能力

若后续接 function calling / MCP，建议优先暴露：

- `context_build_detail`
- `context_build_writer`
- `memory_extract_chapter`
- `memory_rollup_arc`
- `memory_update_states`
- `memory_compact_rag_hits`
- `state_get_open_loops`
- `state_get_sticky_constraints`

## 18. 风险与对应策略

### 风险 1：摘要丢掉关键伏笔

策略：

- 伏笔必须结构化记录到 `foreshadowing_opened/progressed/closed`
- `open_loops` 独立存储

### 风险 2：Writer 因压缩过度写崩连续性

策略：

- Writer 永远读取 `character_state` / `world_state` / `open_loops`
- 不依赖单纯章节摘要

### 风险 3：人工反馈被埋没

策略：

- review note 分为普通 note 与 sticky constraints
- sticky constraints 单独存储、单独预算

### 风险 4：RAG 片段占满预算

策略：

- RAG 默认先压缩
- 原始 chunk 不进入长期上下文
- P5 最先删除

## 19. 推荐实现顺序

1. 定义 Pydantic schema
2. 在章节归档后生成 `chapter_memory`
3. 补 `state/*` 更新器
4. 实现 `ContextAssembler`
5. 实现 `ContextBudgetManager`
6. 将 Detail / Writer 改为统一上下文包输入
7. 增加 `arc_memory` rollup
8. 最后接 function calling / MCP

## 20. 最终结论

本设计的核心不是“上下文超限时再做摘要”，而是：

- 平时就把正文转换成结构化长期记忆
- 调用时按优先级分层组装
- 超限时做多级降级
- 永远保留硬状态、未闭合伏笔和人工 sticky 约束

这样才能在长篇连载中同时控制 token 成本、连续性和可维护性。
