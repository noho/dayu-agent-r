# WU-DUR-P01 Slice 3 Implementation Retry Code Review (AgentDS)

## Verdict

**pass-with-findings**

核心不变量全部成立。proactive 路径完整闭环：manifest 在 runner call 前生成、message_count/role_sequence_digest/compaction_request_digest 与真实 AgentRunRequest 同源、accepted CONTEXT_COMPACTED 和 rejected CONTEXT_COMPACTION_ATTEMPT_REJECTED 正确引用 proposal manifest ref/digest、缺 manifest 时 dispatch 路径 fail closed。没有 fake manifest、side channel、preview-only artifact 或 compact output schema 变更。Compactor proposal 不是 Host admitted Run。类型边界使用 isinstance + @runtime_checkable Protocol，无 hasattr/getattr 弱设计。

唯一实质性 finding 是 reactive compaction 路径（engine_ingest.py）未接入 proposal manifest ref，导致 reactive CONTEXT_COMPACTED 事件不携带 manifest ref/digest。该缺口在 implementation report 中已透明标注，属可接受 residual，不造成回归。

## Findings

### F1: Reactive compaction 路径未接入 proposal manifest ref (MEDIUM)

**文件/位置**: `dayu/host/engine_ingest.py` — 未编辑

**直接证据**:

1. Plan Slice 3 "Exact changes" 要求 "accepted `CONTEXT_COMPACTED` 引用 accepted proposal manifest；rejected/failed attempt 通过 typed diagnostic/progress ref 引用相应 manifest。" 该要求未区分 proactive/reactive 路径。
2. Plan Slice 3 allowed files 明确包含 `dayu/host/engine_ingest.py`，controller adjudication 的 expanded file set 也未移除该文件。
3. Implementation 实现的 `_DurableCompactorProposalManifestRecorder` 只通过 dispatch.py 的 proactive compaction 路径接入（`_compactor_proposal_manifest_recorder()` → `run_compaction_operation()`）。reactive compaction 路径（engine_ingest.py 中的 `_execute_reactive_compaction()` 或等价入口）调用 `run_compaction_operation()` 时未传入 `proposal_manifest_recorder` 参数，导致 `CompactionOperationResult.accepted_proposal_manifest_ref` 为 `None`。
4. Reactive compact closeout 写入 `CONTEXT_COMPACTED` 时，`build_context_compacted_payload()` 的 `accepted_proposal_manifest_ref` 和 `accepted_proposal_manifest_digest` 使用默认值 `None`，reactive compact event 不携带 proposal manifest ref。

**影响**: reactive compaction 产出的 `CONTEXT_COMPACTED` 事件缺少 proposal manifest 引用，analyzer 无法从 reactive compact event 反向定位 compactor runner-call input。proactive 路径完全覆盖，不造成现有行为回归。

**缓解**: implementation report 已透明标注此缺口为 remaining risk，并说明 engine_ingest.py 需在 follow-up allowed-files set 中显式加入。`_DurableCompactorProposalManifestRecorder` 基础设施已就位，reactive 接入是机械性 plumbing，不需要新 contract。

### F2: Compactor proposal 首次 attempt 的 trigger reason 命名偏差 (LOW)

**文件/位置**: `dayu/host/dispatch.py:1267` (`_compactor_trigger_reason()`)

**直接证据**:

```python
def _compactor_trigger_reason(compaction_attempt_number: int) -> str:
    if compaction_attempt_number <= 1:
        return _RUNNER_CALL_TRIGGER_COMPACTION_REPAIR  # "context_compaction_repair_attempt"
    return _RUNNER_CALL_TRIGGER_COMPACTION_RETRY       # "context_compaction_retry_attempt"
```

design.md `RunnerCallTriggerReason` 对 `context_compaction_repair_attempt` 的语义定义为 "compactor repair attempt after proposal rejection"，对 `context_compaction_retry_attempt` 定义为 "compactor retry attempt after proposal execution failure"。首次 proposal attempt 既不是"after proposal rejection"也不是"after proposal execution failure"，它是初始 attempt。

