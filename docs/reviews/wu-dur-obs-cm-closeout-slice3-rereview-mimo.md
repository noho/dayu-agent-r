# WU-DUR-P01 Slice 3 Fix Re-Review — AgentMiMo

## Verdict

pass

## Reviewed Inputs

- `docs/reviews/wu-dur-obs-cm-closeout-slice3-code-review-controller-adjudication.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice3-fix-codex.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice3-implementation-retry-codex.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice3-code-review-mimo.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice3-code-review-ds.md`
- `docs/host/design.md`
- 当前 diff：`dayu/host/compaction_operation.py`、`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py`、`dayu/host/context_events.py`、`dayu/host/durable/schema.py`、测试与 README

## Scope

- Mode: current changes（re-review after fix）
- Branch: `phaseflow/wu-dur-obs-cm-closeout`
- Base: `main`
- Gate: re-review after fix
- Timestamp: 2026-06-05

## Accepted Findings 验证

### AF1. Reactive compaction prepared compactor path records durable compactor proposal manifest and carries accepted_proposal_manifest_ref/digest into reactive CONTEXT_COMPACTED

**状态：fixed**

**直接证据**：

1. `engine_ingest.py:1591-1593`：`_execute_reactive_compaction()` 向 `run_compaction_operation()` 传入 `proposal_manifest_recorder=self._compactor_proposal_manifest_recorder()`。
2. `engine_ingest.py:1729-1734`：`_append_reactive_compacted_event()` 从 `operation_result.accepted_proposal_manifest_ref` 和 `operation_result.accepted_proposal_manifest_digest` 读取 manifest 引用，传入 `build_context_compacted_payload()`。
3. `engine_ingest.py:1879-1882`：`build_context_compacted_payload()` 调用时携带 `accepted_proposal_manifest_ref` 和 `accepted_proposal_manifest_digest`。
4. `engine_ingest.py:1758-1776`：`_compactor_proposal_manifest_recorder()` 构造 `DurableCompactorProposalManifestRecorder`，使用 `host.engine_ingest` 作为 event source。
5. 测试 `test_reactive_prepared_compaction_records_accepted_proposal_manifest`（`test_engine_ingest_mapping.py:625`）验证 reactive accepted compact payload 携带 `accepted_proposal_manifest_ref`（以 `runner-call-manifest:` 开头）和 `accepted_proposal_manifest_digest`，并验证 `RUNNER_CALL_INPUT_ASSEMBLED` event 被写入。

### AF2. Reactive rejected attempt path carries proposal_manifest_ref/digest into reactive CONTEXT_COMPACTION_ATTEMPT_REJECTED

**状态：fixed**

**直接证据**：

1. `engine_ingest.py:1635-1643`：`_execute_reactive_compaction()` 遍历 `operation_result.rejected_attempts`，调用 `_append_reactive_compaction_attempt_rejected_event()`。
2. `engine_ingest.py:2012-2026`：`_append_reactive_compaction_attempt_rejected_event()` 调用 `build_context_compaction_attempt_rejected_payload()`，传入 `proposal_manifest_ref=rejected.proposal_manifest_ref` 和 `proposal_manifest_digest=rejected.proposal_manifest_digest`。
3. `compaction_operation.py:1298-1307`：`_attempt_rejected()` 从 `proposal_manifest_reference.manifest_payload_ref` 和 `proposal_manifest_reference.manifest_digest` 构造 `CompactionAttemptRejected`。
4. 测试 `test_reactive_prepared_rejected_attempt_records_proposal_manifest`（`test_engine_ingest_mapping.py:778`）验证 reactive rejected attempt payload 携带 `proposal_manifest_ref`（以 `runner-call-manifest:` 开头）和 `proposal_manifest_digest`，并验证 `RUNNER_CALL_INPUT_ASSEMBLED` event 被写入。

### AF3. Proactive path still records manifest before runner call and accepted/rejected payload refs still work

**状态：fixed**

