# WU-PROJ-01 Slice 2 Code Review — AgentDS

## 元数据

- Reviewer：AgentDS
- Work unit：WU-PROJ-01
- Slice：Slice 2（Proactive Context Governance 使用同源 material view）
- Gate：code review
- 日期：2026-06-11
- 设计真源：`docs/host/design.md`；`docs/engine/design.md`
- 总控真源：`docs/host/issues-implementation-control.md`
- Accepted plan：`docs/host/wu-proj-01-compact-material-truth-and-bounded-memory-catchup-plan.md`
- Implementation report：`docs/reviews/wu-proj-01-slice2-implementation-codex.md`
- Review scope：当前未提交 diff

## Verdict

**PASS**

无 blocking findings。实现正确对齐 accepted plan Slice 2 的全部要求，代码变更聚焦、无过度设计，旧职责删除彻底，测试覆盖关键正确性路径。pyright 0 errors，所有 affected tests 通过。

## Findings by Severity

### 无 Blocking Findings

### Low Severity (3 findings)

#### DS-S2-L1：material source failure 异常捕获范围偏宽

**位置**：`dayu/host/dispatch.py` `_run_context_governance_for_session` 中 `except Exception as exc`（line 975）；`dayu/host/engine_ingest.py` 中 `except Exception:`（line 1333）。

**描述**：material source failure 使用 bare `except Exception` 捕获所有异常。虽然 SystemExit / KeyboardInterrupt 等 BaseException 子类不会被捕获，也不会影响正确性，但无法区分以下场景：
- `HostDurableError`（payload/artifact 损坏）—— transient 读事务失败。
- `TypeError`/`ValueError`（参数或数据 shape 非法）—— 逻辑 bug。

当前实现将所有这些都映射为 `failure_reason="material_source_failed"`，丢失了更细粒度的根因分类。

**建议**：将 `except Exception` 改为更细粒度的异常分类（至少区分 `HostDurableError` 与编程错误），让 diagnostic 中的 `failure_reason` 更精确。这也能帮助后续 Tool Trace analyzer 做 failure signature 分类。

**严重度**：Low。当前行为正确（always fail closed），不影响 compact 路径正确性。仅影响 diagnostic 可诊断性。

#### DS-S2-L2：`_proactive_fallback_material_blocks` 中的 current input 追加逻辑缺少边界场景测试

**位置**：`dayu/host/dispatch.py` `_proactive_fallback_material_blocks`（line 3656-3681）。

**描述**：该函数将 `material_view.material_blocks` 与 `_current_input_material_block` 合并后传给 fallback selector。当前 `material_view.material_blocks` 来自 delta `[start, end)`（end 为 current_input_event_sequence），因此 current input 不会出现在 delta 中，追加是正确的。

但当前没有直接测试验证 `material_view.material_blocks` 中一定不存在与 current input 同 source 的重复 block。如果未来 delta builder 的边界语义发生变化（例如 range 改为 closed interval），这个追加就会产生重复块。

**建议**：新增一个 focused 单测，直接断言 `material_view.material_blocks` 中不包含 kind 为 `USER_INPUT` 且 event_sequence 等于 `current_input_event_sequence` 的 block。

**严重度**：Low。当前数据流保证了正确性，测试是防御性的。

#### DS-S2-L3：reactive material source failure 不写 `CONTEXT_COMPACTION_FAILED` event

**位置**：`dayu/host/engine_ingest.py` `_fail_reactive_recovery_without_request`（line 1333-1348）。

**描述**：与 proactive path 不同，reactive path 的 material source failure 没有调用 `_append_compaction_failed_event` 写入 `CONTEXT_COMPACTION_FAILED`。当前 `_fail_reactive_recovery_without_request` 只关闭旧 Attempt 并 fail Run，不写入 compact governance diagnostic event。

Proactive path 在 material source failure 时显式写了 `CONTEXT_COMPACTION_FAILED` event。不一致可能导致：
- 后续 projective / audit 分析无法区分 reactive compact 是因为 compactor 失败还是 material source 失败。
- EventLog 中缺少可被 durable reader 消费的 compact governance 事件。

**建议**：在 `_fail_reactive_recovery_without_request` 中（或在调用前）也追加 `CONTEXT_COMPACTION_FAILED` event，与 proactive path 保持一致。这需要确认该 event 的 durable schema 是否允许从 reactive 路径写入。

**严重度**：Low。Reactive path 本身是 minimal adaptation，且 accepted plan 明确 reactive 只做 previous view 最小适配。但 diagnostic 完整性与 proactive path 的不对称仍是值得记录的。

### Informational (1 finding)

#### DS-S2-I1：删除的旧 helper 函数无外部调用者残留

