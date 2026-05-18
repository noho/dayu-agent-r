# Phase 10 Slice 3 Code Re-Review — AgentMiMo

Reviewer: AgentMiMo
Date: 2026-05-18
Scope: 确认 DS M1 与 residual risk 修复是否到位；检查 fix 是否引入新 blocking/high defect

## Verdict

**PASS**

## Summary

Codex fix 已正确修复 DS M1（`proposed_verified_fact_refs` 非空拒绝）与 DS residual risk（replace patch value validator 层 fail closed）。全部 79 个测试通过，pyright 零错误。原 Slice 3 全部要求仍然满足。fix 未引入新的 blocking 或 high defect。

## Fixed Findings

| 来源 | 编号 | 级别 | 修复状态 | 验证证据 |
| --- | --- | --- | --- | --- |
| DS | M1 | Medium | **已修复** | `context_events.py:273-277`：`_optional_text_list(summary, "proposed_verified_fact_refs")` 非空时抛 `ValueError("compact summary must not propose verified facts")`。测试 `test_compacted_payload_rejects_summary_proposed_verified_fact_refs`（`test_context_compact_events.py:138-147`）覆盖。 |
| DS | Residual | — | **已修复** | `context_events.py:638-639`：`_validate_patch_evidence` 在 `REPLACE` 操作下调用 `_validate_replace_patch_value`。该函数对 `current_goal` 要求非空文本（`_required_text`），对 tuple 字段要求文本数组，对 `confirmed_subjects` 要求 opaque ref items。测试 `test_compacted_payload_rejects_replace_patch_without_value`（`test_context_compact_events.py:164-175`）覆盖缺失 value 场景。 |

## Original Slice 3 Requirements Re-Verification

| 要求 | 状态 | 证据 |
| --- | --- | --- |
| `CONTEXT_COMPACTED` 作为 compact truth | PASS | `memory.py:1063-1076` 消费 `CONTEXT_COMPACTED`；`EPISODE_SUMMARY_ACCEPTED` 已从全部 Python 文件移除 |
| `CONTEXT_COMPACTION_FAILED` 不进入生产 filter | PASS | `durable/memory.py:74-79` 与 `run_input.py:100-107` 均不含 |
| summary 只成为 assumption continuity | PASS | `memory.py:1375` `claim_status=MemoryClaimStatus.ASSUMPTION` |
| verified facts 只来自 TOOL_RESULT_ACCEPTED | PASS | `memory.py:1070` `_validate_compact_summary_fact_refs` 不创建新 verified fact；DS M1 fix 在 validator 层额外拒绝 `proposed_verified_fact_refs` 非空 |
| RunInputBuilder messages 来自 projection snapshot | PASS | `test_run_input_builder.py` `test_run_input_memory_messages_include_context_compacted_projection` 走 catch-up → snapshot → messages 完整链路 |
| pinned patch 三态语义 | PASS | `context_events.py:638-639` REPLACE 层 fail closed；`memory.py:1389-1434` 三态正确应用 |
| confirmed_subjects Host-neutral opaque ref | PASS | `context_events.py:642-660` validator + `memory.py` projection 双重校验 |

## New Findings

**无新增 blocking / high / medium defect。**

### Low

**L1（继承 MiMo L1）. `_patched_text_field` / `_patched_text_tuple_field` 接受 raw string / list 绕过三态结构**

- 文件: `dayu/host/memory.py:1461-1462`, `dayu/host/memory.py:1504-1506`
- 状态: 未修（Codex fix report 说明未纳入本轮修复范围）。
- 影响: 当前不可达（validator 先于 projection 运行）。纯防御性分支，不影响功能正确性。
- 优先级低，不阻塞。

**L2（继承 MiMo L2）. `_allowed_opaque_ref_kinds` 与 `HostNeutralRefKind` 枚举值不对齐**

- 文件: `dayu/host/context_events.py:739-748`
- 状态: 未修（Codex fix report 说明保持依赖方向清洁，避免从 context_events 导入 memory）。
- 影响: 当前两组值一致，无功能偏差。维护时需手动同步。
- 优先级低，不阻塞。

## Verification

| 检查项 | 结果 |
| --- | --- |
| `pytest tests/host/test_context_compact_events.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q` | 79 passed (77 原有 + 2 新增), 0 failed |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| DS M1 fix: `proposed_verified_fact_refs` 非空拒绝 | `context_events.py:273-277` ✅ |
| DS residual fix: replace patch value fail closed | `context_events.py:638-639` + `_validate_replace_patch_value` ✅ |
| `_optional_text_list` 缺失字段返回空 tuple | `context_events.py:579-580` ✅ |
| `_validate_replace_patch_value` 覆盖全部 patch 字段类型 | `current_goal`→`_required_text`, `confirmed_subjects`→opaque ref, tuple fields→text array ✅ |
| Fix 是否引入新 regression | 否，全部 79 个测试通过 |

## Residual Risks

1. **Slice 4+ proactive / reactive orchestration 未实现**：`CONTEXT_COMPACTED` production append 调用点由后续 slice 接入。
2. **compact artifact provider rebuild 未实现**：属于后续 slice 范围。
3. **MiMo L1/L2 low findings 未修**：均非总控要求的阻塞项，Codex fix report 明确保留。
