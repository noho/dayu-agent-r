# WU-DUR-P01 Slice 3 Implementation Retry Code Review — AgentMiMo

## Verdict

pass-with-findings

## Reviewed Inputs

- `docs/reviews/wu-dur-obs-cm-closeout-slice3-implementation-retry-codex.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice3-blocker-controller-adjudication.md`
- `docs/host/wu-dur-obs-cm-closeout-plan.md` Slice 3
- `docs/host/design.md` 13.1、13.3、16、23.1、CompactorRunnerCallIdentity contract
- 当前 diff：`dayu/host/llm_compaction.py`、`compaction_operation.py`、`dispatch.py`、`context_events.py`、`durable/schema.py`、测试与 README

## Review Scope Verification

blocker controller adjudication 要求的 expanded allowed files 全部覆盖：

| 文件 | 变更内容 | 对齐判定 |
|------|----------|----------|
| `dayu/host/llm_compaction.py` | 拆分 `prepare_compactor_proposal_run_input` / `run_prepared_compactor_proposal`；同源 `agent_request`、`message_count`、`role_sequence_digest`、`compaction_request_digest`、`compactor_input_projection` | 对齐 |
| `dayu/host/compaction_operation.py` | `CompactorProposalRunInput`、`CompactorProposalManifestReference`、`CompactorProposalPreparedCompactor` Protocol、`CompactorProposalManifestRecorder` Protocol、`run_compaction_operation` 扩展 manifest 流、`CompactionAttemptRejected` / `CompactionOperationResult` 扩展 manifest ref/digest | 对齐 |
| `dayu/host/dispatch.py` | `_DurableCompactorProposalManifestRecorder` 实现、manifest body/hot payload 构造、`CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_ATTEMPT_REJECTED` payload builder 传入 manifest ref/digest、fail-closed `_required_compactor_manifest_ref` | 对齐 |
| `dayu/host/context_events.py` | `build_context_compacted_payload` / `build_context_compaction_attempt_rejected_payload` 扩展 proposal manifest ref/digest 字段、`_validate_optional_ref_digest_pair` 成对校验 | 对齐 |
| `dayu/host/durable/schema.py` | `COMPACTOR_INPUT_PROJECTION_DESCRIPTOR_KIND` 常量 | 对齐 |
| `tests/host/test_llm_compaction.py` | prepared input 同源 message/role/digest 断言 | 对齐 |
| `tests/host/test_compaction_operation.py` | accepted/rejected manifest ref 传递、`_PreparedManifestCompactor`、`_RecordingProposalManifestRecorder`、prepare→record→run 顺序断言 | 对齐 |
| `tests/host/test_public_compact_smoke.py` | manifest bounded、不内联重复长正文、`runner_call_kind=compactor_proposal`、`message_count=2` | 对齐 |
| `dayu/host/README.md` | manifest 说明、accepted/rejected payload 扩展说明 | 对齐 |
| `tests/README.md` | prepared proposal / manifest propagation 覆盖说明 | 对齐 |

## Findings

### F1. 初始 proposal 的 trigger reason 语义错误（severity: medium）

**文件/行号**：`dayu/host/dispatch.py:4096-4105`

**直接证据**：

```python
def _compactor_trigger_reason(compaction_attempt_number: int) -> str:
    if compaction_attempt_number <= 1:
        return _RUNNER_CALL_TRIGGER_COMPACTION_REPAIR  # "context_compaction_repair_attempt"
    return _RUNNER_CALL_TRIGGER_COMPACTION_RETRY        # "context_compaction_retry_attempt"
```

design.md 23.1 定义：

| trigger reason | 含义 |
|---|---|
| `context_compaction_repair_attempt` | compactor repair attempt **after proposal rejection** |
| `context_compaction_retry_attempt` | compactor retry attempt **after proposal execution failure** |

