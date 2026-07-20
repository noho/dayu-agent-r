# WU-SEMANTIC-OWNERSHIP-01 / R03-S1 Code Review — AgentMiMo

## 1. Scope

- Mode: current changes（`6e11d916..working tree`，含 untracked production file 与 Controller/implementation artifacts）
- Branch: `phaseflow/host-issues-control`
- Base: `6e11d916`（`docs: resume R03 S1 implementation`）
- Output file: `docs/reviews/wu-semantic-ownership-01-r03-s1-code-review-mimo.md`
- Included scope: 8 production files（含 1 新增）、9 test files、2 README files、`docs/host/issues-implementation-control.md`（control 追踪）、3 untracked review artifacts
- Excluded scope: 无
- Parallel review coverage: 无

## 2. Review 方法与输入

本次 review 按以下顺序完整读取：

1. `AGENTS.md`（项目约束）
2. `docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md` §0-6/13-16（accepted plan）
3. `docs/reviews/wu-semantic-ownership-01-r03-s1-plan-correction-review-controller-adjudication.md`（plan correction adjudication）
4. `docs/reviews/wu-semantic-ownership-01-r03-s1-implementation-codex.md`（implementation artifact）
5. `docs/reviews/wu-semantic-ownership-01-r03-s1-controller-validation.md`（Controller validation，含 `R03-S1-CV-F01`）
6. `docs/reviews/wu-semantic-ownership-01-r03-s1-controller-revalidation.md`（Controller re-validation）
7. 完整 production diff（`git diff -- dayu/host/`）
8. 完整 test diff（`git diff -- tests/`）
9. 完整 README diff
10. 新增 `dayu/host/tool_call_request.py` 全文
11. `docs/host/issues-implementation-control.md` diff

独立验证执行：

- S1 9-file test matrix: `389 passed in 2.61s` ✓
- full Host: `1951 passed, 2 skipped, 5 deselected in 61.69s`（1 个无关 flaky test 重跑通过）✓
- pyright: `0 errors, 0 warnings, 0 informations` ✓
- ruff: `All checks passed!` ✓
- 8-file coverage: 全部达标（`86%`–`98%`）✓
- CV-F01 owner tests: `4 passed` ✓
- awaiting request link corruption tests: `5 passed` ✓
- old helper deletion scan: 零命中 ✓

## 3. Findings

未发现实质性问题。

### 3.1 详细 adversarial 检查结果

以下按 accepted plan §6 的关键 contract 逐项审查：

#### 3.1.1 ordinary/awaiting canonical request 单 owner

- `dayu/host/tool_call_request.py` 定义 `AcceptedToolCallRequestAtomInput` 与 `build_tool_call_requested_event_request`。
- `tool_runtime.py::_tool_call_request_atom(candidate)` 将 `ToolFactAcceptCandidate` 显式映射为 atom，`tool_identity_digest` 原样传入 `candidate.call.tool_identity_digest`。
- `waiting.py::_tool_call_request_atom(candidate)` 将 `ToolAwaitingAcceptCandidate` 显式映射为 atom，`tool_identity_digest` 原样传入 `candidate.tool_identity_digest`，`semantic_query_text=None`。
- 两个 caller 都调用 `build_tool_call_requested_event_request`，writer 不 append、不预测 sequence。
- **结论**：单 owner contract 已落实。✓

#### 3.1.2 transaction sequencing/rollback/idempotency

- `waiting.py::DefaultHostToolAwaitingAcceptPort._accept_in_transaction` 严格按 §4.4 顺序：shared writer → append request → `append_event(...).row` 取真实 row → 构造 `tool_call_requested_event_ref` → append `TOOL_AWAITING` → 后续 facts。
- 全部步骤在同一 `run_write` transaction 内，任一异常整体 rollback。
- **结论**：sequencing 正确。✓

#### 3.1.3 TOOL_AWAITING governance-only exact link

- `_event_payload.py::tool_awaiting_payload` 参数已改为 `tool_call_requested_event_ref`，删除 `normalized_arguments_digest`、`accepted_arguments`、`accepted_arguments_source_digest`。
- payload 只包含治理字段与 `{event_id, event_sequence}` ref。
- 测试 `test_wait_awaiting_accept.py` 断言 exact key-set 与 absence assertions。
- **结论**：governance-only contract 已落实。✓

