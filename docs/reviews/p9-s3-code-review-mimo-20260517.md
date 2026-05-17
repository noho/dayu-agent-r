# Code Review

## Scope

- Mode: current changes
- Branch: `feat/host-p9-conversation-memory`
- Base: `main`（未提交 workspace diff）
- Output file: `docs/reviews/p9-s3-code-review-mimo-20260517.md`
- Included scope: `dayu/host/run_input.py`、`dayu/host/memory.py`、`tests/host/test_run_input_builder.py` 中与 P9-S3 `RunInputBuilder MemorySnapshotProvider and Lag Fallback` 相关的未提交 diff。
- Excluded scope: 已提交的 P9-S1、P9-S2 slice commit，除非与当前 diff 形成直接回归。
- Parallel review coverage: 无。

## Findings

### 001-已修复-[低]-`_is_current_run_user_input_memory_item` 回退过滤器可能误杀同 Run 内历史 raw turn

- **状态**: **已修复**。controller 接受了 MiMo 方向，删除了 `run_id + summary_text` 回退过滤器，仅保留 `event_id` 判定。
- **直接证据**: `run_input.py:1723-1727` 现在只判断 `item.event_id == render_scope.user_input_event_id`，回退 `return False`。不再有 `run_id + summary_text` 匹配路径。

### 002-未修复-[低]-`_validate_snapshot_cursor` 中 `checkpoint_event_id is None` 守卫为不可达死代码

- **入口/函数**: `_validate_snapshot_cursor`（`run_input.py:718`）
- **文件(行号)**: `dayu/host/run_input.py:737`
- **输入场景**: `MemorySnapshotCursor` 的 `checkpoint_event_sequence > 0` 且 `checkpoint_event_id is None`。
- **实际分支**: 永远不会到达。`MemorySnapshotCursor.__post_init__`（`memory.py:220-221`）在 `checkpoint_event_sequence > 0` 时要求 `checkpoint_event_id is not None`，否则抛出 `ValueError`。构造 `MemorySnapshotCursor` 时就已经拒绝了非法状态。
- **预期行为**: `_validate_snapshot_cursor` 应假设已通过 dataclass 校验的 cursor 状态，不需要重复防御。
- **实际行为**: `if cursor.checkpoint_event_id is None:` 守卫（`run_input.py:737-743`）为不可达代码。
- **直接证据**: `memory.py:217-221`：`if self.checkpoint_event_sequence == _MIN_SEQUENCE: if self.checkpoint_event_id is not None: raise ValueError(...)` 及 `elif self.checkpoint_event_id is None: raise ValueError(...)`。构造时已拒绝 `sequence > 0 and event_id is None` 的组合。
- **影响**: 无功能影响。死代码增加维护认知负担，但不产生错误行为。
- **建议改法和验证点**: 删除 `if cursor.checkpoint_event_id is None:` 分支。`read_event_by_id` 的参数类型为 `str`，不存在 `None` 路径。验证：pyright 通过，现有测试不受影响。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 003-未修复-[低]-缺少 `_validate_snapshot_cursor` 边界测试

- **入口/函数**: `_validate_snapshot_cursor`（`run_input.py:718`）
- **文件(行号)**: `tests/host/test_run_input_builder.py`
- **输入场景**: snapshot cursor 的 `event_sequence` / `event_id` 与 EventLog 不匹配、session_id 不一致、或 cursor 指向不存在的 event。
- **实际分支**: 现有测试 `test_damaged_memory_snapshot_raises_repair_required` 只覆盖了 digest 损坏路径（`_read_latest_snapshot_or_repair` 中的 `HostDurableError`），未直接测试 `_validate_snapshot_cursor` 的三种损坏判断分支。
- **预期行为**: `_validate_snapshot_cursor` 的每个损坏分支（event 不存在、sequence 不匹配、session_id 不匹配）都应有独立测试覆盖。
- **实际行为**: 这三个分支没有直接测试。
- **直接证据**: `run_input.py:744-755` 包含三个损坏判断条件，但 `test_damaged_memory_snapshot_raises_repair_required` 只测试了 digest 损坏触发的 `HostDurableError` 路径（`_read_latest_snapshot_or_repair:700`），未覆盖 `_validate_snapshot_cursor` 内部的 `read_event_by_id` 返回 `None`、`sequence mismatch`、`session_id mismatch` 三种情况。
- **影响**: 损坏 cursor 的防御路径未被测试验证，回归风险中等。
- **建议改法和验证点**: 新增三个测试：cursor event 不存在、cursor event sequence 不匹配、cursor session_id 不匹配。每个测试应确认 `MemoryProjectionRepairRequired` 被抛出且 `reason is MemoryRepairReason.SNAPSHOT_DAMAGED`。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Re-Review Note（20260517 第二轮）

controller 在第一轮 review 后追加了两项变更，纳入本轮审查：

### 变更 A：stable layer budget 裁决

**实现**: `_bounded_stable_memory_messages`（`run_input.py:1498-1532`）按 P9 优先级（goals → subjects → verified_facts → questions_assumptions）消费 `policy.stable_layer_size_units`。每个 stable block 通过 `estimate_memory_size_units` 估算尺寸，累计超出预算时跳过后续 block 并记录 `BUDGET_LIMIT_REACHED` diagnostic。recent raw turns、episode summaries 和当前 prompt 不受 stable layer cap 约束。