attempt_number == 1 是 operation 内第一次 proposal，此时不存在 prior rejection 或 prior execution failure。将第一次 proposal 标记为 `repair_attempt` 语义不正确。

**根因**：design.md 的 `RunnerCallTriggerReason` closed enum 没有定义 "initial proposal" 触发原因。实现被迫在两个都不语义正确的选项中选择。

**建议**：在 design.md 的 `RunnerCallTriggerReason` enum 中新增 `context_compaction_initial_proposal`（或等价语义），并在 `_compactor_trigger_reason` 中对 attempt_number == 1 返回该值。或者在当前 design 不变的约束下，用 `context_compaction_retry_attempt` 作为第一次 attempt 的 trigger reason（因为 design 定义它为 "after proposal execution failure"，第一次可以解释为"没有 prior failure 的 baseline attempt"），但需要在 manifest contract 中明确说明。当前 `repair_attempt` 语义确实错误。

### F2. accepted proposal 缺少 manifest ref 时 fail-closed 无直接测试覆盖（severity: low）

**文件/行号**：`dayu/host/dispatch.py:1431`、`dayu/host/dispatch.py:4282-4293`

**直接证据**：

```python
def _required_compactor_manifest_ref(result: CompactionOperationResult) -> str:
    value = result.accepted_proposal_manifest_ref
    if value is None or value.strip() == "":
        raise RuntimeError("accepted compaction is missing proposal manifest ref")
    return value
```

该 fail-closed 逻辑在 proactive compaction accepted path 中被调用（dispatch.py:1431），但 `test_compaction_operation.py` 和 `test_public_compact_smoke.py` 中没有直接测试该 `RuntimeError` 路径。

**建议**：补充一个 focused test，断言当 `CompactionOperationResult.accepted_proposal_manifest_ref=None` 但 `accepted_candidate is not None` 时，`_required_compactor_manifest_ref` raises `RuntimeError`。

### F3. `CompactorRunnerCallIdentity` 后置 cross-reference 更新缺失（severity: low）

**文件/行号**：`dayu/host/dispatch.py:3870-3877`

**直接证据**：

manifest body 中 `compactor_identity` 在 proposal 前写入：

```python
"compactor_identity": {
    "parent_host_run_id": request.run_id,
    "parent_session_id": request.session_id,
    "compaction_operation_id": compaction_operation_id,
    "compactor_engine_run_id": prepared_input.compactor_engine_run_id,
    "compaction_attempt_number": compaction_attempt_number,
    "compaction_request_digest": prepared_input.compaction_request_digest,
    "compactor_input_projection_ref": compactor_input_projection_ref,
    # accepted_context_compacted_event_ref: missing
    # rejected_attempt_diagnostic_ref: missing
},
```

design.md CompactorRunnerCallIdentity contract 定义了 `accepted_context_compacted_event_ref`（accepted attempt 时 present）和 `rejected_attempt_diagnostic_ref`（rejected/failed attempt 时 present）。当前 manifest 写入发生在 proposal call 前，此时 accepted/rejected event 尚不存在，因此这两个字段自然为 null。但 code 中也没有后续更新路径将这些 cross-reference 补回 manifest。

**影响**：manifest 作为 proposal-time snapshot 可以不含后置引用；`CONTEXT_COMPACTED` payload 已通过 `accepted_proposal_manifest_ref` / `accepted_proposal_manifest_digest` 建立了反向引用。但如果 analyzer 需要从 manifest identity 侧查到对应的 accepted/rejected event，当前无法完成。

**建议**：可作为 Slice 4 Tool Trace 或后续 WU-OBS-00 的 follow-up，不需要在 Slice 3 阻塞。

### F4. `_CompactorProposalExecutionError` 使用 dataclass 继承 Exception（severity: nit）

**文件/行号**：`dayu/host/compaction_operation.py:185-194`

**直接证据**：

