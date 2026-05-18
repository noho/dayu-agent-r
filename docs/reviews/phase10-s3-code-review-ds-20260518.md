# Phase 10 Slice 3 Adversarial Code Review — AgentDS

**Review Date:** 2026-05-18
**Reviewer:** AgentDS
**Scope:** Phase 10 Slice 3 — Canonical Compact Events, Memory Projection Consumption, RunInputBuilder Tests
**Design Truth:** `docs/host/design.md` §13.3, §23, §24, §25
**Implementation Control:** `docs/host/implementation-control.md`
**Slice Plan:** `docs/host/phase10-context-governance-plan.md` Slice 3
**Verdict: PASS**

---

## Verification

| 命令 | 结果 |
|------|------|
| `pytest tests/host/test_context_compact_events.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q` | 77 passed |
| `pyright` | 0 errors, 0 warnings, 0 informations |

---

## Adversarial Check Matrix

### 1. CONTEXT_COMPACTED validator — 能否接受非法 payload？

| 攻击向量 | 防御路径 | 结论 |
|----------|---------|------|
| rejected quality result (`accepted=False`) | `_validate_quality_check_result` :710-711: 显式 `if not accepted: raise ValueError` | **BLOCKED** |
| accepted 但有 rejection_reasons | `_validate_quality_check_result` :712-713: 检查 `rejection_reasons` 为空 | **BLOCKED** |
| 四个 retention flags 有 False | `_validate_quality_check_result` :714-721: 逐一 `_required_bool` 并断言为 True | **BLOCKED** |
| retained evidence refs 不存在 | `_validate_quality_check_result` :722-724: `issubset(evidence_ids)` | **BLOCKED** |
| patch 缺 evidence refs | `_validate_patch_evidence` :604-607: 非 MISSING 操作必须有非空 evidence refs 且在 evidence_ids 内 | **BLOCKED** |
| patch 证据不存在 | `_validate_patch_evidence` :606-607: `issubset(evidence_ids)` | **BLOCKED** |
| confirmed_subjects 自由业务字符串 | `_validate_confirmed_subject_patch` :610-628 → `_validate_confirmed_subject_item` :639-647 → `_validate_opaque_ref_text` :658-664 要求 `kind:ref_id` 格式 | **BLOCKED** |
| confirmed_subjects 未知 ref kind | `_validate_opaque_ref_kind` :675-676: kind 必须在 `_allowed_opaque_ref_kinds()` 集合内（8 种 HostNeutralRefKind） | **BLOCKED** |
| 未知 patch 字段 | `_validate_patch_evidence` :593-595: `if field_name not in _PATCH_ALLOWED_FIELDS: raise ValueError` | **BLOCKED** |
| patch 字段绕过三态结构（直写文本） | `_validate_patch_evidence` :598-599: `if not isinstance(value, Mapping): raise ValueError` | **BLOCKED** |
| summary 缺 preservation evidence | :267-269: `summary_evidence_refs` 非空检查 | **BLOCKED** |
| summary evidence refs 不存在 | :270-271: `issubset(evidence_ids)` | **BLOCKED** |

**未防御的向量：`proposed_verified_fact_refs` 非空不拒绝。**

`validate_context_compacted_payload` :251-279 读取 `episode_summary_candidate` 但不校验 `proposed_verified_fact_refs` 字段。`EpisodeSummaryCandidate.to_json()` 会将该字段序列化到 payload 中。若有人绕过 typed builder 构造 JSON（如 EventLog replay 场景），validator 不会拒绝非空的 `proposed_verified_fact_refs`。

**影响评估：** 实际风险低。理由：
- `build_context_compacted_payload` 要求 `accepted_candidate: CompactionCandidate`（typed），其 `proposed_verified_fact_refs` 默认为空 tuple
- Slice 2 quality checker 拒绝 `SUMMARY_PRETENDS_VERIFIED_FACT`
- memory projection `memory.py:1066-1074` 不消费 `proposed_verified_fact_refs`，verified facts 仍仅来自 `TOOL_RESULT_ACCEPTED`
- 即使非空 payload 进入 memory projection，也只会被忽略，不会创建 verified fact

