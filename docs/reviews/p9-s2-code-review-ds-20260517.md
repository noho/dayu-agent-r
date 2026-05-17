# Code Review

## Scope

- Mode: current changes (uncommitted workspace diff)
- Branch: feat/host-p9-conversation-memory
- Base: HEAD (uncommitted changes review)
- Output file: docs/reviews/p9-s2-code-review-ds-20260517.md
- Included scope:
  - `dayu/host/memory.py` — P9 projection event dispatching, typed contracts, limit/select helpers, JSON serde
  - `dayu/host/durable/memory.py` — `ConversationMemoryProjectionConsumer`, snapshot read/write, checkpoint integration
  - `tests/host/test_memory_projection.py` — new slice 2 tests (10 new test functions)
- Excluded scope: design docs, schema migration, RunInputBuilder, repair/after-commit wiring (slice boundary)
- Parallel review coverage: 无

## Findings

### 1-未修复-中-project_conversation_memory_event 缺少未知 event_type 默认分支

- **入口/函数**: `project_conversation_memory_event`
- **文件(行号)**: `dayu/host/memory.py:860-879`
- **输入场景**: 任一不被四个已识别 event_type (`TOOL_RESULT_ACCEPTED` / `USER_INPUT_ACCEPTED` / `RUN_SUCCEEDED` / `EPISODE_SUMMARY_ACCEPTED`) 覆盖的 EventLog row 被传入。
- **实际分支**: if/elif 链全都不命中，代码直接进入 budget limit 步骤，随后生成新 cursor（`checkpoint_event_sequence=event.event_sequence`）并返回一个新 snapshot。
- **预期行为**: 防御性拒绝或至少产出 diagnostic，而不是静默推进 cursor 并产出与上一个 snapshot 内容相同但 digest 不同（因为 cursor 和 built_at 改变）的 snapshot。
- **实际行为**: cursor 已推进到该 event 的 sequence，但 snapshot 四类 view (pinned / verified_facts / working_assumptions / continuity) 保持不变。消费者认为 event 已被 APPLIED。该 event 在 EventLog 中仍存在，但永远不会被本 consumer 再次处理（因为 cursor 已越过它）。这不符合任何已知语义：既不是 SKIPPED（消费者明确忽略），也不是 APPLIED（投影内容发生了变化），也不是 DUPLICATE（已在 cursor 之后）。
- **直接证据**: `dayu/host/memory.py:860-879` 的 if/elif 链无 else/default 分支；其后紧接 `dayu/host/memory.py:881-926` 的 limit 步骤，limit 使用原始的 base view（等于未变更的 previous snapshot）。
- **影响**: 若未来新增 EventLog type 但忘记更新 event_filter 或 dispatcher，则对应事件会被静默消费且不可恢复。当前 consumer event_filter 限制了只有四种 type 进入，此路径在当前配置下不可达，但结构性防御缺失使后续演进容易引入静默数据丢失。
- **建议改法和验证点**: 在 if/elif 链末尾增加 else 分支，返回 `ProjectionApplyResult(SKIPPED)` 或 raise `ValueError`；若选择 SKIPPED，需确保 cursor 不被推进（目前 architecture 上 cursor 由 runner 推进，consumer 不控制，因此适合 raise 或在 consumer 层处理）。另一个方案：在 dispatch 末尾添加 `else: diagnostics += (unsupported_event_type_diagnostic,)` 但不修改 view，这至少留下 trace。
- **修复风险（低）**: 仅添加防御分支，不改变现有四条路径行为。
- **严重程度（中）**: 当前不可达，但属结构性缺口。

### 2-未修复-中-_limit_continuity_items 的 always_items 无预算上限

- **入口/函数**: `_limit_continuity_items`
- **文件(行号)**: `dayu/host/memory.py:1316-1321`
- **输入场景**: 同一 session 内发生多次 `RUN_SUCCEEDED`（例如多 run），每次都会产生一个 `ASSISTANT_CONCLUSION` item（item_kind 非 raw_turn 非 episode，落入 `always_items` 分类）。
- **实际分支**: `always_items`（行 1316-1318）被无条件加入 `selected_ids`（行 1321），不受 `history_pool_size_units` 约束。仅 `older_raw` 和 `episode_summaries` 受预算限制（行 1323-1330）。
- **预期行为**: 所有 continuity item 应在一个统一的 budget 下竞争，或至少 `always_items` 也受上限约束。
- **实际行为**: 所有 `ASSISTANT_CONCLUSION` 类 item 无条件进入 continuity view。每多一次 RUN_SUCCEEDED 就多一条不会因预算被裁剪的 item。虽然 item 按 event_id 去重（`_replace_item_by_id`），每个独立 run 有独立 event_id，因此仍会累积。
- **直接证据**: 行 1321 `selected_ids: set[str] = set(item.item_id for item in recent_raw + always_items)`，后续 budget 循环仅迭代 `older_raw` 和 `episode_summaries`（行 1323、1327），`always_items` 不参与预算检查；行 1322 `budget_used = _size_units_sum(always_items)` 仅用于计算 remaining budget，不用于限制 always_items 自身。
- **影响**: 在频繁多 run session 场景下 history pool 预算可被绕过，导致 memory snapshot 尺寸超出预期。此场景在当前单 run 为主的财报分析场景中较罕见，但架构约束不应依赖使用模式假设。
- **建议改法和验证点**: 将 `always_items` 也纳入 budget 竞争，或为其添加独立的 count/size 上限；或在 policy 中新增 `max_assistant_conclusions` 参数。若当前设计有意为之（assistant conclusion 是稳定层的一部分），应在 docstring 和 plan 中明确说明理由。
- **修复风险（中）**: 修改 budget 分配模型可能影响现有测试断言。
- **严重程度（中）**: 当前场景罕见但构成预算绕过。

