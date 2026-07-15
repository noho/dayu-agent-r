# R03-S1 Final Code Re-Review — AgentMiMo

## Scope

- Mode: current changes (final re-review of existing R03-S1 implementation)
- Branch: `phaseflow/host-issues-control`
- Base: `6e11d916` (accepted plan commit)
- Review date: 2026-07-15
- Output file: `docs/reviews/wu-semantic-ownership-01-r03-s1-code-rereview-mimo.md`
- Included scope: 全部 R03-S1 production / test / README diff（含 untracked `tool_call_request.py`）+ 全部 R03-S1 gate artifacts
- Excluded scope: S2/S3 production files、Engine/Fins/Config/Doc/Web tool producers、prompt assets、Issue #177/#178
- Parallel review coverage: 无（单 reviewer 直接走读全部 production/test/README diff）

## 复核输入

本 re-review 完整读取了以下权威输入：

1. `AGENTS.md` — 全部编码/架构/语义所有权约束
2. `docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md` — accepted R03 plan §0-6/13-16
3. `docs/reviews/wu-semantic-ownership-01-r03-s1-code-review-mimo.md` — initial MiMo code review（PASS，0 findings）
4. `docs/reviews/wu-semantic-ownership-01-r03-s1-code-review-ds.md` — initial DS code review（PASS，0 findings）
5. `docs/reviews/wu-semantic-ownership-01-r03-s1-code-review-controller-adjudication.md` — Controller adjudication（ACCEPTED_FINDINGS_ZERO）
6. `docs/reviews/wu-semantic-ownership-01-r03-s1-code-review-fix-codex.md` — zero-change fix record
7. `docs/reviews/wu-semantic-ownership-01-r03-s1-code-review-fix-controller-validation.md` — Controller validation（PASS）
8. `docs/reviews/wu-semantic-ownership-01-r03-s1-implementation-codex.md` — full implementation artifact
9. `docs/reviews/wu-semantic-ownership-01-r03-s1-controller-validation.md` — initial Controller validation（CV-F01）
10. `docs/reviews/wu-semantic-ownership-01-r03-s1-controller-revalidation.md` — Controller revalidation（PASS，CV-F01 closed）
11. `docs/reviews/wu-semantic-ownership-01-r03-s1-plan-correction-controller-adjudication.md` — plan correction adjudication
12. `docs/reviews/wu-semantic-ownership-01-r03-s1-plan-correction-codex.md` — plan correction artifact
13. `docs/reviews/wu-semantic-ownership-01-r03-s1-plan-correction-review-mimo.md` — plan correction MiMo review（PASS）
14. `docs/reviews/wu-semantic-ownership-01-r03-s1-plan-correction-review-ds.md` — plan correction DS review（PASS）
15. `docs/reviews/wu-semantic-ownership-01-r03-s1-plan-correction-review-controller-adjudication.md` — plan correction Controller adjudication（ACCEPTED）
16. `docs/reviews/wu-semantic-ownership-01-r03-s1-allowlist-controller-adjudication.md` — test-only allowlist expansion
17. `dayu/host/README.md` — updated Host development manual
18. `tests/README.md` — updated test ownership documentation
19. 全部 8 个 production diff files + 1 个 new production file
20. 全部 9 个 test diff files

## 验证结果

### 测试与类型检查

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| S1 matrix（9 files） | **389 passed** | `pytest tests/host/test_toolruntime_accept_barrier.py ... -q` |
| Full Host suite | **1952 passed, 2 skipped, 5 deselected** | `pytest tests/host -q` |
| pyright | **0 errors, 0 warnings** | `python -m pyright dayu/ tests/ utils/` |
| `run_transition.py` coverage | **80%**（281/1375 missing） | `--cov=dayu.host.durable.run_transition --cov-report=term-missing` |

### Allowlist 完整性

`git diff 6e11d916 --name-only` 产出 19 个 modified files + 1 个 untracked new file：