#### 3.1.4 inline/descriptor/query mutual exclusion

- `payload_resolution.py::_read_arguments_json` 在 descriptor 分支新增 `arguments_inline_json is not None` guard。
- `payload_resolution.py::_read_semantic_query` 在 descriptor 分支新增 `semantic_query_text is not None` guard。
- 测试覆盖两种 rejection。
- **结论**：冷热互斥 guard 已落实。✓

#### 3.1.5 strict digest/shape/identity

- `payload_resolution.py::tool_call_request_atoms` 新增 `arguments_payload_digest != normalized_digest` guard。
- `_required_text` 替代 `_optional_text` 用于 `semantic_input_digest`（现为必填）。
- `_read_arguments_json` 的 inner `arguments` object 校验从 `_FIELD_ARGUMENTS not in` 改为 `isinstance(accepted_arguments, Mapping)`。
- **结论**：strict digest/shape 校验已落实。✓

#### 3.1.6 accepted-result/RunInput/Memory/Compact/Trace no fallback/no partial publication

- `accepted_result_projection.py::_request_atoms_projection` 现在对所有 failure path 抛 `HostDurableError`，不再返回 `None`。
- `_request_row_matches_result` 删除 `result.execution_id is None` 兼容分支。
- `_request_atoms_match_envelope` 新增 `semantic_input_digest` equality check。
- `_request_unavailable_query` 已删除。
- `run_input.py::_resume_wait_accepted_arguments` 现在要求 `request_arguments_json` 非空，否则抛 `HostDurableError`。
- `_resume_wait_fallback_message` 已删除。
- 四个 consumer test files 均覆盖 corruption → `HostDurableError` → no-publication 路径。
- **结论**：no-fallback/no-partial-publication 已落实。✓

#### 3.1.7 wait-resolution source Attempt execution owner 与 precondition

- `_waiting_tool_result_event_request` 新增 `source_attempt: AttemptRow` 参数，写入 `attempt_id=source_attempt.attempt_id`、`execution_id=source_attempt.execution_id`。
- `resume_run_from_waiting_in_transaction` 与 `_terminal_run_from_waiting_in_transaction` 共用该 writer。
- `_invalid_waiting_resolution_precondition` 新增 `wait_record.execution_id != source_attempt.execution_id` guard。
- 公开测试 `test_resolve_wait_completed_resumes_run_and_wakes_dispatch` 断言 `TOOL_RESULT_ACCEPTED.attempt_id == seeded.attempt_id` 且 `execution_id == seeded.execution_id`。
- 公开测试 `test_resolve_wait_failed_and_lost_close_run_without_resume_attempt` 断言 failed/lost 的 result 使用各自 suspended source Attempt identity。
- direct transition 测试 `test_waiting_resolution_transition_rejects_execution_identity_mismatch` 参数化 completed/failed 两分支，断言 `INVALID_STATE` + 五表 no-mutation。
- **结论**：source Attempt execution owner 与 precondition 已落实。✓

#### 3.1.8 CV-F01 NOT_FOUND tests 是否真实且非 coverage shim

- `test_waiting_resolution_transition_returns_not_found_without_mutation` 参数化 `missing_run` / `missing_wait` 两 case。
- `missing_run`: 使用 `replace(request, run_id="run-resolve-missing")` 使目标 Run 不存在，断言 `NOT_FOUND` + 五表 snapshot 完全相等。
- `missing_wait`: 使用 `replace(request, wait_id="wait-resolve-missing")` 使 WaitRecord 不存在，断言 `NOT_FOUND` + 五表 snapshot 完全相等。
- 使用真实 SQLite store、production `EventLogStore`、完整 typed transition input。
- **结论**：真实 durable precondition tests，非 coverage shim。✓

#### 3.1.9 docstring/typing/README

- `tool_call_request.py` 所有函数和类均有完整中文 docstring（参数、返回、异常）。
- 签名无 `Any`/`object`。
- `README.md` 更新反映 shared writer、governance-only awaiting、strict consumer 与 exact resume。
- `tests/README.md` 更新反映 wait resolution identity、canonical fixture 与 strict corruption matrix。
- **结论**：docstring/typing/README 合规。✓

