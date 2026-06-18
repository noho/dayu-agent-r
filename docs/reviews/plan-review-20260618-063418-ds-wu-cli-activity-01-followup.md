# Plan Review: WU-CLI-ACTIVITY-01 follow-up delta EventLog and projection catch-up

- **Reviewer**: AgentDS
- **Reviewed artifact**: `docs/host/host-issues/wu-cli-activity-01-followup-delta-eventlog-projection-catchup-plan.md`
- **Reviewed date**: 2026-06-18
- **Design truth**: `docs/host/design.md`; `docs/engine/design.md`
- **Control doc**: `docs/host/issues-implementation-control.md`
- **Branch**: `wu-cli-activity-01`

## Review scope

Adversarial review of the plan artifact for WU-CLI-ACTIVITY-01 follow-up. Focus areas as specified: motivation/root cause verification, removing default durable per-delta EventLog safety, removing semantic LIMIT budget coherence, filter-aware projection read correctness, slice code-generation-readiness and test sufficiency, blocking findings, overdesign, and hidden schema/API changes.

## Assumptions tested

1. Per-delta EngineEvents (`content_delta`, `reasoning_delta`, `tool_call_delta`) are currently default-durable in EventLog.
2. `ProjectionRunner._process_next_event` reads one EventLog row at a time without event-level filter.
3. `MemoryProjectionCatchupBudget` / `BUDGET_EXHAUSTED` is the semantic stop condition in production catch-up paths.
4. `_MEMORY_EVENT_TYPES` in `run_input.py` is an independent parallel copy of the memory consumer's event type filter.
5. Projection checkpoint schema allows `checkpoint_event_id` to reference any EventLog row (not just matching rows).
6. Consumer `event_filter` can be mechanically converted to durable read filter without schema changes.
7. Removing semantic budget from after-commit/after-compact catch-up won't cause unacceptable synchronous latency on the dispatch hot path.
8. Public read APIs (`read_session_host_events_after`, `stream_run_events`) remain correct when per-delta rows are removed from EventLog.

## Findings

### DS-01 未修复-高-design.md 第 3213 行"不得让 dispatch hot path 无上限同步补账"约束被移除但无替代保护

- **位置**: Goal / Design Alignment / Slice 4 / Risk 3
- **问题类型**: 架构边界 / 状态机漏洞
- **当前写法**: Plan 在 Design Alignment 段明确要求将 design.md:3213 的"超出 catch-up 执行预算时产生结构化 diagnostic"改为"page size 不是语义预算"。Slice 4 删除 `MemoryProjectionCatchupBudget` / `BUDGET_EXHAUSTED`，所有 after-commit / after-compact catch-up 变为无上限同步追平。Risk 3 承认"可能在包含大量 matching memory facts 的情况下同步执行较久"，但只写"deferred-with-owner，future projection scheduler WU"。
- **反例/失败场景**: 用户在一次 session 中连续触发多次 Run，每次 Run 产生数百条 `TOOL_RESULT_ACCEPTED`。在 compact 尚未触发时，after-commit memory catch-up 需要同步扫描并 apply 所有积累的 matching rows，block dispatch hot path 数秒甚至更久。当前 bounded budget 至少能限制单次同步追平的时间窗口。
- **为什么有问题**: `docs/host/design.md:3213` 明确写的是两条并列硬约束："Host 必须执行 bounded memory projection catch-up / rebuild 或在 policy 允许范围内做 inline delta repair；失败或超出 catch-up 执行预算时产生结构化 diagnostic" **与** "也不得让 dispatch hot path 无上限同步补账"。前者是行为描述，后者是硬约束。plan 修改了前者（改为 page-bounded），但移除了满足后者的唯一机制（semantic budget），且没有在本次 WU 中引入任何替代保护。Risk 3 把问题完全推迟给不存在的 future async projection worker，但在此期间 dispatch hot path 就是无上限同步补账。
- **直接证据**:
  - `docs/host/design.md:3213` 当前文字："也不得让 dispatch hot path 无上限同步补账"
  - Plan Design Alignment 段只要求修改"执行预算"表述，不提替代保护
  - Plan Decision 6："本 WU 不引入新的 stop budget；后续如需异步 projection worker，应作为独立 work unit 设计"
  - Plan Risk 3："该风险来自同步 projection 架构，不应继续用 LIMIT N 伪装 correctness。若需要异步 projection worker，后续独立 work unit 处理。"