**审查结论**: 实现正确。

- `_memory_stable_blocks`（`run_input.py:1467`）按 P9 裁决固定优先级构造 blocks，与设计 §23 顺序一致。
- `_bounded_stable_memory_messages` 使用累加预算，高优先级 block 先占预算，低优先级 block 在预算耗尽时被跳过——符合设计意图。
- `_memory_messages`（`run_input.py:1431`）将 stable messages、raw turn messages、episode summary 分开处理，raw turns 和 episode 不进入 stable cap——与总控文档 §P9-S3 "recent raw turns、episode summaries 和当前 prompt 不进入 stable_layer cap" 一致。
- `_memory_snapshot_view`（`run_input.py:1404`）将 snapshot diagnostics 与渲染阶段 diagnostics 合并，确保 `BUDGET_LIMIT_REACHED` 和 `INLINE_DELTA_REPAIR_INCLUDED` 同时可观测。
- 新增 `_MemoryStableBlock` 和 `_RenderedMemoryMessages` 为模块私有 dataclass，不暴露到公共 API。
- 测试 `test_memory_provider_applies_stable_layer_budget` 验证了 `stable_layer_size_units=24` 时 verified_facts block 被跳过、raw turns 和当前 prompt 不受影响、diagnostic 正确记录。

**未发现新问题。**

### 变更 B：`_is_current_run_user_input_memory_item` 回退过滤器删除

**实现**: `run_input.py:1713-1727` 现在只通过 `item.event_id == render_scope.user_input_event_id` 判断，删除了 `run_id + summary_text` 回退。

**审查结论**: 修复正确，与 MiMo finding 001 建议一致。`event_id` 是 `USER_INPUT_ACCEPTED` 的唯一标识，不存在误杀风险。

## Open Questions

- 无。

## Residual Risk

1. **inline delta 路径的 `_is_current_run_user_input_memory_item` 过滤**: 现有测试 `test_inline_delta_filters_current_user_input` 通过手工构造 snapshot 测试过滤，未通过真实 EventLog projection + inline delta 路径验证。若 `project_conversation_memory_event` 将 `USER_INPUT_ACCEPTED` 投影到 `conversation_continuity` 的方式与手工构造不一致，过滤可能失效。
2. **`_validate_snapshot_cursor` 的 zero cursor 快速返回**: `checkpoint_event_sequence == 0` 时直接返回不做 EventLog 校验。如果上游写入了 `sequence=0` 但 `event_id=None` 的非法 cursor，dataclass 校验会拒绝，但如果持久化层绕过了 dataclass 构造，此路径不会发现损坏。当前 `MemorySnapshotCursor.__post_init__` 已覆盖此边界。
3. **ahead-of-required 路径**: controller 新增的 `SNAPSHOT_AHEAD_OF_REQUIRED` 逻辑正确，`lag_events < 0` 与 `lag_events <= 0` 顺序正确，不会误命中 covered 路径。测试 `test_ahead_memory_snapshot_raises_repair_required` 已覆盖。
4. **`DurableSessionContinuityProvider` 不再注入历史 raw turns**: 已正确删除 `read_run_input_continuity_events` 调用，只保留 resume-specific continuity。测试 `test_session_continuity_does_not_emit_unbudgeted_historical_raw_turns` 已验证。
5. **memory message 注入顺序**: `_memory_messages` 按 P9 裁决顺序渲染 stable blocks（目标约束、主体口径、tool verified facts、open questions/assumptions），然后 raw turns、episode summaries。`RunInputBuilder.build` 将 memory messages 放在 scene messages 之后、compact/continuity/current prompt 之前。当前 prompt 作为 final `UserMessage` 只出现一次。测试 `test_durable_memory_provider_uses_covered_snapshot` 和 `test_covered_memory_snapshot_filters_current_user_input` 已验证。
6. **stable layer budget 优先级降级**: 当前测试只覆盖了"全部跳过"场景（`stable_layer_size_units=24`，第一个 block 就超预算）。未测试"部分保留"场景（例如预算允许 goals 但不允许 verified_facts）。低风险，因为 `_bounded_stable_memory_messages` 的累加逻辑简单且确定性。

## Conclusion

未发现阻断性问题。三条核心路径（covered snapshot、inline delta repair、missing/damaged/ahead/over-threshold repair-required）实现正确，inline delta 不写 EventLog、不改 Run Attempt 状态、不推进 projection checkpoint。`DurableSessionContinuityProvider` 已正确收敛为 resume-only。snapshot cursor 校验、session scope、policy digest、diagnostics 均具备可观测性。stable layer budget 按 P9 优先级正确裁决，recent raw turns / episode summaries / 当前 prompt 不受 stable cap 约束。`_is_current_run_user_input_memory_item` 回退过滤器已修复，仅用 `event_id` 判定。测试覆盖了 S3 的主要反幻觉边界（当前 prompt 不重复注入、同一 EventLog + 同一 policy 生成稳定 messages、projection lag 不改变 Run 状态、stable layer budget enforcement）。剩余 2 个低严重程度 finding（002 死代码、003 测试补充），不阻塞 S3 接受。
