# Gateflow Code Review: Host P4-S3 Run Follow-up Cancel

- gate: Phase 4 implementation
- slice: P4-S3 Run Admission, Follow-up Queue, Cancel Run And Cancel Session Runs Subset
- reviewer: AgentMiMo
- review date: 2026/05/14
- baseline: P4-S2 accepted slice commit `190d905`
- design truth: `docs/host/design.md`
- accepted plan: `docs/host/phase4-public-api-command-path-plan.md`
- implementation artifact: `docs/reviews/gateflow-implementation-host-p4-s3-run-followup-cancel-20260514.md`

## Conclusion

**Accepted / No blocking finding.**

P4-S3 实现符合 accepted plan 的 scope 和 design truth 要求。所有验证命令通过，无类型错误、无 whitespace 问题。

## Scope Verification

### P4-S3 子集边界

- ✅ **确认 P4-S4 行为未实现**：`get_run` 和 `stream_run_events` 未被实现或导出。grep 确认 `dayu/host/` 目录下无 `def get_run` 或 `def stream_run_events` 定义。
- ✅ **确认 scope correction 已执行**：implementation artifact 已记录首次实现包含 P4-S4 行为的 scope creep，以及后续移除修正。
- ✅ **确认导出范围正确**：`dayu/host/__init__.py` 只导出 `start_run`、`submit_followup`、`cancel_run`、`cancel_session_runs`，无 `get_run` 或 `stream_run_events`。

### P4-S3 允许实现项

- ✅ `start_run(host, request) -> RunSnapshot`
- ✅ `submit_followup(host, session_id, request) -> FollowupSnapshot`（只实现 `behavior=queue`）
- ✅ `cancel_run(host, run_id, request) -> RunSnapshot`（queued 和 pre-dispatch STARTING）
- ✅ `cancel_session_runs(host, session_id, request) -> SessionSnapshot`（Phase 4 子集）

## Implementation Correctness

### start_run

- ✅ **复用 internal admission**：`command.py:278-282` 直接调用 `host._admission_service.start_run()`。
- ✅ **direct running**：无 active Run 时创建新 Run 并返回 `RunSnapshot`。
- ✅ **queue**：有 active Run 且 `queue_policy="queue"` 时创建 QUEUED Run。
- ✅ **reject**：有 active Run 且 `queue_policy="reject"` 时抛出 `CONFLICT`。
- ✅ **attach_active**：有 active Run 且 `queue_policy="attach_active"` 时返回当前 active `RunSnapshot`，不追加 canonical attach fact（由 internal admission 保证）。
- ✅ **幂等重放**：同 semantic digest 返回当前 `RunSnapshot`，不追加重复事件。

### submit_followup

- ✅ **session_id 不一致**：`command.py:316-321` 检查 `session_id != request.session_id` 时抛出 `INVALID_STATE`。
- ✅ **QUEUE 返回正确**：`command.py:332-345` 构造 `FollowupSnapshot`，`accepted_run_id` 和 `accepted_run_status` 来自 admission result，`queued_run_id` 在 `status == QUEUED` 时等于 `accepted_run_id`，否则为 `None`。
- ✅ **STEER 返回 UNSUPPORTED_OPERATION**：`command.py:323-329` 抛出 `UNSUPPORTED_OPERATION(retryable=False)`，不调用 admission，不追加 EventLog。
- ✅ **default execution target**：`command.py:332` 使用 `_PUBLIC_FOLLOWUP_DEFAULT_EXECUTION_TARGET`，implementation artifact 已记录为 residual risk。

### cancel_run

- ✅ **queued cancel**：复用 internal admission `cancel_run()`。
- ✅ **pre-dispatch STARTING cancel**：复用 internal admission `cancel_run()`。
- ✅ **deferred cancel states 映射**：`command.py:358-372` 捕获 `INVALID_STATE` 并检查 `_is_deferred_cancel_state()`，属于 deferred 时抛出 `UNSUPPORTED_OPERATION`。
- ✅ **terminal/true invalid state 不被误映射**：`_is_deferred_cancel_state()` 只对 `WAITING`、`CANCELLING`、`RECOVERING`、`RUNNING`（非 pre-dispatch STARTING）返回 `True`，其它状态返回 `False`。
- ✅ **pre-dispatch STARTING 判断**：`command.py:448-466` 检查 `attempt.status == STARTING` 且 `dispatch_record.status == PENDING`。

