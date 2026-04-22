# Outline Continuity Design

## 1. 目标

为下一本新小说增加一层独立的“大纲连续性机制”，解决以下问题：

- 相邻章节目标和事件不连贯
- 上一章 `hook` 在下一章没有被承接
- 新地点、新冲突、新任务突然出现，没有桥接
- `DetailOutlineAgent` 只能看见章节切片，但不知道“这一章必须先收什么尾”

这层机制位于：

- `OutlineAgent` 之后
- `DetailOutlineAgent` 之前
- `ArchiveAgent` 之外，但后续会与其协同

它的职责不是更新长期状态，而是保证“章节设计本身”连续。

## 2. 核心判断

当前系统里最缺的不是“记忆更多”，而是“章节义务传递”。

核心规则：

- 每章结尾留下的 `hook`，必须被视为下一章或后续若干章的显式义务
- 每章开头必须能从上一章结尾自然推出
- 如果下一章要切到新事件，必须有桥接说明
- 大纲不能只写“本章发生什么”，还要写“它如何从上一章接进来，又把什么交给下一章”

## 3. 与 ArchiveAgent 的边界

`Outline Continuity Layer` 负责：

- 检查章节设计是否连续
- 维护 hook/payoff/bridge
- 生成下一章必须承接的事项

`ArchiveAgent` 负责：

- 在正文完成后更新真实状态
- 更新角色、道具、时间线、open loops、关系变化

边界结论：

- 连续性设计问题，优先由 `Outline Continuity Layer` 解决
- 状态漂移问题，优先由 `ArchiveAgent` 解决
- 两者协同后，`DetailOutlineAgent` 才能既知道“该接什么”，也知道“现在是什么状态”

## 4. 新增字段

建议扩展 `ChapterPlan`，从“只描述本章内容”改成“描述本章在链条中的位置”。

### 4.1 ChapterPlan 新字段

```json
{
  "chapter_id": 8,
  "title": "血色试炼",
  "goal": "通过外部考验巩固地位",
  "beats": [],
  "hook": "战斗结束，李青看到对手眼中闪过一丝恐惧而非仇恨",
  "carry_in": [
    "上一章奸细潜入事件必须先得到处理或转化",
    "阵法图纸是否失窃需要明确",
    "团队内部信任裂痕仍在"
  ],
  "entry_state": [
    "队伍仍处于内部警惕状态",
    "李青已经锁定可疑对象但未公开处理"
  ],
  "exit_state": [
    "外部威胁升级，赵无极公开逼迫",
    "队伍内部暂时形成一致对外"
  ],
  "open_threads_created": [
    "擂台背后另有安排",
    "对手并非真正仇敌"
  ],
  "open_threads_resolved": [
    "奸细夜盗阵法图纸事件"
  ],
  "next_chapter_must_address": [
    "擂台异常反应的真实原因",
    "恐惧目光意味着什么"
  ],
  "transition_bridge": "奸细供出的情报把矛头引向赵无极布下的擂台"
}
```

### 4.2 字段说明

- `carry_in`
  本章开始前，必须承接的上文义务

- `entry_state`
  本章开头时的人物/局势起点

- `exit_state`
  本章结束后被推进出的新局势

- `open_threads_created`
  本章新开的线

- `open_threads_resolved`
  本章明确收掉的线

- `next_chapter_must_address`
  强约束式的下章承接事项

- `transition_bridge`
  本章为何能从上一章自然切过来的桥

## 5. 连续性检查规则

在全局大纲生成后，增加一次 `outline_continuity_pass`。

输入：

- `NovelOutline`
- 相邻章节对 `(chapter_n, chapter_n+1)`

输出：

- 修正后的 `NovelOutline`
- 每章连续性报告 `continuity_report`

### 5.1 必查项

1. 上一章 `hook` 是否被下一章承接
2. 下一章 `carry_in` 是否覆盖上一章未决义务
3. 下一章 `entry_state` 是否能从上一章 `exit_state` 推出
4. 是否存在突发新地点/新任务/新冲突但没有 `transition_bridge`
5. 是否存在上一章新开的高优先级线索，在下一章被无故遗忘
6. 相邻章节目标是否逻辑冲突

### 5.2 判定级别

- `normal`
  连续，无需修补

- `warning`
  可读性有轻微跳跃，但能解释

- `high`
  读者会明显感觉断层，需要补桥接

- `blocking`
  下一章无法从上一章推出，必须重写相邻章节设计

## 6. 自动修补策略

连续性机制不应只报错，还应能自动补一层最小修复。

### 6.1 可自动补的内容