### 3-未修复-中-_verified_fact_from_projection_event 的 tool_name fallback 语义不一致

- **入口/函数**: `_verified_fact_from_projection_event`
- **文件(行号)**: `dayu/host/memory.py:1022-1024`
- **输入场景**: `TOOL_RESULT_ACCEPTED` event 的 payload 中缺失 `tool_name` 字段。
- **实际分支**: `tool_name = _optional_payload_str(event.payload, _PAYLOAD_FIELD_TOOL_NAME)` 返回 `None` → `tool_name = _PRODUCER_NAME_HOST_PROJECTION`（即 `"host_projection"`）。
- **预期行为**: 使用一个明确表示"未知工具"的中立 fallback，例如 `"unknown_tool"`，以区分"工具事实由工具产生但工具名未知"与"内容由 host projection 产生"两种语义。
- **实际行为**: 生成的 `MemoryProvenanceRef` 中 `producer_kind=MemoryProducerKind.TOOL` 但 `producer_name="host_projection"`。`host_projection` 这个名称在 `MemoryProducerKind.HOST_PROJECTION` 上下文中使用（episode summary 的 producer_kind），将其作为 TOOL producer 的名称会产生语义混淆——下游消费者无法区分"这是工具产生的事实但工具名缺失"和"这是 host projection 自身合成的结论"。
- **直接证据**: 行 1022-1024 `if tool_name is None: tool_name = _PRODUCER_NAME_HOST_PROJECTION`；行 1057 `producer_name=tool_name` 与行 1056 `producer_kind=MemoryProducerKind.TOOL` 同时出现在同一 provenance 中。
- **影响**: 下游工具链若按 producer_name 做过滤或统计，会将缺失 tool_name 的 TOOL 事实归入 host_projection 类别，造成事实来源追踪失真。
- **建议改法和验证点**: 将 fallback 改为 `"unknown_tool"` 或类似中立名称，并可选地附加 `MISSING_FACT_SUMMARY_FALLBACK` 以外的 diagnostic 说明 tool_name 缺失。
- **修复风险（低）**: 仅修改一个字符串常量或 fallback 逻辑；测试 `test_missing_tool_fact_summary_uses_neutral_fallback_diagnostic` 不检查 tool_name，不会因此失败。
- **严重程度（中）**: 影响来源追踪准确性。

### 4-未修复-低-recent_raw_turns_floor 为 0 时 items[-0:] 导致全部 raw turn 进入 recent

- **入口/函数**: `_limit_continuity_items`
- **文件(行号)**: `dayu/host/memory.py:1314`
- **输入场景**: `MemoryProjectionPolicy.recent_raw_turns_floor = 0`（policy 校验允许 `>=0`）。
- **实际分支**: `raw_items[-0:]` 在 Python 中等价于 `raw_items[:]`，即返回全部 raw_items。
- **预期行为**: floor=0 应表示不保留任何 recent raw turn floor，所有 raw turn 进入 older_raw 参与 budget 竞争。
- **实际行为**: 所有 raw_items 被标记为 recent，全部无条件纳入 continuity view，相当于 history pool budget 完全不约束 raw turns。
- **直接证据**: 行 1314 `recent_raw = raw_items[-policy.recent_raw_turns_floor :]`；Python 语义 `[][-0:] == []` 和 `[1,2,3][-0:] == [1,2,3]`；`_require_non_negative` 在行 2476 允许 floor=0。
- **影响**: floor=0 的配置会产生反直觉行为——本意是不保留保底，实际却保留全部。
- **建议改法和验证点**: 将 `_require_non_negative` 改为 `_require_positive`（行 555-557），或在 `_limit_continuity_items` 中对 floor==0 做特殊处理。推荐前者，因为 floor=0 的语义本身就是"无保底"，且当前无使用场景。
- **修复风险（低）**: 若已有代码依赖 floor=0，会因 ValueError 暴露。当前测试均使用 floor >= 2。
- **严重程度（低）**: 仅 floor=0 时触发，实际场景罕见。