- **Production（8 modified + 1 new）**: `tool_call_request.py`（new）、`tool_runtime.py`、`waiting.py`、`_event_payload.py`、`payload_resolution.py`、`accepted_result_projection.py`、`run_input.py`、`durable/run_transition.py`
- **Tests（9 modified）**: `test_toolruntime_accept_barrier.py`、`test_wait_awaiting_accept.py`、`test_resolve_wait_command.py`、`test_run_input_builder.py`、`test_accepted_result_projection.py`、`test_compact_material.py`、`test_memory_projection.py`、`test_tool_trace_projection.py`、`test_tool_trace_queries.py`
- **Docs（2 modified）**: `dayu/host/README.md`、`tests/README.md`

逐文件与 accepted plan §6.2 allowlist 做集合比较：**完全一致**。

唯一额外 diff 文件为 `docs/host/issues-implementation-control.md`，变更内容仅更新 gate 状态行。该文件不在 S1 production/test/doc allowlist 内，但其变更已被 initial MiMo code review 作为 observation 3.2 记录，并被 Controller adjudication 裁决为"authorized Controller state / no finding"。本 re-review 确认该裁决有效。

### 34-target zero-change integrity

zero-change fix artifact 声明 34 个 protected target 的 aggregate content digest 为 `5bed25157482aeda9a52e6eb2cf7e23f091867de4c66bc4c7738fd5df3089c7a`，protected status digest 为 `5f6e70d8...39d`。Controller validation 确认 digests 未变、gate delta 仅为 fix artifact 本身。本 re-review 独立验证：当前 working tree 的 19 个 modified files 均为 S1 implementation diff，不存在被 zero-change gate 误触的 protected target 回退。

## 逐项复核

### 1. Shared writer contract（plan §4.2）

**证据**：`dayu/host/tool_call_request.py` 完整实现 `AcceptedToolCallRequestAtomInput`（frozen dataclass, 15 fields, 无 `Any`/`object`）和 `build_tool_call_requested_event_request`。writer 只构造 `EventLogAppendRequest`，不 append、不预测 `event_sequence`。

**ordinary 映射**（`tool_runtime.py:4290-4317`）：`_tool_call_request_atom(candidate: ToolFactAcceptCandidate)` 从 `candidate.identity`、`candidate.call`、`candidate.idempotency`、`candidate.tool_fact_kind` 显式映射全部 15 个 atom fields。`tool_identity_digest` 原样取 `candidate.call.tool_identity_digest`，不重算。`semantic_query_text` 取 `candidate.call.semantic_query_text`。

**awaiting 映射**（`waiting.py:2310-2326`）：`_tool_call_request_atom(candidate: ToolAwaitingAcceptCandidate)` 从 candidate 同名字段映射。`tool_identity_digest` 原样取 `candidate.tool_identity_digest`。`semantic_query_text=None`（无 synthetic query）。`tool_fact_kind="awaiting"`。

**复核结论**：两个入口到 atom 的映射精确符合 plan §4.2 表格。✓

### 2. TOOL_AWAITING governance-only（plan §4.4）

**证据**：`_event_payload.py` diff 删除 `accepted_arguments`、`accepted_arguments_source_digest`、`normalized_arguments_digest` 三个参数和字段，新增 `tool_call_requested_event_ref: Mapping[str, JsonValue]`。`_tool_awaiting_event_request`（`waiting.py:2329`）接收同事务 append 返回的真实 `tool_call_requested: EventLogRow`，通过 `_event_ref_json(tool_call_requested)` 构造 `{event_id, event_sequence}` ref。

**sequencing**：`waiting.py` `_accept_in_transaction` 中 `build_tool_call_requested_event_request` → `append_event(...).row` → `_tool_awaiting_event_request(..., tool_call_requested)` → `append_event(...)` → 后续 facts。符合 plan §4.4 的 6 步 sequencing。

**复核结论**：TOOL_AWAITING payload 不再包含 arguments/digest 副本。✓