**确认**：以下旧代码已在本次 diff 中完整删除且无外部残留引用：
- `_proactive_material_blocks` → 已重命名为 `_proactive_fallback_material_blocks`，语义完全改为同源 view 包装。
- `_proactive_represented_evidence_refs` → 已重命名为 `_selected_evidence_refs`，不再读取 memory snapshot。
- `_latest_session_compacted_event_before_input` → 已删除。

导入清理也完整：`read_latest_memory_snapshot_at_or_before`、`CONVERSATION_MEMORY_CONSUMER_ID`、`digest_memory_projection_policy`、`_payload_object`、`accepted_evidence_mapping_refs`、`build_accepted_tool_evidence_material_blocks` 均已在 `dispatch.py` 中移除。已通过 pyright（0 errors）和测试验证无 import 错误。

这是 informational 确认，不作为 finding。

## 检查清单逐项确认

### 1. proactive budget estimate 使用 material_view.budget_fragments

✅ **通过。** `_run_context_governance_for_session` 成功构造 material view 后，`estimate_context_budget` 的 `message_fragments` 参数使用 `material_view.budget_fragments`（line 1023），替代原先仅包含当前输入的单个 `BudgetTextFragment`。

`_pre_dispatch_budget_fragments`（`compact_material.py:2246-2276`）从 `previous_view`、`material_blocks`、`current_input_text` 三个同源组件构造 fragments。测试 `test_proactive_budget_uses_pre_dispatch_material_view` 覆盖此行为，断言 `estimated_input_tokens > 20`（仅当前用户输入 "short current question" 不可能触发该阈值）。

### 2. 同一 material view 用于 segment selection、pack 构建、fallback

✅ **通过。** `_prepare_compact_before_dispatch` 内：
- `select_compact_segment(..., material_blocks=material_view.material_blocks)` — line 1554
- `build_compact_material_pack(..., material_blocks=material_view.material_blocks)` — line 1558
- `_build_proactive_fallback_selection` 接收 `material_view` 并传给 `_proactive_fallback_material_blocks` — line 1906
- `_selected_evidence_refs` / `_selected_raw_turn_refs` / `selected_material_source_refs` 均使用 `material_view.material_blocks`

无分支使用第二套 material 来源。

### 3. build_compact_material_pack 传递 previous_compacted_view=material_view.previous_compacted_view

✅ **通过。** Line 1563-1564：`previous_compacted_view=material_view.previous_compacted_view`。`material_view.previous_compacted_view` 由 `build_pre_dispatch_compact_material_view` 通过 `_previous_compacted_view_from_compacted_event` 从 latest accepted compact event 的 candidate payload 直接构造（`compact_material.py:1734-1817`），不读取 memory snapshot。

### 4. CompactionRequest refs 从 material view / selection 派生

✅ **通过。**
- `evidence_backed_fact_refs`：从 `_selected_evidence_refs(material_blocks, selected_block_ids)` 派生（line 1579），基于 selected blocks 的 `accepted_evidence_id` 字段。
- `recent_raw_turn_refs`：从 `_dedupe_texts((run.input_event_id, *selected_raw_turn_refs))` 派生（line 1580），其中 `_selected_raw_turn_refs` 从 selected USER_INPUT / ASSISTANT_FINAL_ANSWER blocks 的 `canonical_source_refs` 派生。
- `older_raw_turn_refs`：从 `selected_material_source_refs(material_blocks=material_view.material_blocks, selected_block_ids=...)` 派生（line 1581）。

不再使用空 tuple `()` 或仅 `(run.input_event_id,)`。

### 5. 旧 proactive material blocks / memory snapshot evidence 去重职责已删除

✅ **通过。** 以下旧函数已删除或语义完全改变：
- `_proactive_material_blocks` → `_proactive_fallback_material_blocks`（不再读取 EventLog/Memory）。
- `_proactive_represented_evidence_refs` → `_selected_evidence_refs`（不再读取 `read_latest_memory_snapshot_at_or_before` / memory snapshot / compacted event payload）。
- `_latest_session_compacted_event_before_input` → 已删除。

导入清理完整无残留。

### 6. material source failure fail unstarted Run，不创建 Attempt

✅ **通过。**

**Proactive path**（`dispatch.py:964-1017`）：捕获 `build_pre_dispatch_compact_material_view` 异常后：
1. 写入 `CONTEXT_COMPACTION_FAILED` event（`failure_reason="material_source_failed"`）。
2. 调用 `_fail_unstarted_in_transaction` → 内部使用 `fail_unstarted_run_in_transaction`，直接将 Run 标记为 FAILED，不创建 Attempt。
3. 返回 `_GovernanceStageResult(pending_dispatch=None, compact_accepted=None)`。