详见 Medium Finding M1。

---

### 2. Memory projection — 能否从 compact summary 新建 verified fact？

**:1066-1074 (memory.py):**

```python
elif event.event_type == _EVENT_TYPE_CONTEXT_COMPACTED:
    validate_context_compacted_payload(event.payload)
    _validate_compact_summary_fact_refs(event, base.verified_facts)
    item = _compact_episode_summary_from_projection_event(event, policy=policy)
    continuity_items = _replace_item_by_id(continuity_items, item)
    pinned_state = _apply_pinned_state_patch_candidate(...)
```

- `CONTEXT_COMPACTED` handler 只创建 `ConversationContinuityItem`（summary）与更新 `PinnedStateView`（patch）
- `verified_facts` 未在此分支被修改 — 仅 `TOOL_RESULT_ACCEPTED` handler 创建 verified fact
- `_validate_compact_summary_fact_refs` :1453-1472 校验 `confirmed_fact_refs` 只引用已有工具事实（`_existing_tool_fact_refs`），但不允许新建

**结论：无法由 compact summary 创建 verified fact。** ✅

测试 `test_context_compacted_summary_fact_refs_do_not_create_verified_facts` 验证：summary 引用已有 tool fact ref 后，verified_facts 计数仍为 1（仅来自 `TOOL_RESULT_ACCEPTED`）。

---

### 3. Pinned patch — missing / clear / replace 三态一致性

`:152-197 (memory.py)` 的 `_apply_pinned_state_patch_candidate`：

| 字段 | 类型 | 处理器 | missing | clear | replace |
|------|------|--------|---------|-------|---------|
| `current_goal` | `str \| None` | `_patched_text_field` :1400-1475 | 保留原值 | `None` | 新文本 |
| `confirmed_subjects` | `tuple[OpaqueMemoryRef, ...]` | `_patched_confirmed_subjects` :1482-1513 | 保留原值 | `()` | 新 tuple |
| `user_constraints` | `tuple[str, ...]` | `_patched_text_tuple_field` :1478-1536 | 保留原值 | `()` | 新 tuple |
| `open_questions` | `tuple[str, ...]` | `_patched_text_tuple_field` :1478-1536 | 保留原值 | `()` | 新 tuple |

四个字段使用不一致的处理函数（text 字段 vs tuple 字段），但三态语义一致：missing=保留（在 `_patched_text_field` / `_patched_text_tuple_field` 的 `if field_name not in patch: return current_value` ），clear=空值，replace=新值。

测试 `test_context_compacted_pinned_patch_updates_clears_and_preserves` 验证： replace `current_goal` → 替换；clear `user_constraints` → 清空；省略 `open_questions` → 保留；后续 compact replace `open_questions` → 新增，同时 `current_goal` / `confirmed_subjects` / `user_constraints` 均未变化。

**结论：三态一致。** ✅

---

### 4. Consumer filter — 仅消费 CONTEXT_COMPACTED，不消费 CONTEXT_COMPACTION_FAILED

`dayu/host/durable/memory.py:42-48`:

```python
_EVENT_TYPE_FILTER = (
    _EVENT_TYPE_USER_INPUT_ACCEPTED,
    _EVENT_TYPE_RUN_SUCCEEDED,
    _EVENT_TYPE_TOOL_RESULT_ACCEPTED,
    CONTEXT_COMPACTED,
)
```

`CONTEXT_COMPACTION_FAILED` 不在 filter 内。`CONTEXT_COMPACTION_REQUESTED` 也不在 filter 内。

测试 `test_memory_projection_filter_includes_compacted_but_not_failed` 直接断言 consumer filter 包含 `CONTEXT_COMPACTED` 且不包含 `CONTEXT_COMPACTION_FAILED`。