### 3. Wait-resolution execution identity（plan §4.5, §6.3.10-11）

**evidence**：

- `_waiting_tool_result_event_request`（`run_transition.py:3744`）新增 `source_attempt: AttemptRow` keyword 参数，写入 `attempt_id=source_attempt.attempt_id`、`execution_id=source_attempt.execution_id`。旧代码 `attempt_id=request.suspended_attempt_id, execution_id=None` 已删除。
- `resume_run_from_waiting_in_transaction` 和 `_terminal_run_from_waiting_in_transaction` 均传入 `source_attempt`。
- `_invalid_waiting_resolution_precondition`（`run_transition.py:5360`）新增 `wait_record.execution_id != source_attempt.execution_id` 检查。不一致时返回 `StateMutationStatus.INVALID_STATE`，发生在所有 fact/state mutation 之前。

**复核结论**：execution identity 从 suspended source Attempt 直接取得，不留 `None`、不用 resume Attempt identity。precondition 在写入前 fail closed。✓

### 4. Normalized digest equality guard（plan §4.3）

**证据**：`payload_resolution.py` diff 在 `tool_call_request_atoms` 中新增：

```python
if arguments_payload_digest != normalized_digest:
    raise HostDurableError("tool call arguments payload digest must match normalized digest")
```

同时新增 descriptor 互斥 guards：descriptor arguments 不得携带 `arguments_inline_json`，descriptor query 不得携带 `semantic_query_text`。`semantic_input_digest` 从 `_optional_text` 改为 `_required_text`。

**复核结论**：reader 严格验证 digest equality 和 storage shape。✓

### 5. Strict projection / no-fallback（plan §4.5-4.6）

**证据**：

- `accepted_result_projection.py::_request_atoms_projection` 返回类型从 `ToolCallRequestAtoms | None` 改为 `ToolCallRequestAtoms`。所有 `diagnostics.append(...); return None` 分支替换为 `raise HostDurableError(...)`。
- `_request_unavailable_query` 函数已删除。
- `_request_row_matches_result` 删除 `or result_row.execution_id is None` 兼容分支。
- `_request_atoms_match_envelope` 新增 `semantic_input_digest` equality 检查。
- `run_input.py::_resume_wait_request_arguments` 在 `request_arguments_json is None` 时 `raise HostDurableError`，不再返回 `None`。
- `_resume_wait_fallback_message` 已删除。

**复核结论**：四个 LLM-facing consumer 对 canonical request material 缺失/损坏统一 fail closed。✓

### 6. llm_safe_replay_arguments 删除（plan §4.4.4）

**证据**：`_event_payload.py` diff 删除 `llm_safe_replay_arguments` 函数、`_PAYLOAD_FIELD_ACCEPTED_ARGUMENTS`、`_PAYLOAD_FIELD_ACCEPTED_ARGUMENTS_SOURCE_DIGEST` 常量、`redact_sensitive_json_fields` import。

**复核结论**：S1 scope 内的 LLM-safe normalization 已删除。✓

### 7. Old test deletion / replacement（plan §6.4）

**证据**：

- `test_awaiting_accept_persists_only_llm_safe_replay_arguments` → renamed to `test_awaiting_accept_persists_exact_shared_request_atom_and_governance_link`，断言从 redaction check 改为 exact shared request atom + governance link check。
- `test_resume_wait_replays_only_llm_safe_arguments` → renamed to `test_resume_wait_replays_exact_canonical_arguments`，参数从 `<redacted>` sentinel 改为 exact canonical arguments。

**复核结论**：旧 LLM-safe 断言已替换为 owner-contract 断言。✓

### 8. Direct transition owner tests（plan §6.4）

**证据**：`test_resolve_wait_command.py` 新增两个参数化 test：

