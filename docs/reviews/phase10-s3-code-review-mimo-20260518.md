# Phase 10 Slice 3 Code Review — AgentMiMo

Reviewer: AgentMiMo
Date: 2026-05-18
Scope: `context_events.py` builder/validator, `memory.py` CONTEXT_COMPACTED projection, `durable/memory.py` filter, `run_input.py` filter, tests, README sync

## Verdict

**PASS**

## Summary

Slice 3 实现严格遵循计划要求：`CONTEXT_COMPACTED` 已替换 `EPISODE_SUMMARY_ACCEPTED` 成为 memory projection compact truth；typed payload builder/validator 覆盖三个 compact event 类型，`CONTEXT_COMPACTED` validator 强制 accepted quality result、pinned patch 三态结构与 evidence refs；memory projection 按字段三态语义应用 pinned state patch，episode summary 只生成 assumption continuity item，verified facts 仍只来自 `TOOL_RESULT_ACCEPTED`；生产 filter 纳入 `CONTEXT_COMPACTED` 不纳入 `CONTEXT_COMPACTION_FAILED`；`EPISODE_SUMMARY_ACCEPTED` 已从全部生产与测试 Python 文件中移除。发现 0 blocking、0 high、2 low、3 info 级别问题。

## Verification

| 检查项 | 结果 |
| --- | --- |
| `pytest tests/host/test_context_compact_events.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q` | 77 passed, 0 failed |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| `EPISODE_SUMMARY_ACCEPTED` 残留 grep | Python 文件零残留；仅 docs/reviews 旧 artifact 引用 |
| `CONTEXT_COMPACTED` filter in `durable/memory.py` | 使用 `context_events.CONTEXT_COMPACTED` 常量，非魔法字符串 |
| `CONTEXT_COMPACTION_FAILED` 不在生产 filter | `durable/memory.py:74-79` 与 `run_input.py:100-107` 均不含 |
| Slice 计划 allowed files | 全部修改在允许范围内 |

## Findings

### Low

**L1. `_patched_text_field` / `_patched_text_tuple_field` 接受 raw string / list 绕过三态结构**

- 文件: `dayu/host/memory.py:1461-1462`, `dayu/host/memory.py:1504-1506`
- `_patched_text_field` 中 `isinstance(value, str)` 分支接受直接文本值，`_patched_text_tuple_field` 中 `isinstance(value, list)` 分支接受直接数组值，均绕过 `operation` 字段级三态结构。
- 当前不可达：`project_conversation_memory_event` 在 line 1066 调用 `validate_context_compacted_payload(event.payload)`，该 validator 的 `_validate_patch_evidence`（`context_events.py:598-599`）拒绝非 mapping 的 patch 字段。因此 raw string/list 在生产路径中不会到达 projection 代码。
- 影响：纯防御性分支，不影响功能正确性。若后续有人绕过 validator 直接注入 EventLog，这些分支会静默接受非标准格式而非显式失败。
- 建议：可保持现状（防御性编程），或替换为 `raise ValueError` 使非法格式显式失败。优先级低。

**L2. `_allowed_opaque_ref_kinds` 与 `HostNeutralRefKind` 枚举值不对齐**

- 文件: `dayu/host/context_events.py:685-694` vs `dayu/host/memory.py` 中 `HostNeutralRefKind`
- 事件 validator 的 `_allowed_opaque_ref_kinds()` 返回硬编码 `set[str]`（`source`, `chunk`, `entity`, `subject`, `topic`, `evidence`, `payload`, `external`），而 projection 代码的 `_opaque_ref_from_text` 使用 `HostNeutralRefKind(kind_text)` 解析 ref kind。
- 若 `HostNeutralRefKind` 枚举增减成员，事件 validator 的硬编码集合不会自动同步。
- 影响：当前两组值一致，无功能偏差。但维护时需手动同步。
- 建议：可将 `_allowed_opaque_ref_kinds` 改为从 `HostNeutralRefKind` 枚举动态派生。优先级低。

### Info

**I1. `_compact_episode_summary_text` fallback 确定性拼接**

- 文件: `dayu/host/memory.py:2246-2270`
- 当 `episode_summary_candidate` 无 `summary_text` / `summary` 字段时，`_compact_episode_summary_parts` 将 `title`、`goal`、`completed_actions`、`open_questions`、`next_step` 确定性拼接为 `key=value` 格式。
- 这是计划要求的 "deterministic join of typed candidate fields" 实现。行为正确。

