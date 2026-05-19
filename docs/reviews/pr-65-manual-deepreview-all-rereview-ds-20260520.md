# Code Review — PR 65 Manual Deepreview-All Fix Re-Review

## Scope

- Mode: current changes (workspace diff re-review)
- Branch: feat/host-phase-11-recovery
- Base: main
- Output file: docs/reviews/pr-65-manual-deepreview-all-rereview-ds-20260520.md
- Included scope: uncommitted workspace diff fixing controller-accepted findings from:
  - docs/reviews/repo-review-20260520-060834.md
  - docs/reviews/repo-review-20260520-060858.md
- Non-goals (controller-deferred): PID start_token boot_id, AsyncAgent structure, EventLog corrupted payload tolerance, compaction budget redesign, recovery dispatch count semantics, public interface changes
- Parallel review coverage: 无

## Changes Verified

### 1. recovery.py — Startup scan 唤醒 queue promotion (Finding: recovery scan 不唤醒 ACCEPTED/QUEUED)

- **入口/函数**: `StartupRecoveryScanner.scan` / `_classify_run` / `_append_unseen_session_id`
- **文件(行号)**: `dayu/host/recovery.py` (139-148, 190-217, 241-253, 697-712)
- **变更**: ACCEPTED 和 QUEUED Run 分类时将 session_id 收集到 `queue_promotion_sessions`，事务提交后调用 `wake_queue_promotion`。`_append_unseen_session_id` 使用 `set` 去重，O(1) 成员检查。
- **验证结论**: 通过。事务提交后唤醒，状态保留（不写数据库），set 去重正确。`dispatch_wakeup_port is not None` 守卫正确。`_RecordingWakeup` 测试桩验证了 wake 行为。

### 2. tool_runtime.py — Awaiting timeout diagnostic refs 类型一致 (Finding 1 0834: 类型标注错误)

- **入口/函数**: `ToolRuntimeExecutor._accept_awaiting_with_retry`
- **文件(行号)**: `dayu/host/tool_runtime.py` (2846)
- **变更**: `diagnostics = tuple(result.diagnostic_refs)`
- **验证结论**: 通过。`ToolAwaitingAcceptTimedOut.diagnostic_refs: tuple[str, ...]`（`waiting.py:307`），`tuple()` 包裹确保类型推断明确为 `tuple[str, ...]`。末行 `(*diagnostics, timeout_ref.ref_id)` 拼接 `str` 与 `str`，类型一致。

### 3. tool_runtime.py — Duplicate ALLOW 不发出 governed event (Finding 7 0834: spurious governed event)

- **入口/函数**: `_should_append_governed_event`
- **文件(行号)**: `dayu/host/tool_runtime.py` (3560-3567)
- **变更**: 第三个条件增加 `candidate.duplicate_decision is not DuplicateDecisionKind.ALLOW`
- **验证结论**: 通过。`duplicate_decision` 为 `ALLOW` 时返回 False，不追加 `TOOL_CALL_GOVERNED`。`test_duplicate_allow_does_not_append_governed_event` 验证了 event stream 仅含 `TOOL_CALL_REQUESTED` + `TOOL_RESULT_ACCEPTED`。

### 4. context_governance.py — CLEAR + empty open_questions 不误报 retained (Finding 5 0834: 语义缺陷)

- **入口/函数**: `_open_questions_retained`
- **文件(行号)**: `dayu/host/context_governance.py` (454-459)
- **变更**: 重构为三级判断：summary 有 questions → True；REPLACE 且 value 非空 → True；其余 → False
- **验证结论**: 通过。CLEAR + empty summary → False。REPLACE with None/empty → False。MISSING → False。`test_quality_marks_open_questions_lost_when_clear_without_summary_questions` 验证。

### 5. retry_policy.py — 非 429 Retry-After cap 至 120s (Finding 8 0858: 无上限)

- **入口/函数**: `compute_retry_decision`
- **文件(行号)**: `dayu/engine/runners/openai/retry_policy.py` (91-94)
- **变更**: 非 429 `Retry-After` 路径增加 `min(retry_after_seconds, _RATE_LIMIT_RETRY_AFTER_CAP_SECONDS)`
- **验证结论**: 通过。cap 为 120s，与 429 路径一致。docstring 同步修正。`test_non_rate_limit_retry_after_capped_by_stable_retry_after_limit` 验证 999s → 120s。

### 6. non_stream_parser.py — 非流式 provider error object 检测 (Finding 9 0858: 错误信息丢失)

- **入口/函数**: `_emit_from_dict` / `_provider_error_message`
- **文件(行号)**: `dayu/engine/runners/openai/non_stream_parser.py` (62-64, 216-234, 357-371)
- **变更**: 在 choices 检查前新增 `"error"` 字段检查；产出 `RunnerProtocolErrorData(provider_request_id, raw_payload)` + `RunnerDone(ERROR)`。`_provider_error_message` 处理 str/dict 两种 error payload。
- **验证结论**: 通过。`_ERROR_FIELD` / `_ERROR_MESSAGE_FIELD` 常量与 `sse_parser.py` 一致。`test_non_stream_provider_error_object_emits_protocol_error` 验证了 protocol error + error done 事件序列及 provider 信息保留。

### 7. admission.py — ATTACH_ACTIVE 返回 ACCEPTED Run (Finding 10 0858: 拒绝 ACCEPTED)

- **入口/函数**: `_StartRunOperation._handle_active_run`
- **文件(行号)**: `dayu/host/admission.py` (1015-1026)
- **变更**: ACCEPTED 状态不再抛 CONFLICT；early return `RunAdmissionResult(run=active, attempt=None, dispatch_record=None, attached_active=True)`
- **验证结论**: 通过。early return 确保不写 idempotency record、不创建 attempt。`attached_active=True` 正确标记附着而非新创建。`test_start_run_accepts_and_attach_active_returns_unstarted_run` 和 `test_reject_conflicts_and_attach_active_returns_accepted_active` 验证了无 side effect 和状态不变。

### 8. README 同步更新

- `dayu/engine/README.md`: "SSE 与非流式顶层 error object" 覆盖非流式新增场景。
- `dayu/host/README.md`: "ACCEPTED 与 QUEUED 会在 scan 事务提交后唤醒 queue promotion" 补充 recovery 行为。
- **验证结论**: 更新与代码实现一致。

## Findings

未发现实质性问题。

## Open Questions

1. `_accept_awaiting_with_retry` 的 `tuple()` 包裹虽确保类型安全，但如果原始 finding 1 所指的 `ToolFactAcceptTimedOut`（`diagnostic_refs: tuple[ToolTraceDiagnosticRef, ...]`）与 `ToolAwaitingAcceptTimedOut`（`diagnostic_refs: tuple[str, ...]`）的类型不一致是设计意图，应在两个 TimedOut 类的 docstring 中明确说明为何一个存 `str` ref id 另一个存 `ToolTraceDiagnosticRef` 对象。

## Residual Risk

- `_accept_awaiting_with_retry` 的 `tuple()` 包裹未改变运行时语义，仅做防御。若 `accept_tool_awaiting` 实际返回类型与声明的 `ToolAwaitingAcceptTimedOut.diagnostic_refs: tuple[str, ...]` 不一致，运行时问题仍存在。但当前实现与声明一致，短期风险为零。
- Non-goal 区域（PID probe、EventLog 损坏、compaction budget、recovery dispatch count）仍存在原 review 中记录的已知风险，需按 controller 指定的 defer 时间线跟进。