**Reactive path**（`engine_ingest.py:1333-1348`）：捕获异常后调用 `_fail_reactive_recovery_without_request` 关闭旧 Attempt 并 fail Run。

测试 `test_pre_start_governance_material_source_failure_fails_closed` 覆盖 proactive 路径，断言 Run 状态为 FAILED、无 Attempt、无 CONTEXT_COMPACTION_REQUESTED event。

### 7. compactor/config failure fallback 只在已有可信 material view 时使用

✅ **通过。** `_append_compaction_failed_with_proactive_fallback` 接收 `material_view=pending.material_view`（line 1262），该 view 在 pending 阶段已成功构造（由 `_prepare_compact_before_dispatch` 验证）。fallback 路径不再独立读取 EventLog 或 memory snapshot，完全从已有可信 view 派生。

如果 material source 本身失败（第 6 条），代码不会执行到 compactor/config failure fallback 分支。

### 8. hard-threshold precondition 不进入 fallback

✅ **通过。** Line 1052-1085：当 `decision is BLOCK_HARD_THRESHOLD` 时：
1. 直接 `_append_compaction_failed_event`（无 fallback 参数）。
2. 直接 `_fail_unstarted_in_transaction`。
3. 返回 `pending_dispatch=None, compact_accepted=None`。

不调用 `_append_compaction_failed_with_proactive_fallback`。测试 `test_pre_start_governance_fallback_budget_fail_closes_run` 已更新断言，验证 `failure_reason="hard_threshold_before_dispatch"` 而非旧 `fallback_action="fail_closed"`。

### 9. reactive path 只做 previous view 最小适配

✅ **通过。** `engine_ingest.py` 变更范围：
1. `_ReactiveCompactPending` 新增 `previous_compacted_view` 字段（line 500）。
2. 初始化时调用 `build_pre_dispatch_compact_material_view(...)` 提取 `.previous_compacted_view`（line 1327-1332），失败时 fail closed（line 1333-1348）。
3. `_reactive_compaction_request` 和 `_reactive_compaction_pass_queue` 传递 `previous_compacted_view=pending.previous_compacted_view` 给 `build_compact_material_pack`（line 3627, 3676）。

**无** multi-pass、overflow ordinary material freeze、evidence-block 分段等改造。

### 10. inherited residual risk: `_readable_query_text_from_envelope` full query atom path 测试

✅ **通过。** `test_pre_dispatch_evidence_uses_full_tool_call_query_atom`（`test_compact_material.py:887-945`）：
- 构造完整 `TOOL_CALL_REQUESTED` durable atom（含 `semantic_query_text="Search FY2025 revenue for MSFT"`）。
- 构造关联的 `TOOL_RESULT_ACCEPTED`（含 `tool_call_requested_event_ref`）。
- 通过 `build_pre_dispatch_compact_material_view` 产生 material view。
- 断言 `evidence_blocks[0].readable_query_text == "Search FY2025 revenue for MSFT"`。

### 11. tests 覆盖 plan 要求 & pyright/test validation

✅ **通过。**
- `tests/host/test_compact_material.py`：32 passed。
- `tests/host/test_dispatch_scheduler.py -k "governance or compact or proactive"`：18 passed。
- `tests/host/test_public_compact_smoke.py`：6 passed，1 skipped（按 implementation report，未复验）。
- pyright：0 errors，0 warnings。

## Residual Risks

| ID | 状态 | Owner | 下一步 |
|---|---|---|---|
| DS-S2-R1 | open | Slice 3/4 或后续 owner | reactive material source failure 不写 `CONTEXT_COMPACTION_FAILED` event（见 DS-S2-L3）。由 reactive deep hardening 或 context governance event audit 后续处理。 |
| DS-S2-R2 | deferred-with-owner | Plan Slice 3 / bounded memory catch-up | proactive hard-threshold 和 material source failure 路径的 `CONTEXT_COMPACTION_FAILED` payload 当前缺少 compact operation statistics（如 scanned_events, delta_event_count），后续 Slice 3 可能需要在 context governance diagnostic payload 中引入这些字段。 |

## 未覆盖项

无。Slice 2 plan 要求的 10 个测试场景均已实现并通过：
- proactive budget 使用同源 material view ✅
- 第二次 proactive compact 使用 previous view 不重展旧 raw material ✅
- material source failure fail closed ✅
- reactive compact request 使用 latest previous view ✅
- hard-threshold no-fallback ✅
- full query atom path 测试 ✅

## 验证复验

```text
$ pytest tests/host/test_compact_material.py -q
32 passed in 0.29s

$ pytest tests/host/test_dispatch_scheduler.py -k "governance or compact or proactive" -q
18 passed, 48 deselected in 0.64s

$ pyright
0 errors, 0 warnings, 0 informations
```