- `test_waiting_resolution_transition_rejects_execution_identity_mismatch`（`completed`/`failed`）：用辅助 Attempt 的 execution id 改写 WaitRecord，断言 `StateMutationStatus.INVALID_STATE`，全表 rows 不变。
- `test_waiting_resolution_transition_returns_not_found_without_mutation`（`missing_run`/`missing_wait`）：断言 NOT_FOUND，全表 rows 不变。

**复核结论**：WaitRecord/source Attempt execution mismatch 和 missing durable 主体均被直接 transition 测试覆盖。✓

### 9. CV-F01 closure

**证据**：Controller validation 发现 `run_transition.py` 覆盖率 79%（低于 ≥80% 目标）。Controller revalidation 确认两个新 NOT_FOUND owner cases 将覆盖率提升至 80%（281/1375 missing）。本 re-review 独立复现：`77 passed, run_transition.py 80%`。

**复核结论**：CV-F01 已关闭。✓

### 10. 四项 Controller no-fix disposition

| # | Observation | Disposition | 复核 |
| --- | --- | --- | --- |
| 3.1 | MiMo timing observation | no finding（full suite green） | ✓ |
| 3.2 | control doc 不在 S1 allowlist | authorized Controller state | ✓ |
| 3.3 | DS duplicate-preimage observation | rejected as finding（independent producer/validator + fail-closed equality） | ✓ |
| 3.4 | unused import deletion | no finding | ✓ |

### 11. S2/S3/deferred 边界

S1 闭合 durable writer/reader/link/resume corruption。S2（blacklist repair + producer schema + LLM source audit）和 S3（opaque refs internal-only + four-consumer propagation closure）均未被侵入。`docs/host/design.md`、Engine files、Fins files、prompt assets 均无 diff。

`dayu/runtime/json_redaction.py`（S2 删除目标）在 S1 diff 中无变更，仅其 import 被 `_event_payload.py` 删除（因为 `llm_safe_replay_arguments` 被删除）。该模块本身仍存在于 working tree，等待 S2 删除。

**复核结论**：S1/S2/deferred 边界清晰。✓

### 12. README 更新

**`dayu/host/README.md`**：ToolRuntime 段新增 shared writer contract 说明；Outbox/tool trace 段从"宽松 projection"改为"统一 `HostDurableError` fail closed"；Resume 段从"LLM-safe replay 参数"改为"exact canonical replay 参数"，新增 wait resolution execution identity 不变量说明。

**`tests/README.md`**：新增 wait resolution identity 测试描述；更新 durable foundation 段落反映 shared writer 和 governance-only TOOL_AWAITING；更新 provider/Tool Trace 段落反映 four-consumer strict projection。

**复核结论**：README 更新反映已落地的 S1 事实，未写 S2/S3 未来计划。✓

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `dayu/runtime/json_redaction.py` 仍存在于 working tree，其唯一调用方（`_event_payload.py::llm_safe_replay_arguments`）已被 S1 删除。该模块为 S2 删除目标；S1 不触碰该文件是正确的。
- `run_transition.py` 覆盖率为 80%（精确达标），未覆盖行主要为 terminal/lost/cancel/expire 等非 wait-resolution 分支。这些分支由现有 `test_run_attempt_transitions.py` 覆盖，不在 S1 新增 scope 内。
- Issue #177（Doc output continuation wiring）和 Issue #178 均不在 R03 scope 内。
- real public-run smoke（§12）依赖外部 provider/网络/Fins 环境，不在本 code re-review 验证范围内；该 smoke 是 aggregate gate，不是 S1 slice gate。

## Conclusion

**PASS**

R03-S1 implementation 与 accepted plan §6 全部 contract 一致。34-target zero-change integrity 未被破坏。四项 Controller no-fix disposition 保持有效。CV-F01 已关闭。S1/S2/deferred 边界清晰。389 S1 matrix + 1952 full Host + pyright 0 errors + run_transition.py 80% coverage 全部通过。无新 material finding。

本 re-review 结论为 PASS。交回 Controller 裁决，不提交、不进入 S2/S3/aggregate。