**根因**: design.md 的 `RunnerCallTriggerReason` 闭包枚举缺少 `context_compaction_initial_attempt` 或等价值。实现方在现有枚举约束下选择了最接近的值，这是 design contract 缺口导致的命名偏差，不是实现错误。

**影响**: 纯命名层面，不影响功能正确性、manifest 消费或 event 路由。trigger reason 仍是合法枚举值，analyzer 可正常消费。

### F3: CompactorRunnerCallIdentity 在 manifest 中缺少 outcome-dependent 字段 (INFO)

**文件/位置**: `dayu/host/dispatch.py:1040` (`_compactor_runner_call_manifest_body()`)

**直接证据**: design.md `CompactorRunnerCallIdentity` contract（design.md:3061-3071）包含 `accepted_context_compacted_event_ref`（"present only for accepted attempt"）和 `rejected_attempt_diagnostic_ref`（"present for rejected or failed attempts"）。实现侧的 `compactor_identity` 不包含这两个字段。

**分析**: manifest 在 proposal runner call **之前**写入，此时无法知道 acceptance/rejection 结果。这两个 outcome-dependent 字段在 manifest 中不可用是时序必然。实现通过 `CONTEXT_COMPACTED.accepted_proposal_manifest_ref` / `CONTEXT_COMPACTION_ATTEMPT_REJECTED.proposal_manifest_ref` 补偿，使得 compact event ↔ manifest 引用关系可双向解析。这是正确的工程选择，不是实现缺陷。design contract 应在 `CompactorRunnerCallIdentity` 中标注这两个字段的 "deferred to compact event payload" 约束。

### F4: Artifact 写入在 SQLite transaction 内但非事务性 (INFO)

**文件/位置**: `dayu/host/dispatch.py:404` (`_DurableCompactorProposalManifestRecorder.record_compactor_proposal_manifest()`)

**直接证据**: `_operation()` 闭包在 `transaction_runner.run_write()` 内执行，先调用 `self._artifact_store.write_artifact_bytes()` 写入文件系统，再调用 `self._payload_store.write_payload_descriptor_for_artifact()` 写入 SQLite payload descriptor。文件系统写入不参与 SQLite 事务回滚。

**分析**: 若 artifact 写入成功但后续 SQLite 操作失败导致事务回滚，会残留孤儿 artifact 文件。这是 pre-existing pattern（现有 compact artifact 写入使用相同模式），不是本 slice 引入的新问题。INFO 级别，不阻塞。

## Review Point 逐一判定

### 1. Manifest 在 runner call 前生成，message_count/role_sequence_digest/compaction_request_digest 与 AgentRunRequest 同源

**PASS**

`_prepare_compactor_proposal()` (compaction_operation.py:420-456) 的执行顺序为 prepare → record → run。`LLMContextCompactor.prepare_compactor_proposal_run_input()` (llm_compaction.py:209-315) 从同一个 `AgentRunRequest.messages` 计算 `message_count`、`role_sequence_digest`、`compaction_request_digest`、`system_prompt_asset_digest`、`user_prompt_template_digest`、`user_prompt_digest` 和 `compactor_input_projection_digest`，全部打包进 `CompactorProposalRunInput`。`_compactor_message_entries()` (dispatch.py:1100-1143) 从 `prepared_input.agent_request.messages` 逐条迭代构造 message entries，确保 manifest message entries 与真实 runner call input 完全同源。测试 `test_llm_context_compactor_prepares_same_source_runner_input` (test_llm_compaction.py:377-404) 验证了这个同源性。

### 2. accepted CONTEXT_COMPACTED / rejected CONTEXT_COMPACTION_ATTEMPT_REJECTED 引用正确 manifest ref/digest；缺 manifest fail closed

**PASS (proactive)，PARTIAL (reactive — see F1)**

Proactive 路径：`_execute_proactive_compaction()` (dispatch.py:1427-1440) 通过 `_required_compactor_manifest_ref(result)` 和 `_required_compactor_manifest_digest(result)` 提取 manifest ref/digest，值为 `None` 时抛出 `RuntimeError("accepted compaction is missing proposal manifest ref")` — fail closed。`_write_compaction_attempt_rejected()` (dispatch.py:2179-2184) 将 `rejected.proposal_manifest_ref` 和 `rejected.proposal_manifest_digest` 传入 `build_context_compaction_attempt_rejected_payload()`。`context_events.py` 中 `_validate_optional_ref_digest_pair()` (line 588-608) 确保 ref/digest 成对出现或均为 null，digest 为合法 SHA-256。Reactive 路径未覆盖 (F1)。