**I2. `_validate_quality_check_result` 同时检查 top-level 与 quality-result-level `evidence_anchors_retained`**

- 文件: `dayu/host/context_events.py:277`（top-level `_required_bool`）vs `context_events.py:714-721`（quality result 内 `_required_bool`）
- top-level `evidence_anchors_retained` 被 validator 检查但不被 projection 代码消费。`build_context_compacted_payload` 将两者设为相同值，但 validator 允许它们独立校验。
- 不影响功能，仅记录冗余检查点。

**I3. projection 代码 `_opaque_ref_from_text` 不限制 ref kind 枚举范围**

- 文件: `dayu/host/memory.py` 中 `_opaque_ref_from_text`
- projection 代码接受任意 `kind:ref_id` 格式，`kind` 通过 `HostNeutralRefKind(kind_text)` 解析为枚举值。若传入不在 `HostNeutralRefKind` 中的 kind，会抛 `ValueError`。但不会主动校验 kind 是否在事件 validator 的 `_allowed_opaque_ref_kinds` 子集中。
- 与 L2 同源。当前无功能偏差。

## Plan Compliance

| 计划要求 | 状态 | 证据 |
| --- | --- | --- |
| `context_events.py` typed builder/validator for 3 event types | PASS | `build_context_compaction_requested_payload` / `validate_*` 全部实现 |
| `CONTEXT_COMPACTED` validator 强制 accepted quality result | PASS | `context_events.py:709-711` |
| pinned patch validator 不接受直写字符串绕过三态 | PASS | `context_events.py:598-599` |
| confirmed_subjects 只接受 Host-neutral opaque ref | PASS | `context_events.py:610-694` |
| Replace `EPISODE_SUMMARY_ACCEPTED` with `CONTEXT_COMPACTED` | PASS | `memory.py:1063-1076`, `durable/memory.py:74-79`, `run_input.py:100-107` |
| `_compact_episode_summary_from_projection_event` helper | PASS | `memory.py:1348-1386` |
| `_apply_pinned_state_patch_candidate` helper with tri-state | PASS | `memory.py:1389-1434` |
| confirmed_subjects opaque ref validation in projection | PASS | `memory.py` 中 `_patched_confirmed_subjects` / `_opaque_ref_from_text` |
| episode summary 只生成 assumption continuity | PASS | `memory.py:1375` `claim_status=MemoryClaimStatus.ASSUMPTION` |
| verified facts 只来自 TOOL_RESULT_ACCEPTED | PASS | `memory.py:1070` `_validate_compact_summary_fact_refs` 不创建新 verified fact |
| `CONTEXT_COMPACTION_FAILED` 不在生产 filter | PASS | `durable/memory.py:74-79`, `run_input.py:100-107` |
| consumer filter 纳入 CONTEXT_COMPACTED | PASS | `durable/memory.py:78`, 测试 `test_memory_projection_filter_includes_compacted_but_not_failed` |
| RunInputBuilder memory messages 包含 compacted 投影 | PASS | `test_run_input_builder.py:test_run_input_memory_messages_include_context_compacted_projection` |
| 测试覆盖事件 validators | PASS | 17 tests in `test_context_compact_events.py` |
| 测试覆盖 memory projection tri-state | PASS | `test_context_compacted_pinned_patch_updates_clears_and_preserves` |
| 测试覆盖 verified fact 规则 | PASS | `test_context_compacted_summary_fact_refs_do_not_create_verified_facts` |
| 测试覆盖 consumer filter/checkpoint | PASS | `test_memory_projection_filter_includes_compacted_but_not_failed`, `test_projection_consumer_writes_snapshot_with_runner_checkpoint` |
| README 同步 | PASS | `dayu/host/README.md` 新增 `context_events` 职责描述；`tests/README.md` 更新覆盖说明 |

## Residual Risks

1. **Slice 4+ proactive / reactive orchestration 未实现**：当前只提供 payload builder/validator 与 memory projection consumption，`CONTEXT_COMPACTED` 的 production append 调用点由后续 slice 接入。
2. **compact artifact provider rebuild 未实现**：属于后续 slice 范围。
3. **confirmed subject ref kind 集合手动同步风险 (L2)**：事件 validator 与 projection 代码的 ref kind 来源不同，后续扩展时需注意同步。