- 给下一章补 `carry_in`
- 给上一章补 `next_chapter_must_address`
- 给下一章补 `transition_bridge`
- 给下一章前 1-2 条 `beats` 补承接动作

### 6.2 不自动补的内容

- 大规模重写整卷结构
- 修改核心主题或主线方向
- 推翻用户明确指定的章节目标

### 6.3 修补原则

- 优先补桥接，不先改主目标
- 优先让下一章“先收尾，再开新局”
- 若无法兼容，则标记 `blocking`，要求重新规划相邻章节

## 7. DetailOutlineAgent 接口改动

`DetailOutlineAgent` 后续生成细纲时，不应只读取当前 `ChapterPlan`，还应读取连续性包。

### 7.1 新输入包

```json
{
  "current_chapter": {},
  "previous_chapter": {},
  "carry_in": [],
  "entry_state": [],
  "transition_bridge": "",
  "next_chapter_must_address": [],
  "continuity_alerts": []
}
```

### 7.2 细纲生成要求

- 本章前段优先处理 `carry_in`
- 本章中段推进 `goal`
- 本章结尾再产出新的 `hook`
- 若 `carry_in` 未被消化，不允许直接跳入全新事件主轴

## 8. 与 Context Budget 的关系

这份设计与 `context_budget_design.md` 不冲突。

关系如下：

- `Outline Continuity Layer` 产生的是章节规划约束
- `Context Budget` 负责把这些约束安全装进上下文

后续可以在 `DetailOutlineContext` 里加入：

- `carry_in`
- `entry_state`
- `transition_bridge`
- `continuity_alerts`

其中优先级建议：

- `carry_in`: P0
- `entry_state`: P0
- `transition_bridge`: P1
- `continuity_alerts`: P1

## 9. 与 ArchiveAgent 的协同方式

当 `ArchiveAgent` 实装后，可以反向给连续性层提供真实验证。

### 9.1 协同方向

- 连续性层负责“计划承接”
- Archive 层负责“事实承接”

### 9.2 后续可加的检查

- 大纲里声明已解决的线，正文归档后是否真的解决
- 大纲里要求延续的线，正文归档后是否被遗漏
- `entry_state/exit_state` 与真实 `character_state/world_state` 是否偏离

也就是说：

- 先用连续性层修“规划”
- 再用 Archive 层修“执行”

## 10. 建议的数据结构

### 10.1 新 schema

建议新增：

- `src/schemas/continuity.py`

包含：

- `ChapterContinuity`
- `ContinuityIssue`
- `OutlineContinuityReport`

### 10.2 示例

```json
{
  "chapter_id": 8,
  "carry_in": [
    "处理奸细夜盗事件",
    "确认阵法图纸是否失窃"
  ],
  "entry_state": [
    "队伍内部不信任上升",
    "李青已锁定可疑人"
  ],
  "exit_state": [
    "赵无极的外部压力公开化"
  ],
  "transition_bridge": "奸细供出的线索将冲突引向赵无极布置的试炼擂台",
  "next_chapter_must_address": [
    "擂台试炼背后的真正目的"
  ]
}
```

## 11. 建议流程

### Phase 1

先补 schema 和 design，不改生成逻辑：

- `ChapterPlan` 扩展字段
- `continuity.py`
- `outline_continuity_design.md`

### Phase 2

实现 `outline_continuity_pass`

- 输入全局大纲
- 输出修正后大纲和报告

### Phase 3

把连续性包接进 `DetailOutlineAgent`

- 细纲必须读取 `carry_in`
- 细纲必须优先解决上一章遗留义务

### Phase 4

与 `ArchiveAgent` 联动做事实校验

## 12. 最小落地版本

如果只做最小可用版，建议先实现这三件事：

1. `ChapterPlan` 增加
   - `carry_in`
   - `exit_state`
   - `next_chapter_must_address`
   - `transition_bridge`

2. 全局大纲生成后执行一次 continuity pass

3. `DetailOutlineAgent` 强制读取上一章 `hook + carry_out + 当前章 carry_in`

这样即使 `ArchiveAgent` 还没上，下一本小说的大纲也会明显更连续。

## 13. 结论

要解决“上一章和下一章接不上”的问题，最先要修的是大纲阶段的连续性协议，而不是单纯增强记忆。

下一本小说的正确顺序应当是：

1. 先有全局大纲
2. 再做连续性校验与修补
3. 然后给 `DetailOutlineAgent`
4. 最后由 `ArchiveAgent` 在正文完成后更新真实状态

一句话概括：

- `Outline Continuity Layer` 保证章节之间“应该能接上”
- `ArchiveAgent` 保证正文之后“实际上没有接歪”