### 3. No fake manifest / no side channel / no preview-only artifact / no compact output schema change

**PASS**

`_DurableCompactorProposalManifestRecorder` (dispatch.py:408-874) 通过 `LocalArtifactStore.write_artifact_bytes()` 和 `PayloadStore.write_payload_descriptor_for_artifact()` 写入真实 durable artifact/descriptor，通过 `EventLogStore.append_event()` 写入 canonical `RUNNER_CALL_INPUT_ASSEMBLED` event。所有数据流经 typed protocols (`CompactorProposalPreparedCompactor`、`CompactorProposalManifestRecorder`)，无 side channel。`ConversationCompactOutputVNext` schema 未改变。

### 4. Compactor proposal 不是 Host admitted Run

**PASS**

`runner_call_kind` 固定为 `"compactor_proposal"`，`RUNNER_CALL_INPUT_ASSEMBLED` event 的 `actor` 为 `"host.context_governance"`。manifest 中的 `compactor_identity` 明确记录 `parent_host_run_id`（Host admitted user Run）和 `compactor_engine_run_id`（`context-compactor:*` 前缀的 Engine run id），区分 parent 和 self。没有创建 Host admitted Run、Attempt 或 Session 生命周期。proactive 路径的 `attempt_id` 和 `execution_id` 为 `None`，符合 pre-dispatch 语义。

### 5. Manifest/compactor_input_projection artifact/descriptor 是否 durable、bounded、不内联 full prompt/material/provider raw

**PASS**

Manifest body 写入 artifact store（`LocalArtifactStore`），通过 `payload_descriptor` + `kind=runner_call_input_manifest` 引用。Compactor input projection 写入 artifact store，通过 `payload_descriptor` + `kind=compactor_input_projection` 引用。Manifest message entries 只包含 `content_digest`、`content_size_bytes`、`source_refs`、`projection_artifact_ref`，不内联 message content。provider_tool_calls_digest / reasoning_content_digest 固定为 `None`（compactor 禁用工具且不涉及 reasoning），不出现 raw dict/Any bag。

Compactor input projection artifact 包含 `compact_input.to_json()` 全量 vNext input data block。该 artifact 是设计允许的 derived artifact（design.md:2582），不作为 EventLog hot payload。测试 `test_proactive_compact_duplicate_prompt_does_not_exceed_compactor_window` (test_public_compact_smoke.py:398-432) 验证 manifest 不内联重复长 prompt 正文。

### 6. generic fake compactor path 与 production LLMContextCompactor prepared path 的类型安全边界

**PASS**

`_prepare_compactor_proposal()` (compaction_operation.py:420-456) 使用 `isinstance(compactor, CompactorProposalPreparedCompactor)` 做分支判断。`CompactorProposalPreparedCompactor` 是 `@runtime_checkable` Protocol (compaction_operation.py:72-106)，不是 hasattr/getattr 弱设计。generic 路径（else 分支）保持旧 `compactor.compact()` 调用，proposal_manifest_reference 为 `None`，与新路径不交叉污染。`CompactorProposalManifestRecorder` 是 plain Protocol，通过显式参数注入，使用方只依赖协议方法签名。

### 7. Reactive compaction 未接线的 scope 判断

**结论：可接受 residual，不违反 Slice 3 scope contract 的核心交付**

证据：

- Plan Slice 3 的核心目标是 "覆盖 Host-owned compactor proposal call，使 analyzer 可轻量定位 compactor system/user messages 或报告 limited-signal。" Proactive 路径已完整交付该目标。
- Plan 的 "Exact changes" 没有显式区分 proactive/reactive 路径的 manifest ref plumbing；"Data flow" 描述只覆盖了通用链路。
- `engine_ingest.py` 在 plan allowed files 中但未被编辑，implementation report 明确将此标注为 remaining risk 并建议 follow-up。
- Controller adjudication 要求的 scope 是 "Add production manifest data flow from compactor proposal request construction through CompactionOperationResult / CompactionAttemptRejected to compact EventLog payloads" — proactive 路径完整满足该数据流。
- 不造成 regression：reactive compaction 的 CONTEXT_COMPACTED 此前也没有 manifest ref，实现未改变该行为。