- **影响**: dispatch hot path 可能被大量 matching memory facts 阻塞较长时间，违反 design.md 硬约束。若实现 agent 机械按 plan 执行，会在本次 WU 关闭后留下一个已知的无保护热路径。
- **建议改法和验证点**:
  1. 保留 `_after_commit_memory_projection_budget` 相关的 budget 构造逻辑，但把 budget 语义改为"单次最多扫描 N 个 EventLog row 的时间保护"，而不是"correctness 停止条件"——即 budget 耗尽时仍记录 diagnostic 但不触发 pre-dispatch failure，只记录后续仍有 unconsumed matching rows 需要后续 catch-up。
  2. 或者在 plan 中明确：本次 WU 接受 dispatch hot path 变为无上限同步补账，但必须在 design.md:3213 中显式记录该约束在当前 phase 被放松，并给出放松的明确理由、预期影响和触发后续 async worker WU 的量化条件（如 matching rows > N 时 alert）。
  3. 测试验证：构造大量 matching canonical facts（>1000），测量 after-commit catch-up 耗时并记录为已知 tradeoff。
- **修复风险（低/中/高）**: 低（方案 1 是局部保留现有逻辑，方案 2 只是文档裁决）
- **严重程度（高/中/低/严重）**: 高

### DS-02 未修复-中-plan 声明"Public Host API 无计划变更"但行为确已变更

- **位置**: Contract / Schema / State / Public API Changes
- **问题类型**: 契约缺失
- **当前写法**: Plan 在 Contract 段写"Public Host API：无计划变更"。同时 Success Signals 段写"`read_session_host_events_after`、`stream_run_events`、CLI activity backfill 不再从 EventLog 看到 per-delta rows"。
- **反例/失败场景**: 如果存在外部 consumer（例如 WeChat adapter、未来的 GUI 客户端）通过 `read_session_host_events_after` 读取 EventLog 并依赖 delta 事件实现自己的 streaming UI，升级后这些 consumer 会发现 stream 中没有 delta 事件，但 API signature 完全没变，没有编译期或类型系统提示。
- **为什么有问题**: API signature 不变不等于行为不变。per-delta 事件从 EventLog 默认移除是一个 material behavioral change。plan 在 Success Signals 中明确描述了行为变化，但在 Contract 段声明"无计划变更"——这两个声明矛盾。implementation agent 或未来的 API consumer 可能被"无计划变更"误导。
- **直接证据**:
  - Plan Contract 段："Public Host API：无计划变更。"
  - Plan Success Signals："`read_session_host_events_after`、`stream_run_events`、CLI activity backfill 不再从 EventLog 看到 per-delta rows"
  - Code evidence: `_ReadSessionHostEventsAfterOperation` (read_api.py:471) 直接调用 `read_events_after` 做 session_id 过滤；移除 delta rows 后返回的 batch 不再包含 delta 事件
  - Code evidence: `_StreamRunEventsOperation` (read_api.py:505) 同理
- **影响**: API consumer 行为静默变化；未来排障时可能误判为 bug
- **建议改法和验证点**: Contract 段改为"Public Host API 签名不变，但 EventLog-backed read path 默认不再包含 per-delta 事件（content_delta、reasoning_delta、tool_call_delta）；详见 Success Signals。"同时检查是否有任何 Host public API docstring 或 README 声称返回 delta 事件需要同步更新。
- **修复风险（低/中/高）**: 低
- **严重程度（高/中/低/严重）**: 中

### DS-03 未修复-中-`covered_event_sequence` 在空 EventLog 或 `max_event_sequence` 无对应行时未定义行为

- **位置**: Slice 3 / Implementation Decision 3 / Exact changes
- **问题类型**: 切片过粗 / 不可直接实施
- **当前写法**: Plan Decision 3 写："当 rows 数量小于 limit 时，helper 查询 target / latest covered row，返回 covered cursor；covered row 可以不匹配 filter，但必须存在于 EventLog。"但未定义：当 EventLog 完全为空时 `covered_event_sequence` 应返回什么；当 `max_event_sequence` 指向一个不存在的 sequence（如 EventLog 只有 5 行但 max=100）时 `covered_event_sequence` 应返回什么。
- **反例/失败场景**:
  1. 新创建的 Session 没有任何 EventLog rows，ProjectionRunner 收到 `covered_event_sequence=0`，`covered_event_id=None`，但 checkpoint 初始值也是 0。Runner 判定为 idle，不报错——这是正确的。但如果实现 agent 把 covered 设为其他值（如 -1、抛异常），Runner 行为不确定。
  2. `max_event_sequence=100` 但 EventLog 最新 row 的 `event_sequence` 只有 5。helper 查询 latest row 返回 sequence=5，`covered_event_sequence=5`，但 target 是 100。Runner 的 `max_event_sequence` 检查逻辑（现有 projection.py:577-586）需要能区分"covered 未到 target 但不是因为没有更多 rows"和"covered 已覆盖所有现有 rows 但 target 尚未到达"。