**直接证据**：

1. `dispatch.py:1173-1186`：`_execute_proactive_compaction()` 向 `run_compaction_operation()` 传入 `proposal_manifest_recorder=self._compactor_proposal_manifest_recorder()`。
2. `dispatch.py:1249-1269`：`_append_compacted_event()` 调用时携带 `accepted_proposal_manifest_ref=_required_compactor_manifest_ref(result)` 和 `accepted_proposal_manifest_digest=_required_compactor_manifest_digest(result)`。
3. `dispatch.py:1974-2023`：`_append_compaction_attempt_rejected_event()` 调用 `build_context_compaction_attempt_rejected_payload()`，传入 `proposal_manifest_ref=rejected.proposal_manifest_ref` 和 `proposal_manifest_digest=rejected.proposal_manifest_digest`。
4. 测试 `test_run_compaction_operation_records_prepared_proposal_manifest_before_call`（`test_compaction_operation.py:656`）验证 prepare → record → run 顺序和 accepted result 携带 manifest ref/digest。
5. 测试 `test_run_compaction_operation_rejected_attempt_keeps_proposal_manifest_ref`（`test_compaction_operation.py:683`）验证 rejected attempt 携带 proposal manifest ref/digest。

### AF4. Accepted missing proposal manifest ref/digest fail-closed guard has direct focused coverage

**状态：fixed**

**直接证据**：

1. `dispatch.py:3734-3745`：`_required_compactor_manifest_ref()` 在 `result.accepted_proposal_manifest_ref` 为 `None` 或空字符串时 `raise RuntimeError("accepted compaction is missing proposal manifest ref")`。
2. `dispatch.py:3748-3758`：`_required_compactor_manifest_digest()` 在 `result.accepted_proposal_manifest_digest` 为 `None` 或空字符串时 `raise RuntimeError("accepted compaction is missing proposal manifest digest")`。
3. 测试 `test_accepted_compaction_missing_proposal_manifest_guard_fails_closed`（`test_compaction_operation.py:708`）直接测试两个 `RuntimeError` 路径：
   - `accepted_proposal_manifest_ref=None` + `accepted_proposal_manifest_digest` 有值 → raises `RuntimeError("accepted compaction is missing proposal manifest ref")`
   - `accepted_proposal_manifest_ref` 有值 + `accepted_proposal_manifest_digest=None` → raises `RuntimeError("accepted compaction is missing proposal manifest digest")`

## Review Constraints 验证

### 新耦合检查：DurableCompactorProposalManifestRecorder 移入 compaction_operation.py

**无新耦合**。`compaction_operation.py` 的 import 只依赖标准库、`dayu.contracts`、`dayu.engine.contracts`、`dayu.host.compaction`/`compact_material`/`context_budget`/`context_governance`/`context_policy`/`durable.*`、`dayu.runtime.diagnostic_text`。不 import `dispatch.py` 或 `engine_ingest.py`。`DurableCompactorProposalManifestRecorder` 通过 Protocol（`CompactorProposalManifestRecorder`）暴露，调用方只依赖协议方法签名。proactive dispatch 和 reactive engine ingest 各自构造 recorder 实例，通过显式参数注入 `run_compaction_operation()`，不产生双向依赖。

### Hot EventLog payload 不内联 full provider request/messages

**PASS**。`_compactor_runner_call_hot_payload()`（`compaction_operation.py:908-952`）只包含摘要字段：`session_id`、`host_run_id`、`attempt_id`、`execution_id`、`runner_call_index`、`runner_call_kind`、`runner_call_trigger_reason`、`manifest_payload_ref`、`manifest_digest`、`message_count`、`role_sequence_digest`、`input_projection_digest`、`projector_metadata_summary`、`diagnostic`。manifest body 的 message entries 也只包含 `content_digest`、`content_size_bytes`、`source_refs`，不内联 message content。`compactor_input_projection` 写入 artifact store，通过 descriptor ref 引用，不进入 hot payload。

