# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-dur-obs-cm-closeout`
- Base: `main`
- Output file: `docs/reviews/wu-dur-obs-cm-closeout-slice4-code-review-mimo.md`
- Included scope: `dayu/host/tool_trace.py`、`dayu/host/durable/tool_trace.py`、`tests/host/test_tool_trace_projection.py`、`tests/host/test_tool_trace_queries.py`、`dayu/host/README.md`、`tests/README.md`
- Excluded scope: `docs/host/design.md`（按 Slice 4 指令不编辑）、Slice 5/6/7 范围
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Review Points 逐项审查

### Review Point 1: RUNNER_CALL_INPUT_ASSEMBLED projection 字段复制

**判定：accepted。**

- `_extract_runner_call_trace()` 从 canonical payload 读取 `runner_call_index`、`runner_call_kind`、`runner_call_trigger_reason`、`iteration_id`、`manifest_payload_ref`、`manifest_digest`、`message_count`、`role_sequence_digest`、`input_projection_digest`、`projector_metadata_summary` 和 `diagnostic`。所有字段经由 `_optional_text()`、`_optional_int()` 或 `_runner_call_trace_summary()` 提取。
- Hot row 的 `result_digest` 存储 `manifest_digest`，`payload_ref` 存储 `manifest_payload_ref`，`payload_digest` 存储 `manifest_digest`。`trace_summary` 包含完整 runner-call signal。
- Cold JSONL `trace_summary` 与 hot row `trace_summary` 一致（`test_tool_trace_projects_runner_call_manifest_signal` 行 533 断言）。
- `projector_metadata_summary` 经 `_runner_call_projector_metadata_summary()` 验证每个 item 是 Mapping，并提取 5 个必填字段（`projector_metadata_id`、`projector_id`、`projector_schema_version`、`projector_digest`、`purpose`）。
- 设计 contract 中要求的 `projector_metadata_id`、`projector_id`、`projector_schema_version`、`projector_digest`、`purpose` 全部覆盖。

### Review Point 2: 非 complete signal 缺少 typed diagnostic 的 fail-closed

**判定：accepted。**

- `dayu/host/tool_trace.py:649-651`：非 complete status 时，若 `diagnostic` 不是 Mapping，抛出 `HostDurableError("runner-call diagnostic must be object")`。
- 测试 `test_tool_trace_rejects_non_complete_runner_call_without_diagnostic`（行 609-653）验证 `validation_status="limited_signal"` + `diagnostic=None` 时，`consumer.apply_event()` 抛出 `HostDurableError`。
- WU-DUR-P01-S2-R1 由本实现关闭。

### Review Point 3: Diagnostic enum 封闭校验

**判定：accepted。**

- `_runner_call_status()` (行 732-746)：通过 `RunnerCallReconstructionStatus(value)` 构造，不支持的值抛 `HostDurableError`。
- `_runner_call_reason()` (行 749-763)：通过 `RunnerCallReconstructionDiagnosticReason(value)` 构造，不支持的值抛 `HostDurableError`。
- `_optional_runner_call_missing_atom_kind()` (行 766-783)：通过 `RunnerCallReconstructionMissingAtomKind(value)` 构造，不支持的值抛 `HostDurableError`。
- `_optional_runner_call_missing_ref_kind()` (行 786-806)：通过 `RunnerCallReconstructionMissingRefKind(value)` 构造，不支持的值抛 `HostDurableError`。
- 查询层 `_runner_call_status_from_text()`、`_optional_runner_call_reason_from_text()`、`_optional_runner_call_missing_atom_kind_from_text()`、`_optional_runner_call_missing_ref_kind_from_text()`、`_runner_call_consumer_boundary_from_text()` 均使用 enum 构造做封闭校验。
- Projection 层 `_runner_call_diagnostic()` 对 `validation_status` 做 enum 校验；diagnostic 内部字段的 reason / missing_atom_kind / missing_ref_kind 由查询层在读取时二次校验。
- 两层共同保证 unsupported enum 值不会穿透。

### Review Point 4: read_runner_call_reconstruction_signals_by_run 查询 helper

**判定：accepted。**

- `dayu/host/durable/tool_trace.py:544-572`：查询只读 `host_tool_trace_hot` 表，WHERE 条件为 `run_id = ? AND event_type = 'RUNNER_CALL_INPUT_ASSEMBLED'`。
- 使用 `_query_page()` 分页，按 `event_sequence ASC` 排序，`limit+1` 预取判断 `has_more`。
- 返回 `RunnerCallReconstructionSignalPage`，signal 由 `_runner_call_signal_from_hot_row()` 从 hot row `trace_summary` JSON 构造 typed 对象。
- Signal 字段类型：`runner_call_index: int | None`、`runner_call_kind: str | None`、`runner_call_trigger_reason: str | None`、`diagnostic: RunnerCallReconstructionDiagnostic`（必填）。
- `diagnostic` 从 `trace_summary` 读取后做完整 enum 校验：status、reason、missing_atom_kind、missing_ref_kind、consumer_boundary 全部通过封闭 enum 构造。
- 测试 `test_runner_call_reconstruction_signal_query_classifies_statuses` 覆盖 complete / limited_signal / mismatch 三种 status 的 query 行为。

### Review Point 5: Producer-boundary missing ref kind 归一化

**判定：accepted。**