### cancel_session_runs

- ✅ **单 write transaction**：`admission.py:119-129` 通过 `self.transaction_runner.run_write()` 在一个事务内执行。
- ✅ **先读取所有 non-terminal Runs**：`admission.py:142-164` 调用 `_read_supported_targets_or_raise()`，内部遍历 `read_non_terminal_runs_for_session()` 返回的所有非终态 Run。
- ✅ **unsupported non-terminal 在 EventLog append 前抛出**：`admission.py:146-163` 遇到 `target is None` 时立即抛出 `UNSUPPORTED_OPERATION`，此时尚未调用 `_cancel_target()`。
- ✅ **不 partial cancel**：验证测试 `test_cancel_session_runs_unsupported_non_terminal_has_no_partial_mutation` 确认存在 unsupported Run 时，queued Run 状态不变。
- ✅ **不 silently ignore**：unsupported non-terminal 抛出明确错误，不跳过。
- ✅ **支持子集正确**：
  - `QUEUED` Run：`admission.py:277`。
  - `RUNNING` + `Attempt STARTING` + `Dispatch PENDING`：`admission.py:279-294`。
- ✅ **cancel 行为正确**：
  - queued Run：`CANCEL_REQUESTED` + `RUN_CANCELLED`。
  - pre-dispatch STARTING：`CANCEL_REQUESTED` + `ATTEMPT_CANCELLED` + `RUN_CANCELLED`。

### cancel_session_runs idempotency

- ✅ **semantic digest 不含动态 Run list**：`admission.py:326-340` 只包含 `operation`、`session_id`、`reason`、`mode`、`caller_semantic_digest`、`call_context_digest`。
- ✅ **same key replay 返回当前 SessionSnapshot**：`admission.py:203-205` 命中幂等记录时调用 `_idempotent_session_cancel_result()`。
- ✅ **不取消首次后新接受的 Run**：幂等重放只读取 Session snapshot，不执行 cancel 操作。
- ✅ **empty supported set 记录幂等性**：`admission.py:220-230` 当 `targets` 为空时仍记录幂等结果，`first_cancel_event_id` 为 `None`。

### cancel_session_runs 不触发 queue promotion

- ✅ **实现确认**：`_CancelSessionRunsOperation` 只调用 `cancel_queued_in_transaction()` 和 `cancel_predispatch_starting_in_transaction()`，不调用 promotion 相关逻辑。
- ✅ **设计文档确认**：`host/README.md:45` 明确说明"该路径不触发 queue promotion"。

### Durable helpers

- ✅ **read_non_terminal_runs_for_session**：`state.py:922-974` 是 narrow durable helper，只读取非终态 Run rows，不包含 command facade 语义。
- ✅ **run_snapshot_from_row**：`state.py:984-1002` 是 narrow durable helper，只从 `RunRow` 构造 `RunSnapshot`，不包含 command facade 语义。
- ✅ **session_snapshot_from_rows**：`state.py:1778-1811` 已存在，`admission.py:232-236` 和 `admission.py:381-385` 复用它构造 `SessionSnapshot`。

### Phase Reminder 确认

- ✅ **Phase 5 owns dispatching / active worker cancel**：implementation artifact 和 host/README.md 已记录。
- ✅ **Phase 7 owns WAITING cancel**：implementation artifact 和 host/README.md 已记录。
- ✅ **Phase 11 owns RECOVERING cancel**：implementation artifact 和 host/README.md 已记录。
- ✅ **Phase 4 子集不得写成最终语义**：所有 deferred 状态映射为 `UNSUPPORTED_OPERATION`，不实现真正 cancel 逻辑。

## Code Quality