- **为什么有问题**: `FilteredEventLogPage` 是新的 public durable primitive contract，其边界行为（空 EventLog、target 超出实际范围）会影响所有 consumer，必须在设计阶段冻结语义。当前规格留给 implementation agent 自行决定，可能导致 inconsistent behavior。
- **直接证据**:
  - Plan Decision 3："covered row 可以不匹配 filter，但必须存在于 EventLog"——但没说不存在时怎么办
  - Plan Slice 3 Exact changes：只描述了"rows 数量小于 limit"的路径，没说"rows 数量等于 0 且 EventLog 也为空"的路径
- **影响**: implementation agent 可能做出不一致的边界决策；空 EventLog 场景的 behavior 在不同 consumer 间可能不一致
- **建议改法和验证点**: 在 `FilteredEventLogPage` 规格中补充：`covered_event_sequence=0` 且 `covered_event_id=None` 时表示未覆盖任何 row（EventLog 为空或 cursor 已在最新 row 之后）；`covered_event_sequence>0` 且 `covered_event_id` 非空时表示已覆盖到该 row（该 row 可以匹配也可以不匹配 filter）。同时在测试中明确覆盖：空 EventLog 返回 `covered=0`；max 超出实际范围返回 latest row sequence。
- **修复风险（低/中/高）**: 低
- **严重程度（高/中/低/严重）**: 中

### DS-04 未修复-中-`_MEMORY_EVENT_TYPES` 与 `_EVENT_TYPE_FILTER` 当前语义等价，plan 将动机描述为"不同 material"属于高估严重性

- **位置**: Motivation / First-principles Judgment And Direct Code Evidence / Slice 5
- **问题类型**: 动机不成立（部分高估）
- **当前写法**: Plan 写到"RunInputBuilder inline repair 是 Conversation Memory projection 的临时只读修复，不应再维护一份 `_MEMORY_EVENT_TYPES` / `_is_memory_projection_row` 的并行逻辑。否则 memory consumer filter 调整后，durable projection 和 inline repair 会看到不同 material。"
- **反例/失败场景**: 直接代码核对证实 `_MEMORY_EVENT_TYPES` = {USER_INPUT_ACCEPTED, RUN_SUCCEEDED, TOOL_RESULT_ACCEPTED, CONTEXT_COMPACTED}（run_input.py:236-243），而 `_EVENT_TYPE_FILTER` = (USER_INPUT_ACCEPTED, RUN_SUCCEEDED, TOOL_RESULT_ACCEPTED, CONTEXT_COMPACTED)（memory.py:91-96）。两者当前语义完全等价，`_is_memory_projection_row` 还额外检查 `event_class == EventClass.CANONICAL_FACT` 和 `session_id`——但 consumer filter 也检查 `event_class == EventClass.CANONICAL_FACT`，且 inline repair 通过 `snapshot.session_id` 做 session 过滤。因此目前不存在"看到不同 material"的现实风险。
- **为什么有问题**: 统一 filter 真源是正确的工程方向（DRY 原则），但 plan 用"会看到不同 material"作为动机夸大严重性。这个高估本身不是 blocker，但可能误导 implementation agent 过度重构（比如把一个简单的 module-level helper 函数做成需要 import consumer 实例的复杂依赖）。当前 plan 在 Slice 5 中给了两种实现方案，其中方案 2（module-level helper）是最小方案，但 plan 文字中写"若采用 helper，必须保证 consumer `event_filter` 仍由该 helper 生成，不能出现两份列表"——这个约束实际上是正确的，但实施复杂度被动机文字放大了。
- **直接证据**:
  - `run_input.py:236-243`: `_MEMORY_EVENT_TYPES` = frozenset({USER_INPUT_ACCEPTED, RUN_SUCCEEDED, TOOL_RESULT_ACCEPTED, CONTEXT_COMPACTED})
  - `memory.py:91-96`: `_EVENT_TYPE_FILTER` = (USER_INPUT_ACCEPTED, RUN_SUCCEEDED, TOOL_RESULT_ACCEPTED, CONTEXT_COMPACTED)
  - `run_input.py:2962-2974`: `_is_memory_projection_row` checks `event_class == EventClass.CANONICAL_FACT` + `event_type in _MEMORY_EVENT_TYPES`
  - `memory.py:240-245`: consumer filter checks `event_class == EventClass.CANONICAL_FACT` + `event_types=_EVENT_TYPE_FILTER`