- `dayu/host/tool_trace.py:800-802`：`_optional_runner_call_missing_ref_kind()` 检测 producer 写入的 `"runner_call_projection_artifact"` 标签，归一为 `RunnerCallReconstructionMissingRefKind.ARTIFACT_REF.value`。
- 该归一在 Tool Trace projection 层完成，查询消费者不会看到 producer-boundary 内部标签。
- 测试 `test_tool_trace_projects_limited_runner_call_manifest_diagnostic` (行 536-606) 验证 producer 写入 `missing_ref_kind: "runner_call_projection_artifact"` → trace summary 归一为 `"artifact_ref"`。
- 查询层 test `test_runner_call_reconstruction_signal_query_classifies_statuses` (行 397-399) 验证 `limited.diagnostic.missing_ref_kind is RunnerCallReconstructionMissingRefKind.ARTIFACT_REF`。
- cold JSONL `trace_summary` 与 hot row 一致（行 606 断言）。

### Review Point 6: 测试覆盖

**判定：accepted。**

覆盖矩阵：

| 场景 | 测试函数 | 文件 |
|---|---|---|
| complete signal projection | `test_tool_trace_projects_runner_call_manifest_signal` | test_tool_trace_projection.py:464 |
| limited_signal diagnostic projection | `test_tool_trace_projects_limited_runner_call_manifest_diagnostic` | test_tool_trace_projection.py:536 |
| 非 complete 缺 diagnostic fail-closed | `test_tool_trace_rejects_non_complete_runner_call_without_diagnostic` | test_tool_trace_projection.py:609 |
| mismatch diagnostic projection | `test_tool_trace_projects_mismatch_runner_call_diagnostic` | test_tool_trace_projection.py:655 |
| 大参数不内联 | `test_tool_trace_does_not_inline_large_tool_call_arguments` | test_tool_trace_projection.py:403 |
| query complete / limited / mismatch | `test_runner_call_reconstruction_signal_query_classifies_statuses` | test_tool_trace_queries.py:266 |

覆盖了 plan 要求的 complete、limited_signal、mismatch、fail-closed missing diagnostic、query behavior。

### Review Point 7: README 更新

**判定：accepted。**

- `dayu/host/README.md`（行 202-203）：新增 `RUNNER_CALL_INPUT_ASSEMBLED` canonical fact 和 manifest 描述，说明 Tool Trace 复制 runner-call signal 和 typed query helper。内容只描述已实现行为，不写未来设计。
- `tests/README.md`（行 129）：更新 Host 测试覆盖描述，补充 runner-call signal projection、fail-closed diagnostic、mismatch、typed query helper 覆盖。
- 两个 README 更新在正确文档中，不越界。

## 其它架构观察

### consumer_boundary 投影归一

Projection 层 (`tool_trace.py:646,684`) 固定将 `consumer_boundary` 归一为 `"tool_trace_query"`，不论 producer 写入什么值。这是当前正确行为，因为 Tool Trace hot projection 的唯一消费者就是 Tool Trace query path。未来若有 analyzer_fixture 或 compact_evidence_projection 直接消费 hot projection，需在 projection 层区分 consumer boundary。当前设计中 analyzer 走 query helper，不直接读 hot projection JSON，所以无实际影响。

### runner_call_kind / runner_call_trigger_reason 类型

查询层 `RunnerCallReconstructionSignal.runner_call_kind` 和 `runner_call_trigger_reason` 为 `str | None`，未在查询层做 enum 封闭校验。Projection 层通过 `_optional_text()` 读取为文本。Design contract 要求 `RunnerCallKind` 和 `RunnerCallTriggerReason` 是封闭枚举。当前 projection 层读取合法文本值，但若 producer 写入非法 enum 值，projection 层不拒绝，只有查询层如果加 enum 校验才能拦截。当前查询层未做该校验，依赖 producer（engine_ingest）保证值合法。不构成 correctness 风险，但可作为后续 hardening 点。

## Open Questions

无。

## Residual Risk

- 查询层对 `runner_call_kind` / `runner_call_trigger_reason` 未做 enum 封闭校验。当前 producer 保证写入合法值；若需更高防御，可在 `_runner_call_signal_from_hot_row()` 增加 enum 验证。
- 无 negative test 覆盖查询层 enum 校验失败路径（例如非法 reason 值在 hot row 中被查询读取时的行为）。Projection 层有对应失败路径测试，正常路径不会到达查询层的非法值。

## Implementation Status by Review Point

| Review Point | 状态 |
|---|---|
| 1. Projection 字段复制 | accepted |
| 2. Non-complete fail-closed | accepted |
| 3. Diagnostic enum 封闭 | accepted |
| 4. Query helper contract | accepted |
| 5. Ref kind 归一化 | accepted |
| 6. 测试覆盖 | accepted |
| 7. README 更新 | accepted |

## Tests / Pyright Evidence

- `pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py`：15 passed
- `pyright dayu/host/tool_trace.py dayu/host/durable/tool_trace.py`：0 errors, 0 warnings

## WU-DUR-P01-S2-R1 关闭状态

已关闭。`test_tool_trace_rejects_non_complete_runner_call_without_diagnostic` 直接覆盖了 S2-R1 要求的 Tool Trace fail-closed behavior（non-complete signal 缺 diagnostic object 时抛 durable error）。Control doc 中 S2-R1 状态应从 `deferred-with-owner` 更新为 `closed`。

## Verdict

**pass**

## Ready for Controller Adjudication

**yes**
