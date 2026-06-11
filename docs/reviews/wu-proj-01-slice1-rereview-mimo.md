# WU-PROJ-01 Slice 1 Re-Review — AgentMiMo

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: Slice 1 re-review gate
- Reviewer: AgentMiMo
- 日期: 2026-06-11
- Fix artifact: `docs/reviews/wu-proj-01-slice1-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-proj-01-slice1-code-review-controller-adjudication.md`
- Previous MiMo review: `docs/reviews/wu-proj-01-slice1-code-review-mimo.md`
- Previous DS review: `docs/reviews/wu-proj-01-slice1-code-review-ds.md`
- Re-review scope: `dayu/host/compact_material.py`, `tests/host/test_compact_material.py`

## Verdict

**PASS** — 5 条 accepted findings 全部 fixed，fix 未引入新 correctness / type / test / architecture 问题。

## 独立验证

| 检查项 | 结果 |
|---|---|
| `pytest tests/host/test_compact_material.py` | 31 passed, 0.29s |
| `pyright dayu/host/compact_material.py tests/host/test_compact_material.py` | 0 errors, 0 warnings, 0 informations |

测试从 28 passed 增长到 31 passed（新增 3 条 direct negative test），与 fix report 声明一致。

## Accepted Findings Fix Status

### MiMo F1: CompactMaterialSourceBoundary direct negative tests — ✅ FIXED

**要求**: 补 direct negative tests 覆盖 inverted boundary 和 delta end mismatch。

**验证**:
- `test_compact_material_source_boundary_rejects_inverted_delta_boundary`（line 883）：构造 `post_compact_delta_start_sequence=4 > post_compact_delta_end_sequence=3`，断言 `pytest.raises(ValueError, match="post compact delta boundary is inverted")`。
- `test_compact_material_source_boundary_rejects_delta_end_mismatch`（line 896）：构造 `post_compact_delta_end_sequence=3 != current_input_event_sequence=4`，断言 `pytest.raises(ValueError, match="delta end sequence must equal current input sequence")`。

两条测试直接命中 `CompactMaterialSourceBoundary.__post_init__` 的 L386-389 校验路径，覆盖完整。

### MiMo F2: PreDispatchCompactMaterialView direct negative tests — ✅ FIXED

**要求**: 补 direct negative tests 覆盖便捷字段与 `source_boundary` 不一致时抛 `ValueError`。

**验证**: `test_pre_dispatch_material_view_rejects_boundary_field_mismatches`（line 912）：
1. 先构造一个 valid boundary 和 valid view。
2. 用 `dataclasses.replace` 逐一修改四个便捷字段，每次断言对应的 `ValueError`：
   - `latest_compacted_event_id` → `"latest compacted event id boundary mismatch"`
   - `latest_compacted_event_sequence` → `"latest compacted event sequence boundary mismatch"`
   - `post_compact_delta_start_sequence` → `"post compact delta start boundary mismatch"`
   - `post_compact_delta_end_sequence` → `"post compact delta end boundary mismatch"`

四条 mismatch 路径全部覆盖，与 `__post_init__` L435-451 校验逻辑一一对应。

### MiMo F3: fallback `tool_call_event_ref` 语义说明 — ✅ FIXED

**要求**: 在 docstring / 注释中明确 fallback 语义。

**验证**:
- `_accepted_tool_evidence_delta_blocks` docstring（L2061-2066）新增："当 accepted evidence envelope 缺少 durable request atom 时，``tool_call_event_ref`` 会退化为当前 producer event ref。这个 ref 只用于 prompt-local provenance 追溯，不表示对应的 ``TOOL_CALL_REQUESTED`` event 一定存在。"
- 行内注释（L2106）："缺少 request atom 时只保留本地 provenance 线索，不伪造 request event。"

语义描述准确，与代码行为一致：`envelope.tool_query.tool_call_requested_event_ref is None` 时 fallback 到 `row.event_id`（producer event），`_readable_query_text_from_envelope` 在 `requested_event_ref is None` 时走 limited-signal 路径。

### DS-F1 / DS-R3: `_snapshot_with_goal` 冗余参数/helper 清理 — ✅ FIXED