### Generic non-prepared fake compactor 行为有效性

**PASS**。`FakeContextCompactor`（`tests/host/fake_compaction.py:39`）实现 `ContextCompactor` 但不实现 `CompactorProposalPreparedCompactor`。在 `_prepare_compactor_proposal()`（`compaction_operation.py:748-783`）中，`isinstance(compactor, CompactorProposalPreparedCompactor)` 为 `False` 时走 `else` 分支：直接调用 `compactor.compact(request, cancellation_token)`，返回 `_CompactorProposalAttempt(proposal_manifest_reference=None)`。多个测试使用 `FakeContextCompactor`（如 `test_reactive_compaction_calls_llm_outside_write_transaction`、`test_reactive_freezes_overflow_material_list_before_compaction` 等），验证 generic path 不产生 manifest 但不影响 compaction 正常完成。

## Deferred Findings 回归检查

controller adjudication 明确 deferred 的 4 项 finding 不应被视为 unfixed，除非 fix 将其回归为 correctness blocker。逐项检查：

| Deferred Finding | 回归检查 | 结论 |
|---|---|---|
| D1: initial compactor proposal trigger reason enum precision | `_compactor_trigger_reason()`（`compaction_operation.py:1124-1133`）逻辑未变，attempt_number <= 1 仍返回 `context_compaction_repair_attempt`。无回归。 | 无回归 |
| D2: outcome-dependent CompactorRunnerCallIdentity refs | manifest body 中 `compactor_identity`（`compaction_operation.py:895-903`）仍不含 `accepted_context_compacted_event_ref` / `rejected_attempt_diagnostic_ref`。`CONTEXT_COMPACTED` payload 通过 `accepted_proposal_manifest_ref` 建立反向引用。无回归。 | 无回归 |
| D3: artifact filesystem/SQLite transaction boundary | `_DurableCompactorProposalManifestRecorder.record_compactor_proposal_manifest()`（`compaction_operation.py:230-335`）仍在 `transaction_runner.run_write()` 内先写 artifact 后写 SQLite。这是 pre-existing pattern，非本 fix 引入。无回归。 | 无回归 |
| D4: Tool Trace analyzer consumption | 未实现，不在本 fix scope。无回归。 | 无回归 |

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

1. **Reactive fail-closed guard 未直接覆盖**：reactive accepted path（`engine_ingest.py:1729-1734`）直接读取 `operation_result.accepted_proposal_manifest_ref` 传入 `build_context_compacted_payload()`，不像 proactive path 那样通过 `_required_compactor_manifest_ref()` 做 fail-closed 检查。当 prepared compactor path 记录了 manifest 时，`run_compaction_operation()` 会正确填充 `accepted_proposal_manifest_ref`；但若 reactive path 使用 generic non-prepared compactor（`FakeContextCompactor`），`accepted_proposal_manifest_ref` 为 `None`，`build_context_compacted_payload()` 会接受 `None` 值（因为 `accepted_proposal_manifest_ref` 参数默认值为 `None`）。这是设计允许的——generic compactor 不产生 manifest，reactive compact event 不强制要求 manifest ref。但如果 controller 要求 reactive path 同样 fail-closed，则需要在 `engine_ingest.py` 中添加等价 guard。当前 proactive path 的 fail-closed 已有 focused test 覆盖。
2. **Deferred findings**：trigger reason enum precision、outcome-dependent identity refs、artifact transaction boundary、Tool Trace analyzer consumption 均为已知 residual，不阻塞 Slice 3 核心 contract。

## Tests / pyright 证据

- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py tests/host/test_public_compact_smoke.py tests/host/test_llm_compaction.py`
  - 结果：114 passed, 1 skipped
- `source .venv/bin/activate && pyright`
  - 结果：0 errors, 0 warnings
- `git diff --check`
  - 结果：通过

## Ready for Controller Adjudication

yes。4 个 accepted findings 全部 fixed，无新 findings，deferred findings 无回归。
