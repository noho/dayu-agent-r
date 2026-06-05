# WU-DUR-P01 Slice 3 Fix Re-Review (AgentDS)

## Verdict

**pass**

四项 accepted findings 全部 fixed。reactive CONTEXT_COMPACTED 和 CONTEXT_COMPACTION_ATTEMPT_REJECTED 现在通过共享 `DurableCompactorProposalManifestRecorder` 正确携带 proposal manifest ref/digest。proactive 路径保持 fail-closed guard 且无回归。deferred findings 未被 fix 变更改坏。未发现提供方完整请求/消息写入 hot EventLog payload、generic fake compactor 路径退化、或新增层面穿透/过度耦合。

## Accepted Findings Status

### F1: Reactive compaction 路径未接入 proposal manifest ref — **fixed**

**证据**：

- `engine_ingest.py:1582-1594` (`_execute_reactive_compaction`): 调用 `run_compaction_operation()` 时传入 `proposal_manifest_recorder=self._compactor_proposal_manifest_recorder()` 与 `compaction_operation_id=pending.operation_id`。
- `engine_ingest.py:1758-1776` (`_compactor_proposal_manifest_recorder`): 构造 `DurableCompactorProposalManifestRecorder`，event_source 为 `host.engine_ingest`，使用 `self._compact_artifact_root` 作为 artifact root。
- `engine_ingest.py:1715-1735` (accepted 分支): `_append_reactive_compacted_event()` 接收 `accepted_proposal_manifest_ref` 和 `accepted_proposal_manifest_digest` 并传入 `build_context_compacted_payload()`。
- `engine_ingest.py:1879-1882`: `build_context_compacted_payload()` 调用携带 `accepted_proposal_manifest_ref` / `accepted_proposal_manifest_digest`。
- `engine_ingest.py:1729-1734`: 从 `operation_result.accepted_proposal_manifest_ref` / `accepted_proposal_manifest_digest` 提取值（泛型路径时为 `None`，prepared 路径时为字符串）。

测试 `test_reactive_prepared_compaction_records_accepted_proposal_manifest` 验证 reactive CONTEXT_COMPACTED payload 携带 `accepted_proposal_manifest_ref`（以 `runner-call-manifest:` 开头）和 `accepted_proposal_manifest_digest`，且 `RUNNER_CALL_INPUT_ASSEMBLED` event 已被写入。

### F2: Reactive rejected attempt 路径未接入 proposal manifest ref — **fixed**

**证据**：

- `engine_ingest.py:1635-1643`: `_operation()` 内对每个 rejected attempt 调用 `_append_reactive_compaction_attempt_rejected_event()`。
- `engine_ingest.py:1973-2031` (`_append_reactive_compaction_attempt_rejected_event`): 调用 `build_context_compaction_attempt_rejected_payload()` 时传入 `proposal_manifest_ref=rejected.proposal_manifest_ref` 和 `proposal_manifest_digest=rejected.proposal_manifest_digest`（lines 2025-2026）。
- `engine_ingest.py:1637`: 传入的 `rejected` 来自 `operation_result.rejected_attempts`，其 `proposal_manifest_ref` / `proposal_manifest_digest` 由 `_attempt_rejected()` (compaction_operation.py:1298-1307) 从 `proposal_manifest_reference` 解包。

测试 `test_reactive_prepared_rejected_attempt_records_proposal_manifest` 验证 reactive rejected 路径 payload 携带 `proposal_manifest_ref`（以 `runner-call-manifest:` 开头）和 `proposal_manifest_digest`。

### F3: Proactive 路径 manifest ref/digest 保持正确 — **confirmed, no regression**

**证据**：

- `dispatch.py:1173-1187` (`_execute_proactive_compaction`): 调用 `run_compaction_operation()` 时传入 `proposal_manifest_recorder=self._compactor_proposal_manifest_recorder()`。
- `dispatch.py:1278-1298` (`_compactor_proposal_manifest_recorder`): 构造 `DurableCompactorProposalManifestRecorder`，event_source 为 `host.dispatch`，使用 `self._local_execution.compact_artifact_root`。
- `dispatch.py:1264-1269` (accepted 分支): 通过 `_required_compactor_manifest_ref(result)` / `_required_compactor_manifest_digest(result)` 做 fail-closed 提取，然后传入 `_append_compacted_event()`。
- `dispatch.py:1212-1218` (rejected 分支): `_append_compaction_attempt_rejected_event()` 调用 `build_context_compaction_attempt_rejected_payload()` 时传入 `rejected.proposal_manifest_ref` / `rejected.proposal_manifest_digest`。
- `dispatch.py:2014-2018` (proactive `_append_compaction_attempt_rejected_event`): `proposal_manifest_ref=rejected.proposal_manifest_ref` / `proposal_manifest_digest=rejected.proposal_manifest_digest`。