### 中文 docstring

- ✅ 所有公共函数（`start_run`、`submit_followup`、`cancel_run`、`cancel_session_runs`）均有完整中文 docstring，包含参数、返回值、异常。
- ✅ 所有内部函数（`_CancelSessionRunsOperation`、`_read_supported_targets_or_raise`、`_cancel_target`、`_cancel_queued_target`、`_cancel_predispatch_target`、`_idempotent_session_cancel_result`、`_session_cancel_target_for_run`、`_raise_for_session_cancel_transition_status`、`_cancel_session_runs_semantic_digest`）均有完整中文 docstring。
- ✅ `SessionCancelResult` dataclass 有中文 docstring。
- ✅ 模块级 docstring 已更新（`command.py:1-6`）。

### 严格类型

- ✅ 无 `Any`、`object`、无类型参数、无类型返回值。
- ✅ 所有函数签名完全类型化。
- ✅ `SessionCancelResult` 使用明确类型：`snapshot: SessionSnapshot`、`idempotent_replay: bool`、`cancelled_run_count: int`。

### 无 getattr/hasattr 逃避类型

- ✅ `command.py` 中无 `getattr` 或 `hasattr` 调用。
- ✅ `admission.py` 中无 `getattr` 或 `hasattr` 调用。
- ✅ 所有访问通过明确的类型化属性。

### 无兼容 wrapper/god bag

- ✅ 无兼容性 re-export。
- ✅ 无兼容性 wrapper。
- ✅ 无 god object、god dataclass、god bag。
- ✅ `HostApiError.detail` 保持 `HostApiErrorDetail | None` 类型，无额外 `extra`、`payload`、`metadata` 字段。

## README 同步

### dayu/host/README.md

- ✅ 更新公共命名空间描述，包含 Run command facade。
- ✅ 添加 "Public Run Command Path" 章节，记录当前已实现的 Run public facade。
- ✅ 更新 internal admission 描述，明确 session-scope cancel 只服务 Phase 4 子集。
- ✅ 更新未实现列表，区分 "Run read public facade" 与 "Run public command facade"。
- ✅ 更新测试覆盖描述，包含 Run public facade 测试范围。
- ✅ 无旧术语、旧路径、旧入口残留。

### tests/README.md

- ✅ 更新 `tests/host/` 描述，包含 Run public command facade。
- ✅ 添加 public run API 测试覆盖说明。
- ✅ 与当前测试范围一致。

## Validation Results

- ✅ `source .venv/bin/activate && pytest tests/host/test_public_run_api.py tests/host/test_public_cancel_session_runs.py tests/host/test_admission_queue.py tests/host/test_admission_multiprocess.py -q`
  - passed: 37 tests
- ✅ `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - passed: 0 errors, 0 warnings, 0 informations
- ✅ `git diff --check`
  - passed
- ✅ `source .venv/bin/activate && pytest tests/host/test_package_exports.py -q`
  - passed: 5 tests
- ✅ `source .venv/bin/activate && pytest tests/host -q`
  - passed: 191 tests (full Host regression)

## Residual Risks (Non-blocking)

1. **submit_followup queue default execution target**：`_PUBLIC_FOLLOWUP_DEFAULT_EXECUTION_TARGET` 是硬编码默认值，因为 `SubmitFollowupRequest` 无 public `resolved_execution_target` 字段且 policy provider 集成不在当前 slice。Implementation artifact 已记录此 residual risk，后续 policy-provider slice 应替换为显式 Host policy resolution output。

2. **cancel_session_runs 部分支持**：Phase 4 只覆盖 queued 和 pre-dispatch STARTING，后续 Phase 5/7/11 需扩展支持范围。这是 intentional design，非实现缺陷。

## Findings Summary

| # | Severity | File | Line | Description |
|---|----------|------|------|-------------|
| - | - | - | - | No blocking finding |

**Total: 0 blocking findings.**

## Recommendation

**Accept.** P4-S3 实现符合 accepted plan 和 design truth 要求，代码质量符合项目约束，所有验证通过。
