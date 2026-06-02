# WU-TOOL-01 Slice 1 Code Re-review

## Gate / Role

- Gate: code re-review
- Role: re-review specialist; 独立复核 CR1-CR6 关闭状态，不改文件、不 commit/push/PR
- Work unit: WU-TOOL-01 Attempt-scoped Duplicate Governance
- Slice: 1 - Typed Policy And Attempt-scoped Duplicate State
- Controller adjudication: `docs/reviews/wu-tool-01-code-review-slice1-controller-adjudication-20260601.md`
- Fix artifact: `docs/reviews/wu-tool-01-fix-slice1-codex-20260601.md`

## CR1-CR6 Close Verification

### CR1: `tool_runtime.py.__all__` 移除 duplicate governance typed contracts re-export

**结论**: closed.

**证据**:

- `tool_runtime.py.__all__`（行 5320-5380）不包含 `DuplicateAcceptedEntry`、`DuplicateDecision`、`DuplicateDecisionKind`、`DuplicateDurableMissingReason`、`DuplicateGovernanceMessages`、`DuplicateGovernancePolicy`、`DuplicateGovernanceRequest`、`DuplicateGovernanceScope`、`InMemoryAttemptDuplicateGovernance`。
- `tool_runtime.py` 内部仍 import 这些类型用于内部实现（行 119-131），不出现在 public API surface。

### CR2: 删除 Run-scoped registry compatibility facade

**结论**: closed.

**证据**:

- `rg "RunScopedDuplicateGovernanceRegistry|InMemoryRunScopedDuplicateGovernanceRegistry|duplicate_governance_registry|_duplicate_governance_registry|active_run_count|_duplicate_message" dayu/host/` -> 零匹配。
- `dayu/host/dispatch.py` 中 `_duplicate_governance_registry`、`duplicate_governance_registry`、`RunScoped`、`active_run_count` -> 零匹配。
- `tests/host/test_dispatch_scheduler.py` 中 `_duplicate_governance_registry`、`active_run_count`、`RunScopedDuplicate` -> 零匹配。
- ToolRuntime factory 不再接收 registry 参数，改用 `duplicate_governance_policy`。

### CR3: `DuplicateGovernancePort` 迁移到 `dayu.host.tool_duplicate_governance`

**结论**: closed.

**证据**:

- `DuplicateGovernancePort` Protocol 定义在 `dayu/host/tool_duplicate_governance.py:280-324`，包含完整中文 docstring。
- 在 `tool_duplicate_governance.py.__all__` 中 export（行 622）。
- `tool_runtime.py` 行 127 从 `dayu.host.tool_duplicate_governance` import 该 Protocol 供内部类型标注（`ToolRuntimeExecutor.__init__` 参数），未出现在 `tool_runtime.py.__all__`。

### CR4: owner cancellation 并发测试

**结论**: closed.

**证据**:

- 新增 `_ControllableCancellationToken` 测试辅助类（行 99-145）。
- 新增测试 `test_same_attempt_concurrent_owner_cancellation_reports_durable_missing`（行 958-1007）：
  - owner 使用可控取消 token，waiter 不传 token（默认未取消）。
  - `token.cancel("owner cancelled by test")` 在 waiter 注册后、owner 完成前触发。
  - 断言 `tool.call_count == 1`（in-flight 窗口内无二次真实执行）。
  - 断言 owner outcome 为 `ToolFailedOutcome`，hint 为 `"tool_runtime_cancelled"`。
  - 断言 waiter outcome 为 `ToolFailedOutcome`，hint 为 `"duplicate_prior_accept_missing"`。
  - 断言第三次调用 `tool.call_count == 2` 且 outcome 为 `ToolCompletedOutcome`（新 owner）。

### CR5: timeout durable-missing 测试断言增强

**结论**: closed.

**证据**:

- `test_same_attempt_concurrent_timed_out_accept_reports_durable_missing`（行 876-914）现在包含：
  - `assert tool.call_count == 1`（行 903）。
  - owner outcome 类型断言 `isinstance(owner_outcome.records[0].outcome, ToolFailedOutcome)`（行 904）。
  - waiter outcome 类型断言 `isinstance(waiter_outcome.records[0].outcome, ToolFailedOutcome)`（行 905）。
  - waiter hint 断言 `"duplicate_prior_accept_missing"`（行 906-907）。
  - 第三次同 key 调用断言 `tool.call_count == 2`（行 913），验证后续 fresh allow。

### CR6: 删除 `_duplicate_message()` fallback

**结论**: closed.

**证据**:

- `rg "_duplicate_message" dayu/host/` -> 零匹配，function 已删除。
- `DuplicateGovernanceMessages.__post_init__`（tool_duplicate_governance.py:101-117）校验所有消息字段非空，空/纯空白抛出 `ValueError`。
- `_policy_decision_from_duplicate()`（tool_runtime.py:4515-4537）在 `decision.message is None` 时 `raise ValueError("duplicate decision requires message")`，不回退默认消息。
- `DuplicateDecision` 构造路径均通过 `DuplicateGovernancePolicy.messages` 填充 message 字段（`InMemoryAttemptDuplicateGovernance._decision_for_accepted_entry` 行 496，`_allow_decision` 行 548，`decide_duplicate` durable_missing 分支行 421）。
- 新增测试 `test_duplicate_governance_messages_reject_empty_text`（行 1050）和 `test_duplicate_candidate_validation_rejects_missing_duplicate_message`（行 1058）。

## Adversarial Pass

### 新旧 bug 检查

- **无新类型错误**: pyright 返回 0 errors, 0 warnings。
- **无测试假阳性**: 所有 26 个 duplicate governance 测试和 57 个 dispatch scheduler 测试均通过。每个测试的 assert 都验证可观察行为（outcome 类型、hint 字符串、call_count），不依赖私有实现字段。
- **in-flight 释放正确性**: `record_durable_missing` 在 `tool_runtime.py:2212` 的 `finally` 块中调用，覆盖 owner 取消、异常、accept 拒绝、accept 超时全部四个失败分支。
- **无死锁风险**: `_AttemptDuplicateGovernanceState.condition` 在 terminal state 写入后调用 `notify_all()`（行 445/465），map entry 在 notifying 前已 pop 或标记 terminal state，waiter 持有 in-flight record 引用，不会在 map entry 移除后错误创建新 owner。

### 残留旧术语检查

- `tool_runtime.py` 中 "run-scoped"/"run-local" 匹配：行 7、791、1129、1294、1736、2736、2797，均在 **truncation** 上下文中（`TruncationManager`、`TruncationCursor`），与 duplicate governance 无关。符合 approved plan 第七节第 14 条。
- 测试文件中无任何 `run-local|run-scoped|RunScoped|RunLocal|同 Run` 匹配。

### scope 越界检查

- `dispatch.py` 改动限于删除 registry import 和 build argument 传递，无新增逻辑。
- `test_dispatch_scheduler.py` 改动限于删除私有 registry 生命周期断言；唯一的 "duplicate_registry" 残留是 `test_reactive_recovery_does_not_clear_duplicate_registry` 的**测试名称**（行 4031）和 docstring（行 4034），但测试体已不再访问任何 registry 内部状态，只验证 Attempt id 和 Run status 行为。是非阻塞命名陈旧问题。

### 未关闭的 deferred findings

- DS M3 awaiting fanout: 不在本 fix scope，controller 已 deferred-with-owner。
- DS L3 tool_trace.py duplicate_scope: Slice 3 范围，不在本 fix scope。

## Validation Results

```text
source .venv/bin/activate && python -m pytest tests/host/test_toolruntime_duplicate_governance.py
-> 26 passed

source .venv/bin/activate && python -m pytest tests/host/test_dispatch_scheduler.py
-> 57 passed

source .venv/bin/activate && pyright
-> 0 errors, 0 warnings, 0 informations
```

## Conclusion

CR1-CR6 全部 closed。无新 bug、类型错误、测试假阳性或 scope 越界。

Remaining blocking findings: **0**.
