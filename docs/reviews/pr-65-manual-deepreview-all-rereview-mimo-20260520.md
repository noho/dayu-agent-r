# Code Review

## Scope

- Mode: current changes (re-review gate)
- Branch: feat/host-phase-11-recovery
- Base: main (uncommitted workspace diff)
- Output file: docs/reviews/pr-65-manual-deepreview-all-rereview-mimo-20260520.md
- Review date: 2026-05-20 06:45 CST
- Included scope: controller-accepted findings fix diff from two manual all-repo artifacts
- Excluded scope: controller-deferred non-goals (PID start_token boot_id, AsyncAgent structure, EventLog corrupted payload tolerance, compaction budget redesign, recovery dispatch count semantics, public interface changes)
- Parallel review coverage: 无

## Verified Scope Items

| # | Scope Item | 文件 | Verdict |
|---|-----------|------|---------|
| 1 | recovery.py startup scan wakes queue promotion for ACCEPTED and QUEUED after commit | `dayu/host/recovery.py` | PASS |
| 2 | tool_runtime.py awaiting timeout diagnostic refs coherent | `dayu/host/tool_runtime.py` | PASS |
| 3 | tool_runtime.py duplicate ALLOW does not emit governed event | `dayu/host/tool_runtime.py` | PASS |
| 4 | context_governance.py CLEAR + empty open_questions not retained | `dayu/host/context_governance.py` | PASS |
| 5 | retry_policy.py non-429 Retry-After capped | `dayu/engine/runners/openai/retry_policy.py` | PASS |
| 6 | non_stream_parser.py top-level provider error becomes protocol error | `dayu/engine/runners/openai/non_stream_parser.py` | PASS |
| 7 | admission.py ATTACH_ACTIVE attaches ACCEPTED without side effects | `dayu/host/admission.py` | PASS |
| 8 | Tests aligned | 7 test files | PASS |
| 9 | README updates aligned | `dayu/engine/README.md`, `dayu/host/README.md` | PASS |

## Findings

未发现实质性问题。

各修复的实现正确性已通过以下方式验证：

### 1. recovery.py: queue promotion wakeup

- `_classify_run` 在 ACCEPTED 和 QUEUED 分支各调用 `_append_unseen_session_id`，将 session_id 追加到 `queue_promotion_sessions` 列表。
- `_append_unseen_session_id` 使用 `set[str]` 做 O(1) 去重，不存在 O(n) membership 问题。
- 扫描事务提交后（`result = self.transaction_runner.run_write(operation)`），才遍历 `result.queue_promotion_sessions` 调用 `wake_queue_promotion`。
- ACCEPTED 和 QUEUED 的原始状态未被修改（无 mutation），仅追加了 wakeup 摘要。
- `StartupRecoveryScanResult` 新增 `queue_promotion_sessions: tuple[str, ...]` 字段，默认值为 `()`，不破坏现有调用方。

### 2. tool_runtime.py: diagnostic refs 类型一致性

- `_accept_awaiting_with_retry` 中 `diagnostics: tuple[str, ...] = ()` 声明。
- 第一轮 timeout 时，`diagnostic_refs=diagnostics` 传入 `ToolAwaitingAcceptTimedOut`，为 `()`。
- 第二轮 timeout 前，`diagnostics = tuple(result.diagnostic_refs)` 从 `ToolAwaitingAcceptTimedOut.diagnostic_refs: tuple[str, ...]` 取值，类型一致。
- 最终构造 `diagnostic_refs=(*diagnostics, timeout_ref.ref_id)` 拼接 `str` 元素，结果为 `tuple[str, ...]`。
- `ToolAwaitingAcceptTimedOut.diagnostic_refs: tuple[str, ...]` 声明与实际值一致。
- pyright 报告 0 errors。

### 3. tool_runtime.py: duplicate ALLOW 不产生 governed event

- `_should_append_governed_event` 第三个条件改为 `candidate.duplicate_decision is not None and candidate.duplicate_decision is not DuplicateDecisionKind.ALLOW`。
- 当 `duplicate_decision` 为 `ALLOW` 时，条件为 `True and False` = `False`，不触发 governed event。
- 当 `duplicate_decision` 为非 `ALLOW`（如 `REJECT`）时，条件为 `True and True` = `True`，正常记录治理事实。
- 当 `duplicate_decision` 为 `None` 时，条件为 `False`，不触发。