```python
@dataclass(frozen=True, slots=True)
class _CompactorProposalExecutionError(Exception):
    original_exception: Exception
    proposal_manifest_reference: CompactorProposalManifestReference | None
```

dataclass + Exception 组合在 Python 中可以工作，但 `frozen=True` + Exception 的 `__init__` 签名与标准 Exception 签名不同，且 `__str__` / `__repr__` 输出为 dataclass 格式而非标准异常格式。由于这是模块私有异常且仅在 `_prepare_compactor_proposal` 中使用，实际风险极低。

## Review Point 逐项裁决

### 1. Compactor proposal manifest 是否在真实 proposal runner call 前生成

**PASS**。`test_compaction_operation.py:test_run_compaction_operation_records_prepared_proposal_manifest_before_call` 断言 `events == ["prepare", "record", "run"]`，manifest recorder 在 `run_prepared_compactor_proposal` 之前被调用。`_prepare_compactor_proposal` 的代码路径确认先 `_record_compactor_proposal_manifest` 再 `compactor.run_prepared_compactor_proposal`。

### 2. message_count / role_digest / compaction_request_digest 是否与真实 AgentRunRequest 同源

**PASS**。`prepare_compactor_proposal_run_input` 中：
- `message_count=len(agent_request.messages)` — 从同一个 `agent_request` 取
- `role_sequence_digest=runner_role_sequence_digest(roles)` — roles 从同一个 `agent_request.messages` 取
- `compaction_request_digest=request.digest()` — 从 immutable `CompactionRequest` 取

`test_llm_compaction.py:test_llm_context_compactor_prepares_same_source_runner_input` 断言 `prepared.compactor_engine_run_id == request.run_id`、`prepared.message_count == len(request.messages) == 2`、`prepared.role_sequence_digest == runner_role_sequence_digest(roles)`。

### 3. accepted CONTEXT_COMPACTED 和 rejected CONTEXT_COMPACTION_ATTEMPT_REJECTED 是否引用正确 proposal manifest ref/digest

**PASS**。`dispatch.py` 中：
- accepted path 通过 `_required_compactor_manifest_ref(result)` / `_required_compactor_manifest_digest(result)` 传入 `build_context_compacted_payload`
- rejected path 通过 `CompactionAttemptRejected.proposal_manifest_ref` / `.proposal_manifest_digest` 传入 `build_context_compaction_attempt_rejected_payload`

`test_compaction_operation.py` 两个 focused test 分别验证 accepted 和 rejected 的 manifest ref/digest 正确传递。

### 4. 缺 manifest 是否 fail closed

**PASS**（逻辑正确，测试覆盖有 gap）。`_required_compactor_manifest_ref` 在 accepted result 缺少 ref 时 `raise RuntimeError`，阻止 `CONTEXT_COMPACTED` 写入。F2 记录了测试覆盖 gap。

### 5. No fake manifest / no side channel / no preview-only artifact / no compact output schema change

**PASS**。
- manifest 由 `_DurableCompactorProposalManifestRecorder` 写入真实 EventLog + artifact store
- `compactor_input_projection` 写入 artifact root 作为 `compactor_input_projection` descriptor kind
- compact output schema 未改变（`ConversationCompactOutputVNext` 不变）
- 无 side channel：所有 manifest ref/digest 通过 typed dataclass 传递

### 6. Compactor proposal 是否仍不是 Host admitted Run

**PASS**。manifest body 中 `runner_call_kind="compactor_proposal"`，`attempt_id` 来自 `CompactionRequest`（proactive compaction 为 None），不创建 Host Run/Attempt 状态转换。`compactor_identity.compactor_engine_run_id` 使用 `_compactor_engine_run_id` 派生的 deterministic id，格式为 `context-compactor-vnext-{digest}`，不进入 Host admitted Run namespace。

### 7. Manifest / compactor_input_projection artifact / descriptor 是否 durable、bounded、不内联 full prompt/material/provider raw