`run_input.py:104-109` 的 `_MEMORY_EVENT_TYPES` frozenset 同步替换为 `CONTEXT_COMPACTED`。

**结论：生产 consumer 仅消费 committed canonical CONTEXT_COMPACTED。** ✅

---

### 5. RunInputBuilder memory messages — 来自 projection snapshot 还是测试直塞？

新测试 `test_run_input_memory_messages_include_context_compacted_projection` (`test_run_input_builder.py:1049-1078`) 的数据流：

1. `_append_rich_memory_source_events` 写入原始 EventLog（含 `CONTEXT_COMPACTED` canonical fact）
2. `catch_up_conversation_memory_projection` 通过 `ProjectionRunner` → `ConversationMemoryProjectionConsumer` 消费 EventLog 构建 memory snapshot
3. `_build_request_with_memory` 使用 `DurableMemorySnapshotProvider` 读取 snapshot + EventLog delta
4. `_message_content` 提取最终 message 内容

最终断言 pinned state（`current_goal=compact pinned goal`、`confirmed_subject=subject:issuer-a`、`open_question=compact open question`）和 episode summary（`episode_summary=episode navigation only`）均出现在 messages 中，且 `current prompt` 仍为最后一条。

**结论：memory messages 真正来自 projection snapshot → DurableMemorySnapshotProvider 路径，不是测试直塞。** ✅

---

### 6. 跨层依赖与 Slice 4/5 假设

**`context_events.py` 导入链：**

```
dayu.contracts.json_value          ← 公共契约层
dayu.host.compaction               ← Host 层内
dayu.host.context_budget           ← Host 层内
dayu.host.context_policy           ← Host 层内
dayu.host.durable.codec            ← Host 层内 (durable 子包)
```

无跨层依赖（无 `dayu.engine`、`dayu.service`、`dayu.ui`、`dayu.fins` 导入）。✅

**对 Slice 4/5 的假设检查：**

- `context_events.py` 不假设 `CONTEXT_COMPACTED` 的 append 调用点 — builder/validator 是纯函数，由上层决定在哪个事务内调用
- `build_context_compacted_payload` 不编码 `trigger_source` — proactive/reactive compacted 输出共享同一 payload 结构
- `CONTEXT_COMPACTION_REQUESTED` validator 已处理 proactive（attempt/execution 可 None）与 reactive（必须非空）的区别 (`:190-192`)
- memory projection 不修改 Run/Attempt 状态 — Slice 4/5 orchestration 可以安全地在 catch-up 后 append `RUN_STARTED` 等状态事实
- `context_events.py` 不 import `dayu.host.memory` — 保持单向依赖 (`memory → context_events`) ✅

**结论：Slice 3 未引入跨层依赖或对后续 slice 的错误假设。** ✅

---

## Findings

### Medium

**M1. `validate_context_compacted_payload` 未校验 `proposed_verified_fact_refs` 为空**

- **文件:** `dayu/host/context_events.py:263-271`
- **证据:** validator 读取 `episode_summary_candidate` (line 263) 并校验 `evidence_refs` (line 267-271)，但未访问 `proposed_verified_fact_refs` 字段。`EpisodeSummaryCandidate.to_json()` (`compaction.py:398-400`) 序列化该字段，所以 payload 中可以携带非空值。
- **利用路径:** 绕过 typed builder 直接构造 JSON payload（如 EventLog 手工回放场景），携带 `proposed_verified_fact_refs: ["fake-fact"]` 同时 `quality_check_result.accepted=True`。validator 不会拒绝。
- **实际影响:** memory projection 不消费此字段，verified facts 仍仅来自 `TOOL_RESULT_ACCEPTED`，故无法通过此缺口创建虚假 verified fact。但 validator 作为 canonical event 的最后防线，应在 payload 层面拒绝。
- **建议修复:** 在 `validate_context_compacted_payload` 中增加：
  ```python
  proposed = _optional_text_list(summary, _PAYLOAD_FIELD_PROPOSED_VERIFIED_FACT_REFS)
  if len(proposed) > 0:
      raise ValueError("compact summary must not propose verified facts")
  ```