已有 proactive 路径测试持续通过（`test_run_compaction_operation_records_prepared_proposal_manifest_before_call`、`test_run_compaction_operation_rejected_attempt_keeps_proposal_manifest_ref`、`test_proactive_compact_duplicate_prompt_does_not_exceed_compactor_window`）。

### F4: Accepted missing proposal manifest ref/digest fail-closed guard 有直接聚焦测试 — **fixed**

**证据**：

- `test_compaction_operation.py` 新增 `test_accepted_compaction_missing_proposal_manifest_guard_fails_closed`：直接构造 `CompactionOperationResult(accepted_proposal_manifest_ref=None, ...)` 和 `CompactionOperationResult(accepted_proposal_manifest_digest=None, ...)`，分别调用 `dispatch._required_compactor_manifest_ref()` 和 `dispatch._required_compactor_manifest_digest()`，断言两者均抛出 `RuntimeError`。
- `dispatch.py:3734-3762` (`_required_compactor_manifest_ref` / `_required_compactor_manifest_digest`): fail-closed guard 检查 `None` 或空白字符串。

## New Findings

### N1: `DurableCompactorProposalManifestRecorder` 未列入 `compaction_operation.__all__` (LOW)

- **入口/函数**: `dayu/host/compaction_operation.py` `__all__` 导出列表
- **文件(行号)**: `compaction_operation.py:1431-1437`
- **输入场景**: 任何使用 `from dayu.host.compaction_operation import *` 的代码
- **实际分支**: `__all__` 仅包含 `CompactionAttemptRejected`、`CompactionFailureCategory`、`CompactionNextPolicyDecision`、`CompactionOperationResult`、`run_compaction_operation`，不包含 `DurableCompactorProposalManifestRecorder`。
- **预期行为**: 作为被 `dispatch.py` 和 `engine_ingest.py` 直接导入的公开具体类，应列入 `__all__`。
- **实际行为**: `from dayu.host.compaction_operation import *` 不会导出该类。
- **直接证据**: `compaction_operation.py:1431-1437` 与 `dispatch.py:159` / `engine_ingest.py:88` 的直接 import 语句不一致。
- **影响**: 不影响当前任何代码路径（两个调用方均使用显式 import）；若未来使用 `import *` 则会静默缺失。仅模块组织一致性问题。
- **建议改法和验证点**: 将 `"DurableCompactorProposalManifestRecorder"` 加入 `__all__` 列表。
- **修复风险（低）**: 纯声明性变更，不影响运行时行为。
- **严重程度（低）**:

## Deferred Findings 未回归检查

四项 deferred findings 均未被 fix 变更改坏：

| Deferred Finding | 状态 | 证据 |
|---|---|---|
| D1: initial compactor proposal trigger reason 枚举精度 | 未回归 | `_compactor_trigger_reason()` (compaction_operation.py:1124-1133) 未被本 fix 修改，行为保持不变 |
| D2: outcome-dependent CompactorRunnerCallIdentity refs | 未回归 | `_compactor_runner_call_manifest_body()` (compaction_operation.py:827-905) 未被本 fix 修改，`compactor_identity` 字段保持不变 |
| D3: artifact filesystem/SQLite transaction boundary | 未回归 | `DurableCompactorProposalManifestRecorder.record_compactor_proposal_manifest()` 仍使用相同的 `write_artifact_bytes` → `write_payload_descriptor_for_artifact` → `append_event` 模式，未改变事务边界 |
| D4: Tool Trace analyzer consumption | 未回归 | 本 fix 未实现任何 Tool Trace 相关代码 |

## Review Constraints 专项检查

### No new overcoupling from moving DurableCompactorProposalManifestRecorder

**通过**。将 `DurableCompactorProposalManifestRecorder` 从 `dispatch.py` 移到 `compaction_operation.py` 属于 **解耦**：具体实现现在与协议定义（`CompactorProposalManifestRecorder`）和使用方（`run_compaction_operation()`）在同一模块。`dispatch.py` 和 `engine_ingest.py` 通过统一的 import 路径引入，无交叉依赖。