#### 3.1.10 旧 helper 删除闭包

- `rg -n 'llm_safe_replay_arguments|_tool_call_requested_event_id_from_wait_id|_validate_wait_request_arguments_digest|_awaiting_semantic_query_text|_resume_wait_fallback_message|_request_unavailable_query|_optional_event_id_from_payload_ref' dayu/host/` — 零命中。
- `rg -n 'accepted_arguments_source_digest|_PAYLOAD_FIELD_ACCEPTED_ARGUMENTS' dayu/host/` — 零命中。
- **结论**：旧 helper 已完整删除，无 compatibility alias。✓

#### 3.1.11 是否越界到 S2/S3

- S2 scope（blacklist repair、`_contains_unsafe_argument_key`、`arguments_summary_unsafe`、`redact_sensitive_json_fields`、`json_redaction.py`）：diff 中无相关修改。
- S3 scope（`OpaqueEvidenceRef`、`source_locator_refs`、`ACCEPTED_EVIDENCE_MATERIAL_UNAVAILABLE_TEXT`）：diff 中无相关修改。
- `git diff -U0 -- dayu/host/accepted_result_projection.py dayu/host/run_input.py dayu/host/memory.py dayu/host/compact_material.py dayu/host/tool_trace.py | rg -n 'OpaqueEvidenceRef|source_refs|locator_refs|ref_kind|ref_id|unsafe|blacklist|citation'` — 零命中。
- **结论**：未越界到 S2/S3。✓

#### 3.1.12 Issue 177/178 或统一 authorization

- diff 中无 Issue 177/178 相关修改。
- 无统一 authorization framework 引入。
- **结论**：未触及。✓

## 4. Open Questions

无。

## 5. Residual Risk

| 风险/残留 | 分类 / owner |
|---|---|
| S2 source blacklist / LLM source owner audit 尚未实施 | covered by `R03-S2` |
| S3 opaque ref internal-only propagation 与 legacy fallback material 删除尚未实施 | covered by `R03-S3` |
| `docs/host/issues-implementation-control.md` 的 control 追踪更新不在 S1 allowlist 中 | 属于 gate 状态追踪，非 production 语义变更；Controller 可裁决是否接受 |
| `run_input.py` 中 `build_memory_budget_diagnostic` 与 `estimate_memory_size_units` import 被移除 | 若该 import 在当前代码中仍被使用则为 breakage；但 pyright 零错误证明它们确实未被使用 |
| macOS multiprocessing spawn 与 coverage 插桩不兼容 | validation tooling limitation；无插桩 full Host 已覆盖 |

## 6. Conclusion

**PASS**。

R03-S1 实现完整落实了 accepted plan §6 的所有 contract：

- ordinary/awaiting 共用 `tool_call_request.py` 单一 writer，payload key set 完全一致。
- `TOOL_AWAITING` 只保存治理字段与显式 `{event_id, event_sequence}` request link，无 arguments/digest 副本。
- request atom reader 严格校验 normalized/payload digest equality、inline/descriptor 互斥、inner arguments object shape。
- accepted-result projection 对所有 request link 缺失/损坏/identity mismatch 抛 `HostDurableError`，四 consumer 无 fallback/limited signal。
- wait-resolution `TOOL_RESULT_ACCEPTED` 始终归属 suspended source Attempt 的 attempt/execution identity。
- `_invalid_waiting_resolution_precondition` 校验 `WaitRecord.execution_id == source_attempt.execution_id`，mismatch 返回 `INVALID_STATE` 且五表无 mutation。
- 旧 `llm_safe_replay_arguments`、`_tool_call_requested_event_id_from_wait_id`、`_validate_wait_request_arguments_digest`、`_awaiting_semantic_query_text`、`_resume_wait_fallback_message`、`_request_unavailable_query` 已完整删除。
- 未越界到 S2/S3、Issue 177/178 或统一 authorization。
- 全部验证通过：389 passed（S1 matrix）、1951 passed（full Host）、pyright 零错误、ruff pass、8-file coverage 全部达标。

Stable finding IDs: 无。
Accepted-plan closure: 完整。
Residual owners: S2（source blacklist audit）、S3（opaque ref propagation closure）。
