# Code Re-Review — P9-S3 Controller Fix Closure Verification

## Scope

- Mode: re-review（闭合验证，非全面再审查）
- Branch: `feat/host-p9-conversation-memory`
- Base: `main`
- Original review: `docs/reviews/p9-s3-code-review-ds-20260517.md` (2026-05-17)
- Re-review artifact: `docs/reviews/p9-s3-code-rereview-ds-20260517.md`
- Review date: 2026-05-17
- Verification targets: 本次 diff 中四项 controller 裁决的闭合状态

## Controller 裁决闭合验证

### Fix 1: DS 001 测试不一致（Accepted）— `_required_memory_cursor` 改为 ATTEMPT_STARTED

- **原 finding**: 测试 helper `_required_memory_cursor` 硬编码 `event-run-started-current`（RUN_STARTED），与生产 `_required_memory_event_sequence` 使用 `attempt.started_event_sequence - 1`（ATTEMPT_STARTED）不一致
- **修复**: `tests/host/test_run_input_builder.py:_required_memory_cursor` — 改为读取 `event-attempt-started-current`；docstring 更新为 "读取 ATTEMPT_STARTED 前一条 EventLog row"
- **验证**: 测试 cursor 计算与生产 `_required_memory_event_sequence` 语义一致，均使用 `ATTEMPT_STARTED - 1`。covered snapshot 测试断言无 INLINE_DELTA_REPAIR_INCLUDED diagnostic（cursor 覆盖场景无需 delta）
- **状态**: ✅ **闭合**

### Fix 1bis: DS 001 生产逻辑（Rejected）— 保持 Attempt 边界

- **原 finding**: 建议改用 RUN_STARTED
- **Controller 裁决**: rejected。P9 plan 明文要求 `required_event_sequence = current_facts.attempt.started_event_sequence - 1`。理由：resume/steer/recovery 新 Attempt 前 committed facts 可以进入 memory；Run 边界不是 P9 当前裁决
- **验证**: `dayu/host/run_input.py:566` 保持 `current_facts.attempt.started_event_sequence - 1`，符合 P9 plan
- **状态**: ✅ **裁决完成，生产无变更**

### Fix 2: DS 002（Accepted）— 移除魔法字符串

- **原 finding**: `_MEMORY_EVENT_TYPES` frozenset 中第四个元素为字面量 `"EPISODE_SUMMARY_ACCEPTED"`，前三个使用常量
- **修复**: `dayu/host/run_input.py:57` 新增 `_EVENT_TYPE_EPISODE_SUMMARY_ACCEPTED = "EPISODE_SUMMARY_ACCEPTED"`；`_MEMORY_EVENT_TYPES` 中替换为常量引用
- **验证**: frozenset 中四个元素全部使用模块私有常量，无魔法字符串
- **状态**: ✅ **闭合**

### Fix 3: DS 003（Accepted）— inline delta + stable budget 交叉测试

- **原 finding**: 测试未覆盖 inline delta repair 后 `stable_layer_size_units` budget 约束组合路径
- **修复**: `tests/host/test_run_input_builder.py:269-305` 新增 `test_inline_delta_applies_stable_layer_budget`。设置 `max_lag_events_for_inline_delta=16` + `stable_layer_size_units=24`，断言同时存在 `INLINE_DELTA_REPAIR_INCLUDED` 和 `BUDGET_LIMIT_REACHED`（`stable:verified_facts`）diagnostics
- **验证**: 两条 diagnostic 在同一 memory view 中同时出现，证明 inline delta 路径触发了 `_bounded_stable_memory_messages` 的 budget 约束
- **状态**: ✅ **闭合**

## 回归检查

- `pytest tests/host/test_run_input_builder.py tests/host/test_memory_projection.py tests/host/test_weak_typing_guard.py`: **49 passed**
- `pyright dayu/host/run_input.py dayu/host/memory.py dayu/host/durable/memory.py tests/host`: **0 errors**
- `git diff --check`: **clean**
- 四项修复均不改变控件流结构，无新增回归风险

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

无新增风险。原 review 中 Residual Risk 1（重试场景测试）已由 controller 裁决为超出 P9 当前 scope；Risk 2（`estimate_memory_size_units` 精度）和 Risk 3（continuity 回退路径渲染）未在本次 diff 中触及，仍为远期观察项。

## Conclusion

**No blocking findings.** 四项 controller 裁决全部闭合：DS 001 测试不一致已修复、DS 001 生产逻辑 rejected（符合 P9 plan）、DS 002 魔法字符串已移除、DS 003 交叉测试已补全。所有测试通过，pyright 零错误，diff 格式 clean。P9-S3 可合入。