**要求**: 移除冗余参数或改造 helper，使调用点只传实际使用的参数。

**验证**:
- `grep -n "_snapshot_with_goal" tests/host/test_compact_material.py` 返回空——函数已完全删除。
- 原先 3 处调用已改为直接使用 `_empty_snapshot`（lines 216, 629, 661 等），不再传入无用的 `current_goal` 参数。
- `_snapshot_with_fact`（line 1741）只接收实际使用的参数：`snapshot_id`、`checkpoint_event_sequence`、`claim_text`、`provenance_event_id`、`tool_result_ref`。

清理干净，无残留。

### DS-F2: memory fact fixture provenance 不再引用不存在 event id — ✅ FIXED

**要求**: 将 fixture provenance 调整为不误导维护者的值。

**验证**:
- `_snapshot_with_fact` 签名（line 1741）已参数化：接受 `provenance_event_id: str` 和 `tool_result_ref: str | None`。
- 原硬编码 `"event-memory-compact"` 已消除。
- 调用点使用实际存在于测试 EventLog 的 event id：
  - `test_pre_dispatch_builder_ignores_memory_snapshot_lag_or_missing`（line 1073）：`provenance_event_id="event-user-memory-independent"`，`tool_result_ref=None`。该 event id 在同测试 seed 中通过 `_append_event` 实际写入（line 1085）。
  - `test_pre_dispatch_represented_evidence_refs_only_from_latest_compact`（line 1126）：`provenance_event_id="event-tool-result-after-compact"`，`tool_result_ref="event-tool-result-after-compact"`。该 event id 在同测试 seed 中实际写入（line 1145）。
  - `_snapshot_with_stable_blocks`（line 1813）：`provenance_event_id="event-stable-memory-source"`，`tool_result_ref=None`。此 snapshot 仅用于 previous view 映射测试，不涉及 EventLog provenance 回查。

provenance 语义准确，不再有不存在的 event id。

## New Findings

无新增 findings。所有 fix 均为：
- 新增 direct negative test（纯测试增量，不影响 production 代码）。
- docstring / 注释改进（纯文档，不影响行为）。
- 删除冗余 test helper（`_snapshot_with_goal` 被 `_empty_snapshot` 替代，行为等价）。
- fixture 参数化（`_snapshot_with_fact` 签名变更，调用点语义不变）。

## Blocking Open Questions

无。

## Residual Risks

- **R1 [deferred-with-owner]**: Slice 1 只落地 builder 与 pack 显式 previous-view path，尚未改 dispatch proactive call path。Owner: WU-PROJ-01 Slice 2。（与前次 review 一致，非本轮 fix 范围。）
- **R2 [deferred-with-owner]**: `_readable_query_text_from_envelope` 的非 limited-signal 路径缺少模块内直接测试覆盖（DS-F4 / DS-R1）。Owner: Slice 2 或后续 focused test cleanup。（前次 review 已识别，非本轮 fix 范围。）
- **R3 [deferred-with-owner]**: `_validated_current_input_event` 的失败分支无独立单元测试（DS-R2）。Owner: 后续 test hardening。（前次 review 已识别，非本轮 fix 范围。）
- **R4 [informational]**: `pyright` 提示新版本 `1.1.410` 可用，当前验证使用 `1.1.409`。不影响本轮结果。

## 总结

5 条 accepted findings 全部按 controller adjudication 要求完成 fix：
- F1 / F2：新增 3 条 direct negative test，覆盖 `CompactMaterialSourceBoundary` 和 `PreDispatchCompactMaterialView` 的 `__post_init__` 校验路径。
- F3：docstring 和行内注释准确描述了 fallback `tool_call_event_ref` 的退化语义。
- DS-F1/DS-R3：`_snapshot_with_goal` 冗余 helper 完全删除，调用点改用 `_empty_snapshot`。
- DS-F2：`_snapshot_with_fact` provenance 参数化，不再使用不存在的硬编码 event id。

31 tests passed，pyright 0 errors，fix 未引入新问题。Slice 1 re-review gate 通过。
