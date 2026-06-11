# WU-PROJ-01 Slice 1 Re-Review — AgentDS

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: re-review (fix gate 后)
- Slice: Slice 1 — EventLog-backed pre-dispatch compact material source
- Reviewer: AgentDS
- 日期: 2026-06-11
- Fix report: `docs/reviews/wu-proj-01-slice1-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-proj-01-slice1-code-review-controller-adjudication.md`
- Previous MiMo review: `docs/reviews/wu-proj-01-slice1-code-review-mimo.md`
- Previous DS review: `docs/reviews/wu-proj-01-slice1-code-review-ds.md`
- Re-review scope: 5 条 accepted findings 的修复正确性，以及修复是否引入新问题

## Verdict

**PASS** — 所有 5 条 accepted findings 均已正确修复，fix 未引入新的 correctness/type/test/architecture 问题。

## 独立验证

| 检查项 | 结果 |
|---|---|
| `pytest tests/host/test_compact_material.py` | 31 passed, 0.29s |
| `pyright` | 0 errors, 0 warnings, 0 informations |

与 fix report 报告一致。

## 逐条 Fix 审查

### ✅ MiMo F1: CompactMaterialSourceBoundary direct negative tests

**Fix**: 新增两个 focused negative test：
- `test_compact_material_source_boundary_rejects_inverted_delta_boundary`（L883）：构造 `start=4, end=3, current=3`，断言 `ValueError("post compact delta boundary is inverted")`
- `test_compact_material_source_boundary_rejects_delta_end_mismatch`（L896）：构造 `start=2, end=3, current=4`，断言 `ValueError("delta end sequence must equal current input sequence")`

**审查结论**: ✅ 通过。两条测试覆盖了 `CompactMaterialSourceBoundary.__post_init__` 中 L386-389 的全部两条显式校验路径。测试是对 dataclass 构造的直接调用，不依赖 builder 间接路径。错误信息与生产代码精确匹配。

### ✅ MiMo F2: PreDispatchCompactMaterialView direct negative tests

**Fix**: 新增 `test_pre_dispatch_material_view_rejects_boundary_field_mismatches`（L912），覆盖四种 mismatch：
- `latest_compacted_event_id` mismatch → `"latest compacted event id boundary mismatch"`
- `latest_compacted_event_sequence` mismatch → `"latest compacted event sequence boundary mismatch"`
- `post_compact_delta_start_sequence` mismatch → `"post compact delta start boundary mismatch"`
- `post_compact_delta_end_sequence` mismatch → `"post compact delta end boundary mismatch"`

每个 mismatch 通过 `dataclasses.replace(view, field=wrong_value)` 触发 `__post_init__` 重新校验（Python 3.11 frozen dataclass 的 `replace()` 通过 `__init__` 创建新实例，`__post_init__` 会被调用）。

**审查结论**: ✅ 通过。测试的 happy-path 构造先验证合法数据可通过，再用 `replace()` 逐一触发 mismatch，覆盖了 `PreDispatchCompactMaterialView.__post_init__` L435-451 的全部四条边界校验。测试结构清晰，不依赖 builder。

### ✅ MiMo F3: fallback `tool_call_event_ref` 语义说明

**Fix**: 在 `_accepted_tool_evidence_delta_blocks` 的 docstring（L2063-2066）增加说明：
> 当 accepted evidence envelope 缺少 durable request atom 时，`tool_call_event_ref` 会退化为当前 producer event ref。这个 ref 只用于 prompt-local provenance 追溯，不表示对应的 `TOOL_CALL_REQUESTED` event 一定存在。

并在 fallback 代码处（L2106）增加行内注释：
> 缺少 request atom 时只保留本地 provenance 线索，不伪造 request event。

**审查结论**: ✅ 通过。docstring 明确了退化语义：退化为 producer event ref、仅用于 prompt-local provenance、不表示 request event 存在。行为完全未修改——旧代码已经是 `tool_call_event_ref = row.event_id`，只是缺少语义说明。`_readable_query_text_from_envelope` 继续在 `requested_event_ref is None` 时走 limited-signal 路径（L2160-2164），与 fallback 语义一致——provenance label 和 query text 各自独立处理 None 情况。

### ✅ DS-F1 / DS-R3: `_snapshot_with_goal` 冗余参数/helper 清理