`compaction_operation.py` 不导入 `dispatch` 或 `engine_ingest`，无循环依赖。两个调用方各自通过自己层的 `_compactor_proposal_manifest_recorder()` factory 构造 recorder，仅传递不同 `event_source`。没有跨层穿透、双向依赖或共享可变状态。

### No full provider request/messages in hot EventLog payload

**通过**。`_compactor_runner_call_hot_payload()` (compaction_operation.py:908-953) 仅包含 manifest 摘要字段：
- `session_id`、`host_run_id`、`attempt_id`、`execution_id`
- `runner_call_index`、`runner_call_kind`、`runner_call_trigger_reason`
- `manifest_payload_ref`、`manifest_digest`、`manifest_schema_version`
- `validation_status`、`message_count`、`role_sequence_digest`、`input_projection_digest`
- `projector_metadata_summary`、`diagnostic`

不包含 provider 请求体、完整 message content、API key、headers 或 runner response。Manifest body 和 compactor input projection 通过 artifact store 持久化，通过 `payload_descriptor` 引用，不进入 hot payload。

### Generic non-prepared fake compactor behavior remains valid

**通过**。`_prepare_compactor_proposal()` (compaction_operation.py:776-783) 的 else 分支对非 `CompactorProposalPreparedCompactor` 的 compactor 保持原有行为：
- 通过 `conversation_compact_input_vnext_from_material_pack()` 构造 input
- 直接调用 `compactor.compact(request, cancellation_token)`
- `proposal_manifest_reference=None`

`_attempt_rejected()` (compaction_operation.py:1298-1307) 在 `proposal_manifest_reference is None` 时正确返回 `proposal_manifest_ref=None` 和 `proposal_manifest_digest=None`。`CompactionOperationResult` 的 `accepted_proposal_manifest_ref` 和 `accepted_proposal_manifest_digest` 同样为 `None`。类型边界使用 `isinstance(compactor, CompactorProposalPreparedCompactor)`，其中 `CompactorProposalPreparedCompactor` 为 `@runtime_checkable` Protocol，非 `hasattr`/`getattr` 弱设计。

## Tests / Pyright Evidence Reviewed

- **Tests**: 根据 fix artifact 报告，94 passed, 1 skipped
  - `test_reactive_prepared_compaction_records_accepted_proposal_manifest` — 验证 reactive CONTEXT_COMPACTED 携带 manifest ref/digest
  - `test_reactive_prepared_rejected_attempt_records_proposal_manifest` — 验证 reactive CONTEXT_COMPACTION_ATTEMPT_REJECTED 携带 manifest ref/digest
  - `test_accepted_compaction_missing_proposal_manifest_guard_fails_closed` — 验证 fail-closed guard
  - `test_run_compaction_operation_records_prepared_proposal_manifest_before_call` — 验证 manifest 在 call 前记录（proactive，持续通过）
  - `test_run_compaction_operation_rejected_attempt_keeps_proposal_manifest_ref` — 验证 rejected attempt 携带 manifest（proactive，持续通过）
- **Pyright**: 0 errors, 0 warnings, 0 informations（根据 fix artifact 报告）
- **git diff --check**: 通过（根据 fix artifact 报告）

## Residual Risks

1. **Reactive 路径对 generic (non-prepared) compactor 的 manifest 为 None**: 当 `_execute_reactive_compaction` 使用的 compactor 不实现 `CompactorProposalPreparedCompactor` 时，`accepted_proposal_manifest_ref` / `accepted_proposal_manifest_digest` 为 `None`。这与 proactive 路径的 fail-closed 行为不一致（proactive 路径通过 `_required_compactor_manifest_ref` 硬性要求 manifest）。当前生产环境 reactive compactor 为 `LLMContextCompactor`（实现 `CompactorProposalPreparedCompactor`），所以此差异不造成生产影响。若未来 reactive 路径替换为非 prepared compactor，需注意此行为差异。
2. **`DurableCompactorProposalManifestRecorder` `__all__` 缺失**: 见 N1。
3. **Deferred 四项风险持续存在**: D1-D4 均未在本 fix 中处理，需后续 design contract / follow-up slice 处理。

## Ready for Controller Adjudication

**Yes.** 四项 accepted findings 全部 fixed，无新增 correctness blocker，无 deferred finding 回归，测试和 pyright 通过。
