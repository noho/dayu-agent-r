# Plan Re-Review: WU-CLI-ACTIVITY-01 Follow-up (MiMo)

## Review Metadata

- **Reviewer**: AgentMiMo
- **Review type**: focused re-review（验证 accepted findings 修复情况）
- **Target**: `docs/host/host-issues/wu-cli-activity-01-followup-delta-eventlog-projection-catchup-plan.md`（revised）
- **Original review**: `docs/reviews/plan-review-20260618-063322.md`
- **Fix artifact**: `docs/reviews/plan-review-fix-20260618-codex-wu-cli-activity-01-followup.md`
- **DS review**: `docs/reviews/plan-review-20260618-063418-ds-wu-cli-activity-01-followup.md`
- **Date**: 2026-06-18
- **Branch**: `wu-cli-activity-01`

## Scope

Focused re-review：逐条验证 MiMo F1/F2/F3 和 DS-01~DS-06 在 revised plan 中是否已修复。不扩展 scope，除非 fix 引入了新的 blocker。

## Finding Status

### MiMo F1 — after-commit/after-compact latency safety bound 被一并移除

**状态：已修复**

Revised plan 在 Implementation Decision #6 中明确区分了两种语义：

- **required correctness catch-up**：删除 `MemoryProjectionCatchupBudget` 和 `BUDGET_EXHAUSTED`，循环到 target / idle / failure。语义预算移除。
- **after-commit / after-compact hot path**：不得执行无界同步补账。二选一：(1) 改为 `run_conversation_memory_projection_maintenance(...)` 或等价 helper，只接受 page size 与命名常量 page cap，达到 cap 时返回 maintenance incomplete，不产生 required cursor failure；(2) 如果 maintenance helper 会让调用面膨胀，直接移除机会性 projection hook。

Revised plan Slice 4 对应更新了 allowed files（保留 `open_host.py`、`dispatch.py`），exact changes 明确要求 hot-path opportunity path 不能调用 required catch-up，测试要求断言 after-commit 不调用 required catch-up 且若保留 maintenance 则断言最多处理命名常量允许的 page 数。

代码证据验证：`open_host.py:164-169` 当前使用 `_OPPORTUNISTIC_AFTER_COMMIT_MEMORY_PROJECTION_BATCH_COUNT`；`dispatch.py:338-344` 使用 `_OPPORTUNISTIC_AFTER_COMPACT_MEMORY_PROJECTION_BATCH_COUNT`。Revised plan 正确保留了这些作为 latency-only bound 的语义空间，不再把它们删除。

结论：F1 核心关切（区分 semantic budget 和 latency safety bound）已被 plan 纳入。implementation agent 有明确的二选一路径，且测试覆盖 latency bound。

### MiMo F2 — Filter-aware covered cursor 实现细节需要更精确规格

**状态：已修复**

Revised plan Implementation Decision #3 补充了完整的边界不变量：

- 空 EventLog / `cursor` 已在 latest row 之上：返回 `rows=()`、`covered_event_sequence=cursor`、`covered_event_id=None`。
- `cursor` 正好等于 latest row：返回 `covered_event_sequence=cursor`、`covered_event_id=None`。
- 有匹配 row 且达到 page limit：covered cursor 是最后一条匹配 row。
- 未达到 page limit：covered cursor 是 `cursor` 之后、读边界之内可证明的最大真实 EventLog row。**新增关键约束**：若 `max_event_sequence` 超过实际 latest，只能覆盖到实际 latest row；若 `max_event_sequence` 在 EventLog 范围内但没有精确 row，只能覆盖到 `<= max_event_sequence` 的最近真实 row。
- `cursor` 与读边界之间没有真实 row：返回 `covered_event_sequence=cursor`、`covered_event_id=None`，不得返回不存在的 sequence。
- **匹配 rows 查询与 covered row 查询必须在调用方提供的同一个 transaction 内完成**（同时修复了 DS-05）。

Revised plan Slice 3 测试要求新增：
- 空 EventLog 返回 `covered_event_sequence=cursor`、`covered_event_id=None`
- `max_event_sequence` 超过 actual latest 时 covered cursor 是 actual latest
- `max_event_sequence` 没有精确 row 时 covered cursor 是最近真实 row `<= max_event_sequence`

代码证据验证：`durable/projection.py:152` `advance_projection_checkpoint` 接受 `event_sequence` 和 `event_id` 参数，要求 `event_id` 引用真实 EventLog row。Revised plan 的规格确保 `covered_event_id` 要么为 `None`（不推进），要么引用真实 row。

结论：F2 规格缺口已完全填补，边界场景有明确语义和测试覆盖。

### MiMo F3 — Slice 5 filter 共源方案存在 import cycle 风险但未明确偏好

**状态：已修复**

