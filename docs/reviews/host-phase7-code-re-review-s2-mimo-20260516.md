# Code Re-Review

## Scope

- Mode: current changes (re-review of fix pass)
- Branch: feat/host-phase7-tool-awaiting-resolve-wait
- Base: main
- Output file: docs/reviews/host-phase7-code-re-review-s2-mimo-20260516.md
- Included scope: fix artifact, new tests, `_AwaitingAcceptStateConflictError`, docstring/comment additions
- Excluded scope: all other P7-S2 files (unchanged in fix pass)
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Verification Summary

### S2-F1 accepted - awaiting accept 失败路径缺少 tool_runtime 层集成测试 ✅ 已关闭

`tests/host/test_toolruntime_executor.py` 新增两个测试：

- `test_awaiting_accept_rejected_returns_governed_error`（第 491 行）：使用 `_SequencedAwaitingAcceptPort` 返回 `ToolAwaitingRejectedAck(reason_code=IDEMPOTENCY_CONFLICT)`，断言 `outcome.result.error == "tool_awaiting_accept_rejected"` 且 `outcome.result.hint == "accept_rejected:idempotency_conflict"`。
- `test_awaiting_accept_timeout_returns_governed_error`（第 521 行）：返回 `ToolAwaitingAcceptTimedOut(attempt_count=1, last_error_code="accept_ack_lost")`，断言 `error == "tool_awaiting_accept_timeout"` 且 `hint == "accept_ack_lost"`。

新增 `_SequencedAwaitingAcceptPort`（第 290 行）支持按序脚本化返回任意 `ToolAwaitingAcceptResult`。

### S2-F2 accepted - POLL binding external_job_ref 缺失路径缺少 tool_runtime 层测试 ✅ 已关闭

`test_poll_awaiting_without_external_job_ref_is_governed_error`（第 550 行）：使用 `_wait_adapter_registry_without_external_job_ref()` helper 配置 `WaitAdapterBinding(resume_policy=POLL, external_job_ref_source=NONE)`，断言 `awaiting_accept_port.candidates == []`（未进入 accept port）且 `outcome.result.hint == "awaiting_external_job_missing"`。

### S2-F3 accepted - `_normalize_runtime_outcome` 退化为空透传 ✅ 已关闭

`_normalize_runtime_outcome` docstring 已更新（第 2640-2644 行）：明确说明 P7-S2 起 awaiting 已分流到 Host awaiting accept path，本 helper 保留为普通工具 outcome 的扩展点，避免后续治理归一化重新混入 awaiting 分支。

### S2-F4 accepted - awaiting accept 成功后 duplicate registry 未更新 ✅ 已关闭

`_accept_awaiting` 第 2492-2493 行已添加行内注释：`# Awaiting 是等待中间态，不写入 duplicate accepted index；等待解析后的工具结果事实由 resolve_wait / resume path 负责。`

## Additional Fixes

### `_AwaitingAcceptStateConflictError`

`waiting.py` 新增 `_AwaitingAcceptStateConflictError(HostDurableError)`（第 66 行）。`_accept_in_transaction` 中 post-precondition CAS 失败时 raise 该异常（第 388 行），`accept_tool_awaiting` catch 后返回结构化 `ToolAwaitingRejectedAck(reason_code=CAS_CONFLICT)`（第 300-304 行），不再泄漏 generic `HostDurableError`。

### stale execution reject 测试

`test_awaiting_accept_stale_execution_rejects_without_wait_record`（第 152 行）：用 `execution_id="execution-stale"` 构造 candidate，断言 `reason_code.value == "stale_execution"` 且无 wait record、无 events 写入。

## Validation

- `pytest tests/host/test_wait_awaiting_accept.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_accept_barrier.py -q` → 24 passed in 0.22s
- `python -m pyright dayu/host tests/host` → 0 errors, 0 warnings, 0 informations

## Open Questions

无

## Residual Risk

无新增。原 review 的 Residual Risk（precondition 失败路径、CAS 失败路径、replay 异常路径）部分已由新增 stale execution 测试和 `_AwaitingAcceptStateConflictError` 覆盖；CAS_LOST race test 仍 deferred to P7-S4。
