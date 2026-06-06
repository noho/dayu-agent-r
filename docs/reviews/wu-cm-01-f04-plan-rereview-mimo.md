# WU-CM-01-F04 Plan Re-Review — MiMo

## Verdict

**pass**

## Summary

AgentCodex 的 plan fix 成功关闭了 MiMo review 和 DS review 中所有 controller accepted findings（7 项）。Fixed plan 的 Slice 0 语义枚举清单与实际 grep 结果一致，迁移/排除决策正确，新增覆盖点明确标注，conditional assertion 策略合理。未引入新的 blocking issue。

## Accepted Findings Final Status

| Finding | 来源 | 状态 | 验证 |
| --- | --- | --- | --- |
| F1 — `_StaleMutatingCompactor` 迁移判断需修正 | MiMo F1 / DS F2 | 已修复 | Plan line 109 明确不迁移；line 149 excluded 清单列出；line 215/286 再次声明。源码验证：`test_compaction_stale_result_does_not_write_compacted_event` 断言 `CONTEXT_COMPACTED == 0`，stale check 在 accepted guard 前写 `CONTEXT_COMPACTION_FAILED`，不触发 manifest guard。 |
| F2 — `_RaisingCompactor` failure 时序语义 | MiMo F2 / DS F7 | 已修复 | Plan line 110 要求先 grep 所有使用点；line 147 inventory 列出唯一使用点；line 247/270 明确 post-manifest failure 是有意升级。源码验证：grep 确认 `_RaisingCompactor` 仅在 line 4035 使用（`test_compaction_repair_attempt_rejection_is_recorded_in_eventlog`）。 |
| F3 — `_QualityRejectOnceCompactor` first rejection manifest 覆盖 | MiMo F3 | 已修复 | Plan line 107 明确是新增覆盖；line 145 要求第一次 rejected 与第二次 accepted 都有 manifest assertions；line 254-255 Slice 3 补充断言。源码验证：当前 test（line 3967）不断言 rejected payload manifest ref/digest，迁移后确实是新增覆盖。 |
| F4 — Slice 4 semantic scan 范围 | MiMo F4 / DS F1 | 已修复 | Plan line 14 成功信号要求"语义枚举所有 proactive path compactor injection"；line 115-156 Slice 0 新增完整枚举步骤；line 284-287 Slice 4 重写为语义扫描而非字面量搜索。 |
| DS F3 — `_TransactionReadableCompactor` 显式迁移分配 | DS F3 | 已修复 | Plan line 108 设为必须显式迁移；line 142 Slice 0 inventory 列出；line 211/214 Slice 2 显式分配。源码验证：`test_proactive_compaction_calls_llm_outside_write_transaction`（line 3890）期望 `CONTEXT_COMPACTED == 1`，确实需要迁移。 |
| DS F4 — `_RequestCapturingCompactor` 使用范围 | DS F4 | 已修复 | Plan line 106 要求先 grep 全部使用点；line 139-140 inventory 列出两个 proactive accepted 使用点。源码验证：grep 确认使用点在 line 3695 和 3730，对应 `test_proactive_compaction_uses_selected_material_not_session_start_range` 和 `test_proactive_material_pack_not_larger_than_ordinary_material_for_same_view`，均为 proactive accepted。 |
| DS F5 — `RUNNER_CALL_INPUT_ASSEMBLED` conditional assertion | DS F5 | 已修复 | Plan line 220 改为 conditional assertion；line 253 rejected path 同样改为 conditional；line 375 residual risks 明确不稳定时只断言 manifest ref/digest。 |
| DS F6 — digest 常量过度设计 | DS F6 | 已修复 / 证据失效 | Plan line 170 替换原 `_COMPACTOR_TEST_DIGEST` 建议，优先复用 `_CALL_CONTEXT_DIGEST`。Controller 已裁决模块级私有 digest 常量不是过度设计。 |

## Blocking Open Questions

无。

## Residual Risks / Uncovered Areas

1. **`-k` 范围外 proactive test**: grep 确认 `FakeContextCompactor()` 直接注入共 8 处（line 3630, 3773, 4189, 4235, 4269, 4341, 4438, 4515）。其中 proactive accepted 3 处（3630, 3773, 4269），excluded fail-before-compact 2 处（4189, 4235），reactive 3 处（4341, 4438, 4515）。Plan Slice 0 inventory 准确覆盖了全部 proactive 使用点，Slice 4 broad scan 作为安全网合理。风险低。

2. **`_TransactionReadableCompactor` 迁移复杂度**: 该 compactor 在 `compact()` 中通过 `self._transaction_runner.run_read()` 开启独立读事务。迁移到 prepared helper 时需在 `run_prepared_compactor_proposal` 中保留此事务能力。Plan line 108/214 已识别并要求保留独立读事务语义。

3. **`_QualityRejectOnceCompactor` counter 状态管理**: 两次 `prepare` + 两次 `run` 的调用顺序必须保证第一次 run 返回带 diagnostic 的 candidate、第二次 run 返回 clean candidate。Plan line 107/254-255 已覆盖。

4. **pyright protocol 签名对齐**: `CompactorProposalPreparedCompactor` 是 `@runtime_checkable Protocol`，helper 方法签名必须严格对齐。Plan line 192 已识别此风险。

5. **wake queue promotion timeout**: 若 manifest seam 修复后仍有 timeout，需检查 promotion task 是否记录了新异常。Plan line 298 已识别。

## Validation Performed

1. 读取 MiMo review artifact 全文（4 项 non-blocking findings）。
2. 读取 DS review artifact 全文（3 blocking + 4 non-blocking findings）。
3. 读取 Codex plan fix artifact 全文（7 fixed + 1 rejected）。
4. 读取 fixed plan artifact 全文，逐节对照 fix 声明。
5. 读取总控文档 WU-CM-01-F04 定义（line 540-571）。
6. Grep `tests/host/test_dispatch_scheduler.py` 中 `_RequestCapturingCompactor`、`_TransactionReadableCompactor`、`_StaleMutatingCompactor`、`_RaisingCompactor`、`_QualityRejectOnceCompactor` 使用点 — 与 plan Slice 0 inventory 一致。
7. Grep `FakeContextCompactor` 使用点 — 8 处直接注入，3 处 proactive accepted，2 处 fail-before-compact excluded，3 处 reactive，与 plan 分类一致。
8. 读取 `_StaleMutatingCompactor` test body（line 3920-3963）— 确认 `CONTEXT_COMPACTED == 0` 断言，stale check 在 manifest guard 前。
9. 读取 `_RaisingCompactor` test body（line 4016-4059）— 确认仅一处使用。
10. 读取 `_QualityRejectOnceCompactor` test body（line 3967-4012）— 确认当前无 rejected payload manifest 断言，迁移后是新增覆盖。
11. 读取 `_TransactionReadableCompactor` test body（line 3890-3916）— 确认 `CONTEXT_COMPACTED == 1` 断言，需要迁移。
12. 读取 `_RequestCapturingCompactor` 使用点 test bodies（line 3690-3721, 3725-3754）— 确认均为 proactive accepted path。
13. 确认 plan 未修改生产代码、测试代码、README 或总控文档。

## Files Changed

- `docs/reviews/wu-cm-01-f04-plan-rereview-mimo.md`（本 artifact）
