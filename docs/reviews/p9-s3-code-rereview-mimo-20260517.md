# Code Re-Review

## Scope

- Mode: current changes（re-review）
- Branch: `feat/host-p9-conversation-memory`
- Base: `main`（未提交 workspace diff）
- Output file: `docs/reviews/p9-s3-code-rereview-mimo-20260517.md`
- Included scope: controller 对 MiMo 前两轮 review findings 的最终修复与裁决。
- Previous artifacts: `docs/reviews/p9-s3-code-review-mimo-20260517.md`（两轮 review 合并版）。

## Controller 裁决与闭合确认

### DS 001：required_event_sequence Attempt 边界

- **裁决**: 生产逻辑 rejected（保持 Attempt 边界）；测试不一致 accepted。
- **闭合确认**: ✅ 已闭合。
  - 生产代码 `run_input.py:1398`：`required_event_sequence = current_facts.attempt.started_event_sequence - 1`，保持 Attempt 边界。符合 P9 plan 明文要求。
  - 测试 helper `_required_memory_cursor`（`test_run_input_builder.py:949-977`）：读取 `event-attempt-started-current` 的 `event_sequence - 1`，与生产代码一致。
  - `test_durable_memory_provider_uses_covered_snapshot`（`test_run_input_builder.py:456-459`）：断言 covered snapshot 的 diagnostics 中不包含 `INLINE_DELTA_REPAIR_INCLUDED`，确认 lag=0 走 covered 路径。
  - 逻辑一致：cursor 等于 required sequence → lag_events=0 → covered 路径 → 无 inline delta diagnostic。

### DS 002：EPISODE_SUMMARY_ACCEPTED 魔法字符串

- **裁决**: accepted。
- **闭合确认**: ✅ 已闭合。
  - `run_input.py:91`：`_EVENT_TYPE_EPISODE_SUMMARY_ACCEPTED = "EPISODE_SUMMARY_ACCEPTED"`。
  - `run_input.py:102-109`：`_MEMORY_EVENT_TYPES` 使用 `_EVENT_TYPE_EPISODE_SUMMARY_ACCEPTED` 替代原魔法字符串。
  - `memory.py` 中 `_MEMORY_EVENT_TYPES` 的消费者通过 `_is_memory_projection_row`（`run_input.py:1658`）间接引用，保持一致。

### DS 003：inline delta + stable budget 组合测试

- **裁决**: accepted。
- **闭合确认**: ✅ 已闭合。
  - `test_inline_delta_applies_stable_layer_budget`（`test_run_input_builder.py:588-627`）：构造空 snapshot + `stable_layer_size_units=24` + `max_lag_events_for_inline_delta=16`，触发 inline delta repair 路径。
  - 断言 1：diagnostics 包含 `INLINE_DELTA_REPAIR_INCLUDED`（确认走了 inline delta）。
  - 断言 2：diagnostics 包含 `BUDGET_LIMIT_REACHED` 且 `item_id == "stable:verified_facts"`（确认 stable budget 裁决生效）。
  - 覆盖了 inline delta 修复后 stable blocks 仍受 budget 约束的组合路径。

## Residual Findings

前两轮 review 中的以下低严重程度 finding 未被 controller 裁决为阻断项，维持原状：

### 002-未修复-[低]-`_validate_snapshot_cursor` 中 `checkpoint_event_id is None` 守卫为不可达死代码

- `run_input.py:737`：`if cursor.checkpoint_event_id is None:` 分支不可达，因 `MemorySnapshotCursor.__post_init__` 已在构造时拒绝 `sequence > 0 and event_id is None`。无功能影响。

### 003-未修复-[低]-缺少 `_validate_snapshot_cursor` 边界测试

- `_validate_snapshot_cursor` 的三种损坏判断分支（event 不存在、sequence 不匹配、session_id 不匹配）缺少直接测试覆盖。`test_damaged_memory_snapshot_raises_repair_required` 只覆盖了 digest 损坏路径。

## Conclusion

**PASS**。Controller 裁决的四项修复全部闭合：

1. DS 001 生产逻辑：Attempt 边界正确，符合 P9 plan。
2. DS 001 测试一致性：helper 与生产代码对齐，covered snapshot 无 inline delta diagnostic。
3. DS 002：魔法字符串已提取为模块级常量。
4. DS 003：inline delta + stable budget 组合路径已覆盖。

无新增 blocking finding。剩余 2 个低严重程度 finding（002 死代码、003 测试补充）不阻塞 S3 接受。