## Open Questions

1. `_limit_continuity_items` 中 `always_items` 无条件纳入是否为有意设计？若 assistant conclusion 被视为"稳定层"且不应因预算被裁剪，应在 plan/design doc 中明确说明，并在代码 docstring 中标注。
2. `MemoryProducerKind.HOST_PROJECTION` 与 `_PRODUCER_NAME_HOST_PROJECTION` 的使用场景是否应该更明确区分？当前在 episode summary 中 producer_kind 使用 `HOST_PROJECTION`，在 tool fallback 中仅 producer_name 使用 `"host_projection"` 但 producer_kind 仍为 `TOOL`，语义不一致。
3. `ConversationContinuityKind.RAW_ASSISTANT_TURN` 在当前 slice 中定义但从未被生产——已知是在 Slice 3 中启用还是在后续 slice 中预留？

## Residual Risk

- **ProjectionRunner 交互验证**: `apply_event` 使用 `write_memory_snapshot`（非 `write_memory_snapshot_with_checkpoint`），依赖 runner 的 `_process_next_event` 在同一 transaction 内推进 checkpoint。当前 runner 实现（`dayu/host/projection.py:519-530`）确实在同一 transaction 内调用 `apply_event` 后再调用 `advance_projection_checkpoint`，因此事务一致性正确。但若 runner 实现变更（例如并行化或 deferred checkpoint），此依赖会断裂——消费者与 runner 的 checkpoint 契约应文档化。
- **stable_layer_size_units 未消费**: `MemoryProjectionPolicy.stable_layer_size_units` 在整个 Slice 2 实现中未被任何生产代码或测试引用 —— `_limit_continuity_items` 使用 `history_pool_size_units`，`verified_facts`/`working_assumptions` 使用 count-based limit，pinned_state 使用 `max_pinned_items`。`stable_layer_size_units` 似乎是为后续 slice 预留，但在当前 slice 中为零使用率的 policy 参数。
- **diagnostic 记录时间**: 当前所有 `MemoryDiagnostic.recorded_at` 在 projection 路径中均为 `None`（`_budget_diagnostic` 和 `_verified_fact_from_projection_event` 中的 diagnostic）。`write_memory_snapshot` 中对 snapshot 内嵌 diagnostic 的写入使用 `updated_at` 作为 `recorded_at`（`dayu/host/durable/memory.py:494-500`），这与 `MemoryDiagnostic.recorded_at=None` 不一致——durable row 的 `recorded_at` 是 `updated_at`，但 typed diagnostic 的 `recorded_at` 仍是 `None`。此不一致不影响 digest（`recorded_at` 被排除在 digest 计算外），但影响诊断数据的可追溯性。
- **session 间 isolation**: `read_latest_memory_snapshot` 按 `(session_id, consumer_id, policy_digest)` 三元组查询。当前测试仅使用 `session-1`，未覆盖多 session 并发场景。若同一 consumer_id/policy 下存在两个并发 session，各自的 snapshot 应正确隔离（当前实现通过 WHERE session_id 过滤保证了这一点）。
- **项目指令合规**: 所有合约均不包含 `company`/`business_line`/`technology_release` 字段（`test_memory_contracts_do_not_expose_business_specific_fields` 已验证）；无 `dayu.fins` import；无 `Any`/`object` 类型；函数签名完整类型标注。

## Verification

```
source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/host/test_durable_schema.py
→ 30 passed in 0.25s

source .venv/bin/activate && pytest tests/host/test_weak_typing_guard.py
→ 1 passed in 0.31s

source .venv/bin/activate && pyright dayu/host/memory.py dayu/host/durable/memory.py tests/host/test_memory_projection.py
→ 0 errors, 0 warnings, 0 informations

git diff --check
→ 无输出（无空白问题）
```

## Verdict

P9-S2 实现正确满足 Slice 2 声明的核心行为：`ConversationMemoryProjectionConsumer` 正确消费四种 canonical EventLog 事件类型；`verified_facts` 仅来自 `TOOL_RESULT_ACCEPTED` 且带完整 provenance refs；`final_answer` / `RUN_SUCCEEDED` 仅进入 continuity 作为 ASSUMPTION；`USER_INPUT_ACCEPTED` 不进入 verified_facts；缺失 tool fact summary 使用中立 fallback + diagnostic；reserved claim statuses（CONFLICTED / STALE / SUPERSEDED）不被主动合成；episode summary 不替代 evidence anchor；history pool 预算优先级正确（recent floor 保留 → summaries 先被丢弃）。snapshot digest 在固定 EventLog + policy 下稳定且不依赖非确定字段。类型安全、架构边界、Host 中立语义均满足约束。

**阻塞计数: 0**。以上 4 项 finding 为中/低严重程度，均不阻塞 Slice 2 进入下一 gate，但建议在 Slice 3 前处理 finding #2 和 #3。