**PASS**。
- manifest body 只包含 message summaries（index、role、content_digest、content_size_bytes、source_refs、projector_metadata_id），不内联 message content
- `compactor_input_projection` 写入 artifact store（`LocalArtifactStore.write_artifact_bytes`），通过 payload descriptor 引用
- `test_public_compact_smoke.py:test_proactive_compact_duplicate_prompt_does_not_exceed_compactor_window` 断言 manifest 不内联重复长正文（`_DUPLICATE_PROMPT_SENTENCE * 20 not in manifest_text`）
- `test_llm_compaction.py` 断言 `_TEST_SYSTEM_PROMPT not in projection_text` 和 `_TEST_USER_PROMPT_TEMPLATE not in projection_text`

### 8. generic fake compactor path 与 production LLMContextCompactor prepared path 的边界是否类型安全

**PASS**。`_prepare_compactor_proposal` 中通过 `isinstance(compactor, CompactorProposalPreparedCompactor)` 分支：
- production path：`isinstance` 为 True 时走 `prepare_compactor_proposal_run_input` → manifest record → `run_prepared_compactor_proposal`
- generic path：`isinstance` 为 False 时走 `compactor.compact(request, cancellation_token)`，`proposal_manifest_reference=None`

`CompactorProposalPreparedCompactor` 是 `@runtime_checkable Protocol`，`isinstance` 检查基于结构化 duck typing，不使用 `hasattr`/`getattr`。

### 9. Reactive compaction 未接线是否违反 Slice 3 scope

**RESIDUAL，可接受**。implementation retry codex review 明确指出：`engine_ingest.py` 不在 expanded allowed files 中，reactive compaction path 不扩展 proposal manifest wiring。当前实现覆盖 proactive path，由 `dispatch.py` 的 `_DurableCompactorProposalManifestRecorder` 连接。如果 controller 期望 reactive `CONTEXT_COMPACTED` payload 同样携带 proposal manifest ref，需要将 `engine_ingest.py` 加入 follow-up allowed files。

### 10. Tests / pyright / README

**PASS**。
- tests：65 passed, 1 skipped（implementation retry codex 报告）
- pyright：0 errors, 0 warnings
- README：`dayu/host/README.md` 和 `tests/README.md` 已同步更新

## Scope Completeness Judgment

Slice 3 的核心 contract——durable compactor proposal manifest、同源 message_count/role_digest、accepted/rejected compact event 引用 manifest ref/digest、fail-closed、compactor input projection artifact——全部实现且对齐 design.md 23.1 与 CompactorRunnerCallIdentity contract。

trigger reason 语义错误（F1）和 CompactorRunnerCallIdentity 后置 cross-reference（F3）属于 contract 精度问题，不阻塞 Slice 3 核心数据流正确性。F2 的测试 gap 需要补充。

## Tests / pyright

- pytest：65 passed, 1 skipped
- pyright：0 errors, 0 warnings
- `git diff --check`：passed

## Remaining Risks

1. **F1 trigger reason 语义**：初始 proposal 的 `runner_call_trigger_reason` 被标记为 `context_compaction_repair_attempt`，语义不正确。需 controller 决定是否在 Slice 3 fix 中修正，或作为 design.md enum 扩展的 follow-up。
2. **F2 fail-closed 测试 gap**：需补充 accepted result 缺少 manifest ref 时的 focused test。
3. **reactive compaction wiring**：`engine_ingest.py` 不在本次 allowed files 中，reactive path 的 proposal manifest 跨文件接线待 follow-up。
4. **CompactorRunnerCallIdentity cross-reference**：`accepted_context_compacted_event_ref` / `rejected_attempt_diagnostic_ref` 后置更新路径待 Slice 4 或 WU-OBS-00 覆盖。

## Ready for Controller Adjudication

yes，附带 F1（medium）和 F2（low）供 controller 裁决是否需要在 Slice 3 fix 中处理或标记为 follow-up。