- **触发条件:** Slice 2 quality checker 已拒绝此类候选，typed builder 默认值也为空，正常路径不可达；仅 payload 手工构造可触发。

---

### Low

**L1. `_allowed_opaque_ref_kinds()` 硬编码与 `HostNeutralRefKind` 枚举重复**

- **文件:** `dayu/host/context_events.py:679-694` vs `dayu/host/memory.py:135-145`
- **证据:** `_allowed_opaque_ref_kinds()` 返回硬编码 set: `{"source", "chunk", "entity", "subject", "topic", "evidence", "payload", "external"}`，与 `HostNeutralRefKind` 枚举成员一一对应。新增 ref kind 时需手动同步两处。
- **建议修复:** 从 `HostNeutralRefKind` 枚举成员派生允许集合；或将 `_allowed_opaque_ref_kinds` 提升到共享模块。

**L2. `_patched_text_field` 接受裸字符串作为 patch 字段值**

- **文件:** `dayu/host/memory.py:1461-1462`
- **证据:** `_patched_text_field` 在 `isinstance(value, str)` 分支直接调用 `_bounded_patch_text`，绕过三态结构检查。`_validate_patch_evidence` (`context_events.py:598-599`) 已拒绝非 Mapping 的 patch 字段值，因此此路径在正常 flow 不可达。但若未来 `_patched_text_field` 被直接调用（未经 validator），裸字符串路径可能被误用。
- **建议:** 考虑移除或注释该防御性分支；或在函数 docstring 明确要求调用方先通过 `validate_context_compacted_payload`。

**L3. `_compact_payload` helper 在两处测试文件中有重复定义**

- **文件:** `tests/host/test_memory_projection.py:673-756` vs `tests/host/test_run_input_builder.py:1119-1177`
- **差异:** 两处签名略有不同（`confirmed_fact_refs`、`pinned_patch` 参数不同），但核心结构重复。不影响功能，仅测试维护成本。

---

## Plan Compliance

| 计划要求 | 状态 | 证据 |
|---------|------|------|
| typed builders for CONTEXT_COMPACTION_REQUESTED/COMPACTED/FAILED | PASS | `context_events.py:119-164, 195-248, 282-315` |
| payload validators reject missing required fields | PASS | `test_requested_payload_rejects_missing_required_fields`, `test_compacted_payload_rejects_missing_artifact_digest_pair`, `test_failed_payload_rejects_missing_required_fields` |
| validator rejects untyped metadata for required fields | PASS | `test_requested_payload_rejects_untyped_metadata_for_required_fields` |
| reactive requires attempt/execution | PASS | `context_events.py:190-192`; `test_reactive_requested_requires_attempt_and_execution` |
| compacted payload requires artifact ref/digest pair | PASS | `context_events.py:261-262` |
| summary/patch without evidence rejected | PASS | `test_compacted_payload_rejects_summary_without_preservation_evidence`, `test_compacted_payload_rejects_patch_without_preservation_evidence` |
| Replace EPISODE_SUMMARY_ACCEPTED with CONTEXT_COMPACTED | PASS | `durable/memory.py:44-47` — filter 替换; `memory.py` — event type 常量替换; 所有测试 seed 替换 |
| CONTEXT_COMPACTED not in EPISODE_SUMMARY_ACCEPTED path | PASS | 旧 `_episode_summary_from_projection_event` 重命名为 `_compact_episode_summary_from_projection_event`; `EPISODE_SUMMARY_ACCEPTED` 常量已删除 |
| summary becomes assumption continuity item | PASS | `test_context_compacted_episode_summary_becomes_assumption_continuity` |
| pinned patch tri-state field-level update | PASS | `_apply_pinned_state_patch_candidate` :152-197; `test_context_compacted_pinned_patch_updates_clears_and_preserves` |
| confirmed_subjects only opaque refs | PASS | `_patched_confirmed_subjects` → `_opaque_ref_tuple_from_patch_values`; validator `_validate_confirmed_subject_patch`; `test_context_compacted_rejects_free_form_confirmed_subject_patch` |
| verified facts only from TOOL_RESULT_ACCEPTED | PASS | `test_context_compacted_summary_fact_refs_do_not_create_verified_facts`; `project_conversation_memory_event` :1066-1074 不修改 `verified_facts` |
| consumer filter includes CONTEXT_COMPACTED | PASS | `durable/memory.py:47`; `test_memory_projection_filter_includes_compacted_but_not_failed` |
| CONTEXT_COMPACTION_FAILED not in consumer filter | PASS | `test_memory_projection_filter_includes_compacted_but_not_failed` |
| RunInputBuilder tests from projection catch-up | PASS | `test_run_input_memory_messages_include_context_compacted_projection` |
| README 同步 | PASS | `dayu/host/README.md` 更新 context_events 职责; `tests/README.md` 更新测试覆盖描述 |
| No old EPISODE_SUMMARY_ACCEPTED seed in tests | PASS | 所有 `_append_rich_memory_source_events` / history pool / budget 测试已替换为 `CONTEXT_COMPACTED` |