### 4. context_governance.py: CLEAR + 空 summary 不误判 retained

- `PinnedPatchOperation.CLEAR` 时，不满足 `REPLACE` 分支，落入 `return False`。
- `PinnedPatchOperation.REPLACE` 时，检查 `patch.value is not None and len(patch.value) > 0`，空值返回 `False`。
- `PinnedPatchOperation.MISSING` 时，直接返回 `False`。
- 仅当 summary 有 open questions 或 REPLACE 有非空值时返回 `True`。

### 5. retry_policy.py: non-429 Retry-After cap

- `elif retry_after_seconds is not None` 分支改为 `sleep_seconds = min(retry_after_seconds, _RATE_LIMIT_RETRY_AFTER_CAP_SECONDS)`。
- `_RATE_LIMIT_RETRY_AFTER_CAP_SECONDS = 120`，与 429 路径一致。
- 文档注释同步更新为 "cap 至 120s"。
- 测试 `test_non_rate_limit_retry_after_capped_by_stable_retry_after_limit` 验证 999s 被 cap 到 120s。

### 6. non_stream_parser.py: 顶层 error object 处理

- `_emit_from_dict` 顶部新增 `if _ERROR_FIELD in parsed` 检查，位于 `choices` 检查之前。
- 发出 `RunnerProtocolErrorData`（含 `error_code`、`message`、`provider_request_id`、`raw_payload`）和 `RunnerDoneData(ERROR)` 后立即 return。
- `_provider_error_message` 处理 str/dict/缺失 message 三种情况，均有安全回退。
- 与 SSE 解析器（`_handle_chunk_object`）行为对齐。
- README 文档同步更新为 "SSE 与非流式顶层 error object"。

### 7. admission.py: ATTACH_ACTIVE 接受 ACCEPTED Run

- `RunStatus.ACCEPTED` 分支从 `raise HostApiError(CONFLICT)` 改为 `return RunAdmissionResult(...)`。
- `attached_active=True`，`created=False`，`attempt=None`，`dispatch_record=None`。
- 不调用 `idempotency_store.record_idempotent_result`（ACCEPTED 尚未 dispatch，无 idempotent 结果可记录）。
- 不写新 EventLog 事件（`_event_count` 断言前后不变）。
- 测试验证 `run.run_id == active.run.run_id`，确认返回同一 Run。

### 8. 测试覆盖

- `test_recovery_scan.py`: 新增 `_RecordingWakeup` 辅助类；`test_scan_accepted_*` 和 `test_scan_queued_*` 各增加 3 条断言验证 wakeup 行为。
- `test_compaction_contract.py`: 新增 `test_quality_marks_open_questions_lost_when_clear_without_summary_questions`。
- `test_admission_queue.py`: 原 `test_reject_and_attach_active_conflict_with_accepted_active` 拆分为 reject 冲突和 attach_active 返回现有 Run 两部分。
- `test_public_run_api.py`: 类似拆分，验证 attach_active 返回 ACCEPTED Run。
- `test_protocol_error.py`: 新增 `test_non_stream_provider_error_object_emits_protocol_error`。
- `test_retry_backoff.py`: 原 "not capped" 测试改为 "capped" 测试。
- `test_toolruntime_accept_barrier.py`: 新增 `test_duplicate_allow_does_not_append_governed_event`。
- 全部 107 测试通过，pyright 0 errors。

## Open Questions

无。

## Residual Risk

- 本次修复不涉及 controller-deferred 的非目标项（PID start_token boot_id、EventLog corrupted payload tolerance、compaction budget 估算精度、recovery dispatch count 语义等）。这些风险仍由原始 review artifact 记录。
- `ToolAwaitingAcceptTimedOut.diagnostic_refs` 的类型声明（`tuple[str, ...]`）与 `ToolFactAcceptTimedOut.diagnostic_refs`（`tuple[ToolTraceDiagnosticRef, ...]`）语义不一致。当前行为正确（实际存入的是 str），但两个 "TimedOut" 类型的 diagnostic_refs 语义不同可能造成维护困惑。此为原始 review 的 Open Question #6，本次修复未触及，controller 已知。