Revised plan 固定使用方案 2（模块级 helper 作为单一 filter 真源）：

- Implementation Decision #7：`dayu/host/durable/memory.py` 提供模块级 `conversation_memory_projection_event_filter() -> ProjectionEventFilter`。
- `ConversationMemoryProjectionConsumer.__init__` 调用该 helper 设置 `event_filter`。
- Inline repair 也调用同一 helper；不得实例化 consumer 只为读取 filter，不得把 memory event type tuple 复制回 `run_input.py`。
- Stop condition 明确：如果 helper 放置位置导致 import cycle，停止并回到设计讨论；不得退回 consumer 实例读取 filter，也不得把 memory event type tuple 复制回 `run_input.py`。

代码证据验证：`run_input.py:1211` 已 import `project_conversation_memory_event` from `durable.memory`，import direction 已存在。方案 2 不引入新依赖方向。

结论：F3 不确定性已消除。plan 明确偏好 helper 方案，stop condition 兜底 import cycle 风险。

### DS-01 — design.md 第 3213 行 hot path 约束被移除但无替代保护

**状态：已修复**

Revised plan 与 MiMo F1 修复同源。Implementation Decision #6 和 Slice 4 共同确保：

- Required correctness path：无语义预算，追到 target / idle / failure。
- After-commit / after-compact：不得无界同步补账，只能 bounded latency-only maintenance 或移除 hook。
- Design Alignment 段明确要求保留 `docs/host/design.md` 的 hot path 约束，不把去预算化解释成允许无界同步补账。

结论：DS-01 的两条并列硬约束（"执行 bounded catch-up" 和 "不得无上限同步补账"）在 revised plan 中都有对应处理。

### DS-02 — plan 声明"Public Host API 无计划变更"但行为确已变更

**状态：已修复**

Revised plan Contract 段改为："Public Host API：签名无计划变更；但 EventLog-backed stream / read 行为会变更，默认不再返回 `content_delta`、`reasoning_delta`、`tool_call_delta` per-delta rows。"

结论：行为变更已显式声明，不再与 Success Signals 矛盾。

### DS-03 — covered_event_sequence 在空 EventLog 或 max_event_sequence 无对应行时未定义行为

**状态：已修复**

与 MiMo F2 同源修复。Revised plan Implementation Decision #3 已补充空 EventLog、cursor at/beyond latest、`max_event_sequence` 超出 actual latest、`max_event_sequence` 无精确 row 的完整边界不变量。

结论：DS-03 覆盖的边界场景已在 revised plan 中冻结语义。

### DS-04 — _MEMORY_EVENT_TYPES 与 _EVENT_TYPE_FILTER 当前语义等价，plan 动机高估严重性

**状态：已修复**

Revised plan Motivation 段改为："当前 `_MEMORY_EVENT_TYPES` / `_is_memory_projection_row` 与 Conversation Memory consumer 的 filter 语义等价，但它们是两份独立列表；未来 memory event type 调整时容易漂移。计划只做最小共源化。"

措辞从"会看到不同 material"改为"语义等价...未来容易漂移"，准确反映了 DRY 动机而非夸大为当前已存在的不一致。

结论：DS-04 动机文字已修正，不再误导 implementation agent 过度重构。

### DS-05 — Slice 3 filter-aware read 函数的事务边界未显式规定

**状态：已修复**

Revised plan Implementation Decision #3 新增："匹配 rows 查询与 covered row 查询必须在调用方提供的同一个 transaction 内完成。"

Slice 3 Exact changes 也新增："所有查询必须在调用方提供的同一个 transaction 内完成，包括 matching rows 查询和 covered row 查询。"

结论：事务边界已作为 durable primitive contract 明确规定。

### DS-06 — memory_projection_catchup_batch_size 配置字段重命名未被考虑

**状态：已修复**

Revised plan Non-goals 段改为："不移除或重命名 `memory_projection_catchup_batch_size` 配置字段；本 WU 必须更新 docstring / README / design 表述，明确它是内部 page size，不是单次 catch-up 的语义预算。"

Docs Decision 段也新增："必须更新相关配置 docstring / README / design wording，说明 `memory_projection_catchup_batch_size` 是内部 page size，不是 semantic budget；本 WU 不重命名该字段。"

结论：DS-06 的核心关切（旧名字误导）已通过文档消歧处理；重命名明确 deferred 到后续 WU。

## New Blocker Check

Revised plan 未引入新的 blocker。Fix 改动集中在规格补充、措辞修正和约束显式化，不改变 plan 的架构方向、slice 划分或 implementation boundary。

## Conclusion

**pass**

所有 accepted findings（MiMo F1/F2/F3、DS-01~DS-06）均已在 revised plan 中修复。修复方式为规格补充、措辞修正和约束显式化，未引入新的 blocker。Plan 可以进入 implementation gate。