- **影响**: 实施 Agent 可能过度重构 run_input.py 的 import 结构，引入不必要的 consumer 实例依赖
- **建议改法和验证点**: 保留 filter 统一的目标，但把 Motivation 段相关文字改为"两者当前语义等价，但维护两份独立列表容易在未来的 event type 调整中产生 divergence；统一为单一真源消除该维护风险。"这样 implementation agent 会选择最小方案（module-level helper）而非引入 consumer import。
- **修复风险（低/中/高）**: 低
- **严重程度（高/中/低/严重）**: 中

### DS-05 未修复-低-Slice 3 filter-aware read 函数的事务边界未显式规定

- **位置**: Slice 3 / Implementation Decision 3
- **问题类型**: 切片过粗
- **当前写法**: Plan Decision 3 描述 `read_events_after_matching` 返回 `FilteredEventLogPage`，但未规定该函数内部是否必须在一个 SQL 事务内完成"匹配行查询 + covered row 查询 + 返回 covered cursor"。
- **反例/失败场景**: 如果实现 agent 把匹配行查询和 covered row 查询放在两个独立 transaction 中，则在两查询之间可能有新行插入。导致 covered cursor 声称覆盖到 sequence=N，但实际上在 N+1 处有一条新的 matching row 刚被插入——下一轮 read 会从 N+1 开始并正确读到它，不会丢数据（因为 cursor 语义是 `>` 不是 `>=`）。所以即使跨事务也不会丢数据，但 covered cursor 的语义（"已扫描到某个点"）可能稍微滞后。这不是 correctness bug，是 precision issue。
- **为什么有问题**: Plan 没有显式规定事务边界。对于 ProjectionRunner（它本身就是 `_process_next_event` 在一个 transaction 内），filtered read 自然在同一 transaction；但对于未来的其他 consumer，如果分开调用，covered cursor 的 precision 会下降。这不是当前 WU 的真实风险，但作为 durable primitive contract 应该明确的点。
- **直接证据**: Plan Decision 3 描述了函数签名和返回值语义，但未提及事务要求；current `read_events_after` 接受 `transaction` 参数并在此 transaction 内执行单次 SQL。
- **影响**: 未来非 ProjectionRunner consumer 使用该 API 时 covered cursor 语义可能略有偏差；不影响本次 correctness
- **建议改法和验证点**: 在 `read_events_after_matching` 规格中加一句"本函数必须在调用方提供的 transaction 内完成全部读取，包括 covered row 查找。"或保持当前设计（单 transaction 是当前所有调用方的自然行为），在 stop condition 中注明"若发现需要跨事务使用，必须先讨论 covered cursor 语义"。
- **修复风险（低/中/高）**: 低
- **严重程度（高/中/低/严重）**: 低

### DS-06 未修复-低-`memory_projection_catchup_batch_size` 配置字段重命名未被考虑

- **位置**: Slice 4 / Non-goals
- **问题类型**: 最佳实践偏离
- **当前写法**: Plan Non-goals 写"不移除 `memory_projection_catchup_batch_size` 配置字段；只修正其语义为 page size。"但保留一个语义已变更的旧名字是典型的 misleading 命名。
- **反例/失败场景**: 未来开发者看到配置字段名 `memory_projection_catchup_batch_size`，自然理解为一个 catch-up 边界（"一次 catch-up 处理多少"），但实际语义已变为 page size（"每批读取多少行再继续循环"）。名字和语义不匹配会造成理解偏差和配置错误。
- **为什么有问题**: 命名是合约的一部分。`batch_size` 在过去的语义是"catch-up 最多扫描多少事件"（有上限含义），新语义是"每批读多少行"（无上限含义，循环直到 idle）。保留旧名字但不保留旧语义是一种技术债务。但 plan 在 Non-goals 中显式声明不移除/重命名，这是一个有意识的 tradeoff（避免 config 迁移）。
- **直接证据**:
  - Plan Non-goals："不移除 `memory_projection_catchup_batch_size` 配置字段；只修正其语义为 page size。"
  - Plan 没有提及是否在配置 docstring 或 Host README 中更新该字段的语义说明
- **影响**: 配置字段语义与名字长期偏离，未来可能造成配置错误
- **建议改法和验证点**: 至少在该配置字段的 docstring 或相关 schema 注释中明确写"此字段是内部 page size，不是单次 catch-up 的语义预算"；或在后续 WU 中重命名为 `memory_projection_page_size`。本次不改名是可以接受的 tradeoff。
- **修复风险（低/中/高）**: 低
- **严重程度（高/中/低/严重）**: 低