---

## Positive Observations

1. **Validator 防御深度优秀:** `validate_context_compacted_payload` 对 accepted quality result 做了 7 项校验，对 pinned patch 做了字段白名单、三态结构、evidence refs、confirmed_subjects opaque ref 共 4 层校验。仅缺 `proposed_verified_fact_refs` 一项。
2. **Memory projection 边界干净:** `CONTEXT_COMPACTED` handler 不修改 `verified_facts`、不写 EventLog、不修改 Run/Attempt 状态；仅更新 `continuity_items` 与 `pinned_state`。
3. **Patch 字段隔离:** `_patched_text_field` 和 `_patched_text_tuple_field` 各自独立操作；省略字段保留原值，显式 field 覆盖，不会误清空其他字段。
4. **Type boundary 一致:** `context_events.py` 的 `_allowed_opaque_ref_kinds()` 与 `memory.py` 的 `HostNeutralRefKind` 值集合一致（8 种）。
5. **测试 adversarial 覆盖:** `test_compacted_payload_rejects_direct_patch_field_without_tristate` 直接测试绕过三态攻击；`test_context_compacted_rejects_free_form_confirmed_subject_patch` 测试自由字符串攻击。

---

## Residual Risks

1. **M1 residual: `proposed_verified_fact_refs` payload-level 校验缺失。** 建议在 Slice 3 收尾或 Slice 6 补强。当前正常路径不可达，仅防御深度问题。
2. **`CONTEXT_COMPACTED` validator 未校验 patch field replace value 非空。** `_patched_text_field` / `_patched_text_tuple_field` 在 memory projection 时会以 `ValueError` 兜底，但 validator 不提前报告。建议后续补强 `_validate_patch_evidence` 检查 replace 操作的 value 字段。
3. **Real LLM compactor adapter 未实现。** 属于 Slice 6 范围，当前仅 typed contracts + fake compactor + validator 就绪。
4. **`CONTEXT_COMPACTED` production append 调用点未接入。** 属于 Slice 4/5 orchestration 范围，当前仅 payload builder/validator 与 memory projection consumption 就绪。

---

## Summary

- **Verdict: PASS** — 无 blocking/high finding
- **Findings:** 0 blocking, 0 high, 1 medium, 3 low
- **Tests:** 77 passed, 0 failed
- **Pyright:** 0 errors, 0 warnings, 0 informations
- **Adversarial checks:** 12 blocked, 1 accepted (M1 — 实际零影响)
- **Plan compliance:** 15/15 PASS