**Fix**: 
- `_snapshot_with_goal` helper 已完全删除（grep 确认测试文件中无残留）
- `_snapshot_with_fact` 签名改为只接受实际使用的参数：`snapshot_id`、`checkpoint_event_sequence`、`claim_text`、`provenance_event_id`、`tool_result_ref`——不再接受 `current_goal`
- 原调用点全部更新：
  - `test_vnext_snapshot_does_not_bridge_old_goal_into_previous_view` → 改用 `_empty_snapshot`
  - `test_pre_dispatch_builder_ignores_memory_snapshot_lag_or_missing` → 改用 `_snapshot_with_fact`
  - `test_pre_dispatch_represented_evidence_refs_only_from_latest_compact` → 改用 `_snapshot_with_fact`
  - 内部调用 `_snapshot_with_stable_blocks` → 改用 `_snapshot_with_fact`

**审查结论**: ✅ 通过。冗余 helper 完全移除，保留的 helper 只接受实际使用的参数。所有调用点不传 misleading `current_goal`。测试代码更清晰，读者不会误解参数行为。

### ✅ DS-F2: memory fact fixture provenance 不再引用不存在 event id

**Fix**:
- 硬编码 `"event-memory-compact"` 已从代码中完全移除（grep 确认仅 review document 中有历史引用）
- `_snapshot_with_fact` 新增 `provenance_event_id` 和 `tool_result_ref` 参数，由调用方显式传入
- 两处调用方传入了测试 EventLog 中实际存在的 event id：
  - `test_pre_dispatch_builder_ignores_memory_snapshot_lag_or_missing` → `provenance_event_id="event-user-memory-independent"`（对应 L1087 写入的 `USER_INPUT_ACCEPTED` event）
  - `test_pre_dispatch_represented_evidence_refs_only_from_latest_compact` → `provenance_event_id="event-tool-result-after-compact"`（对应 L1143 写入的 `TOOL_RESULT_ACCEPTED` event）
- `tool_result_ref` 按语义设置：无工具结果时为 `None`，有工具结果时指向对应的 `TOOL_RESULT_ACCEPTED` event id

**审查结论**: ✅ 通过。fixture provenance 现在使用测试 EventLog 中实际存在的 event id，不会再误导维护者。`tool_result_ref` 的语义化传入使 fixture 更自文档化。

## 新问题检查

**无新 findings**。对 fix diff 的逐行审查确认：

- 新增的 3 个测试函数结构正确：`pytest.raises` 匹配精确错误消息，不会误通过
- `_snapshot_with_fact` 的签名字段全部有中文 docstring 说明（L1751-1755），类型标注严格
- 删除 `_snapshot_with_goal` 不影响任何其他测试模块（grep 确认全仓库无其他引用）
- `_accepted_tool_evidence_delta_blocks` docstring 修改仅增加说明段落，不改变 behavior
- 无新增类型错误、无 Any/object 逃逸、无架构反向依赖

## Blocking Open Questions

无。

## Fixed Findings Status

| Finding | Status | 证据 |
|---|---|---|
| MiMo F1: CompactMaterialSourceBoundary negative tests | ✅ fixed | `test_compact_material_source_boundary_rejects_inverted_delta_boundary`、`test_compact_material_source_boundary_rejects_delta_end_mismatch` |
| MiMo F2: PreDispatchCompactMaterialView negative tests | ✅ fixed | `test_pre_dispatch_material_view_rejects_boundary_field_mismatches` |
| MiMo F3: tool_call_event_ref fallback semantics | ✅ fixed | docstring L2063-2066 + 行内注释 L2106 |
| DS-F1/DS-R3: _snapshot_with_goal 冗余参数 | ✅ fixed | helper 已删除，调用点改用 _empty_snapshot 或 _snapshot_with_fact |
| DS-F2: fixture provenance event id | ✅ fixed | 硬编码 event-memory-compact 已替换为实际 event id |

## Residual Risks

- **DS-R1 (unchanged)**: `_readable_query_text_from_envelope` 完整 query atom 路径仍缺模块内直接测试覆盖。本 gate 不处理（deferred-with-owner，Owner: WU-PROJ-01 Slice 2）。
- **DS-R2 (unchanged)**: `_validated_current_input_event` 失败分支无独立单元测试。本 gate 不处理（deferred-with-owner，Owner: 后续 test hardening）。
- **DS-F3 (unchanged)**: `PreDispatchCompactMaterialView` 扁平字段冗余仍为 informational。本 gate 不处理（accepted plan 允许，deferred-with-owner）。
- **DS-F4/DS-R1 (unchanged)**: `_readable_query_text_from_envelope` 完整 query atom 路径缺模块内直接覆盖。本 gate 不处理。

以上 residual risks 均不在本次 fix gate scope 内，且已有明确的 owner 和后续计划。

## 总结

AgentCodex 的 fix 正确、完整、最小化。5 条 accepted findings 全部修复，测试从 28 增加到 31，pyright 保持 0 errors。fix 未扩散到 allowed files 之外，未修改 design docs、control doc 或 README。可进入下一 gate。