## Open questions

1. **OQ-1**: Plan 在 Slice 2 中说 `_is_preview_event` 移除三类 delta 后，这些 delta 事件的 EngineEvent data（`ContentDeltaData`、`ReasoningDeltaData`、`ToolCallDeltaData`）在 Host 内部是否还有其他消费路径（如 usage observation、diagnostic projection、tool trace）需要处理？Plan 说 `_ingest_validated` 会在 `_is_preview_event` 之前处理 non-durable delta，但 Host 内部是否有其他地方直接 switch on `EngineEventType.CONTENT_DELTA` 等并假设存在 EventLog row？建议实现前 grep 全量 `CONTENT_DELTA\|REASONING_DELTA\|TOOL_CALL_DELTA` 确认。

2. **OQ-2**: `_EVENT_TYPE_FILTER` 当前包含 `CONTEXT_COMPACTED`（imported from contracts），但 `_MEMORY_EVENT_TYPES` 也包含 `CONTEXT_COMPACTED`（imported separately in run_input.py）。两个 import 路径可能不同。若 Slice 5 创建 shared helper，这个 import 应从哪里来？建议 implementation agent 先检查两个 `CONTEXT_COMPACTED` 的 import 来源是否一致。

## Residual risks

| ID | 状态 | Owner / Destination | 下一步 |
|---|---|---|---|
| DS-01-R1 | open | 本次 follow-up | dispatch hot path 无上限同步追平——见 DS-01 |
| DS-02-R1 | open | 本次 follow-up | API 行为变更文档声明——见 DS-02 |
| DS-03-R1 | open | 本次 follow-up | `FilteredEventLogPage` 边界语义补充——见 DS-03 |

## No-overdesign check

Plan 的三处修改（delta durable 默认、ProjectionRunner filter-aware read、Memory repair / inline repair filter 语义统一）都是最小修改集。不引入新的 stream subsystem、不改变 public API signature、不改 durable schema、不建设后台 projection scheduler、不迁移历史 EventLog。整体无过度设计。DS-04 指出动机文字有轻微高估但工程方向正确。

## Overcoupling check

Plan 的 filter-aware read 使用 durable-neutral `EventLogReadClassFilter`，通过 `_event_log_read_filter_from_projection_filter` 在 projection 层转换，durable 层不 import projection 层。分层边界正确。`FilteredEventLogPage` 是 durable primitive，不包含 projection 层语义。无过度耦合。

## Slice code-generation-readiness assessment

- **Slice 1** (设计真源): code-generation-ready
- **Slice 2** (delta non-durable): code-generation-ready。Stop condition 中的 `empty events` 处理已经由代码核对证实安全（dispatch.py:3540 `if result.events:` guard）
- **Slice 3** (filter-aware read + ProjectionRunner): 基本 ready，但 `covered_event_sequence` 边界行为（空 EventLog、max 超出范围）需要补充后才能安全交给 implementation agent（见 DS-03）。`read_events_after_matching` SQL 生成逻辑（多个 class_filters 的 OR 组合）在 plan 中有描述但未给出具体 SQL 模板，implementation agent 需要自行设计；对于有经验的 agent 这是合理的。
- **Slice 4** (去预算化): code-generation-ready
- **Slice 5** (inline repair): code-generation-ready。Plan 提供了两种实现方案和 stop conditions。

## Test sufficiency assessment

- Slice 2 测试覆盖 delta non-durable、non-delta preview 保持 durable、final answer 不受影响、public watch/stream 断言——充分
- Slice 3 测试覆盖 canonical/preview/diagnostic 混排、unmatched rows checkpoint advance、`max_event_sequence` 边界、matching row apply failure——充分。缺失：空 EventLog 场景、`max_event_sequence` 指向不存在 row 的场景（见 DS-03）
- Slice 4 测试覆盖 batch_size=1 多页追到 idle/target/failure——充分
- Slice 5 测试覆盖 inline repair 区间大量无关 rows、filter 同源验证、无匹配 rows 但 covered cursor 到 required——充分

## Final plan review conclusion

**PASS-WITH-FINDINGS**

Plan 的动机成立、根因定位准确、整体方案方向正确。五个 slice 边界清晰、可独立验证。DS-01（高）需要在 plan 中补充 dispatch hot path 无上限同步补账的裁决和替代保护；DS-02 和 DS-03（中）需要在 plan 中补充行为变更文档声明和边界语义。DS-04/05/06（中低）可在 implementation 中自然解决。无 blocking structural issues。建议在 DS-01/02/03 修复后进入 implementation gate。