**风险敞口**: 若 controller 期望同一 Slice 内 reactive CONTEXT_COMPACTED 也携带 proposal manifest ref，则本 Slice 对该子项 scope incomplete，需 follow-up 接入 engine_ingest.py。

### 8. Tests / pyright / README

**PASS**

- Tests: 65 passed, 1 skipped (codex report 确认)
  - `test_llm_context_compactor_prepares_same_source_runner_input` — 验证 prepare 与 AgentRunRequest 同源
  - `test_run_compaction_operation_records_prepared_proposal_manifest_before_call` — 验证 manifest 在 call 前记录，accepted result 传出 ref
  - `test_run_compaction_operation_rejected_attempt_keeps_proposal_manifest_ref` — 验证 rejected attempt 传出 proposal manifest ref
  - `test_proactive_compact_duplicate_prompt_does_not_exceed_compactor_window` — 扩展验证 manifest boundedness
- Pyright: 0 errors, 0 warnings (codex report 确认)
- README:
  - `dayu/host/README.md` — 更新 compactor proposal runner-call manifest 说明和 accepted/rejected compact payload 字段
  - `tests/README.md` — 更新 prepared proposal / manifest propagation 和 bounded public smoke 覆盖说明
- `git diff --check` — passed

## Scope Completeness Judgment

| Scope Item | Status |
|---|---|
| Compactor proposal manifest before runner call | Complete (proactive) |
| message_count / role_sequence_digest / compaction_request_digest 同源 | Complete |
| CONTEXT_COMPACTED 引用 accepted proposal manifest ref/digest | Complete (proactive), Partial (reactive — F1) |
| CONTEXT_COMPACTION_ATTEMPT_REJECTED 引用 proposal manifest ref/digest | Complete (proactive), Partial (reactive — F1) |
| 缺 manifest fail closed | Complete (proactive path) |
| No fake manifest / side channel / preview-only artifact | Complete |
| No compact output schema change | Complete |
| Compactor proposal 不是 Host admitted Run | Complete |
| compactor_input_projection descriptor kind in durable schema | Complete |
| Manifest/compactor_input_projection durable, bounded, no full inline | Complete |
| Type-safe generic vs prepared boundary | Complete |
| Tests | Complete |
| Pyright | Complete |
| README sync | Complete |

## Remaining Risks

1. **Reactive compaction manifest ref 未接入 (F1)**：reactive CONTEXT_COMPACTED 和 CONTEXT_COMPACTION_ATTEMPT_REJECTED 事件不携带 proposal manifest ref/digest。需 follow-up 在 engine_ingest.py 接入 proposal_manifest_recorder。
2. **RunnerCallTriggerReason 枚举 gap (F2)**：design.md 缺少 `context_compaction_initial_attempt`，首次 compactor proposal 的 trigger reason 语义不精确。建议在后续 design.md 维护中补充。
3. **Orphan artifact risk (F4)**：artifact 文件系统写入不在 SQLite transaction 范围内，事务回滚可能残留孤儿 artifact。这是 pre-existing pattern，非本 Slice 引入。
4. **Manifest compactor_identity 字段未完成 (F3)**：`accepted_context_compacted_event_ref` 和 `rejected_attempt_diagnostic_ref` 因 manifest 写入时序早于 outcome 而无法填充。需 design.md 在 CompactorRunnerCallIdentity contract 中标注 "deferred to compact event payload"。
5. **Tool Trace analyzer 未实现**：compactor manifest reconstruction 在 Tool Trace 中的消费超出 Slice 3 scope（属 Slice 4），当前无 regression。

## Ready for Controller Adjudication

**Yes.** 核心不变量成立，findings 均有明确定位和缓解路径。F1 是已知并透明标注的 scope boundary，不阻塞 slice acceptance。建议 controller 裁决是否将 reactive path plumbing 纳入本 slice 的 fix 轮次还是 defer 到 follow-up slice。
