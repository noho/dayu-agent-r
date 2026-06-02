# WU-TOOL-01 Slice 1 Code Re-Review

## Gate / Work Unit / Slice

- Gate: code re-review
- Work unit: WU-TOOL-01 Attempt-scoped Duplicate Governance
- Slice: 1 - Typed Policy And Attempt-scoped Duplicate State
- Approved plan: `docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`
- Fix artifact: `docs/reviews/wu-tool-01-fix-slice1-codex-20260601.md`
- Controller adjudication: `docs/reviews/wu-tool-01-code-review-slice1-controller-adjudication-20260601.md`
- Re-review date: 2026-06-01

## Re-Review Target Files

- `dayu/host/tool_duplicate_governance.py`
- `dayu/host/tool_runtime.py`
- `dayu/host/dispatch.py`
- `tests/host/test_toolruntime_duplicate_governance.py`
- `tests/host/test_dispatch_scheduler.py`

## Independent Verification Results

- `pytest tests/host/test_toolruntime_duplicate_governance.py`: **26 passed, 0 failed** ✓
- `pytest tests/host/test_dispatch_scheduler.py`: **57 passed, 0 failed** ✓
- `pyright dayu/host/tool_duplicate_governance.py dayu/host/tool_runtime.py dayu/host/dispatch.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_dispatch_scheduler.py`: **0 errors, 0 warnings, 0 informations** ✓

## CR Finding Closure Verification

### CR1: `tool_runtime.py.__all__` re-export duplicate governance typed contracts — CLOSED ✓

**Fix method**: 从 `__all__` 删除所有 duplicate governance typed contracts 符号。

**Verified evidence**:
- `tool_runtime.py:5340-5381` — `__all__` 不包含 `DuplicateAcceptedEntry`、`DuplicateDecision`、`DuplicateDecisionKind`、`DuplicateDurableMissingReason`、`DuplicateGovernanceMessages`、`DuplicateGovernancePolicy`、`DuplicateGovernanceRequest`、`DuplicateGovernanceScope`、`InMemoryAttemptDuplicateGovernance`、`DuplicateGovernancePort` 中的任何一个。
- `tool_runtime.py:121-132` — 保留内部 import 供 `_execute_one`、`_policy_decision_from_duplicate` 等内部函数使用，符合 controller 要求。
- `tests/host/test_toolruntime_duplicate_governance.py:56-60` — 测试正确从 `dayu.host.tool_duplicate_governance` 导入。

**Residual risk**: 无。

---

### CR2: Run-scoped registry compatibility facade 未删除 — CLOSED ✓

**Fix method**: 删除 `RunScopedDuplicateGovernanceRegistry`、`InMemoryRunScopedDuplicateGovernanceRegistry`、`ToolRuntimeBuildRequest.duplicate_governance_registry` 字段；更新 `dispatch.py` 移除 registry import/field/calls/build arg。

**Verified evidence**:
- `rg "RunScopedDuplicateGovernanceRegistry|InMemoryRunScopedDuplicateGovernanceRegistry|duplicate_governance_registry|_duplicate_governance_registry"` — 源码和测试中零匹配（仅 docs/reviews 中有历史引用）。
- `dispatch.py:185-192` — import 列表中无 registry 符号。
- `tool_runtime.py:1918-1920` — `ToolRuntimeBuildRequest.duplicate_governance_policy: DuplicateGovernancePolicy`（非 registry）。
- `tool_runtime.py:2756-2758` — factory 直接创建 `InMemoryAttemptDuplicateGovernance(request.duplicate_governance_policy)`。
- `dispatch.py` 全文无 `duplicate_governance` 引用（dispatch 不再参与 registry 生命周期）。

**Residual risk**: `docs/reviews/wu-life-01-02-aggregate-deepreview-mimo-20260601.md:108` 引用了 `_duplicate_governance_registry` 作为旧 lifecycle test 内部状态 — 这是 review artifact 中的历史引用，不影响代码。

---

### CR3: `DuplicateGovernancePort` 应迁移到 typed contract module — CLOSED ✓

**Fix method**: 将 `DuplicateGovernancePort` Protocol 移入 `tool_duplicate_governance.py`；`tool_runtime.py` 仅 import 供内部使用。

**Verified evidence**:
- `tool_duplicate_governance.py:280-324` — `DuplicateGovernancePort(Protocol)` 定义完整，含 `decide_duplicate`、`record_accepted`、`record_durable_missing` 三个 async 方法。
- `tool_duplicate_governance.py:622` — `__all__` 导出 `"DuplicateGovernancePort"`。
- `tool_runtime.py:127` — `from dayu.host.tool_duplicate_governance import ... DuplicateGovernancePort`（内部 import，不在 `__all__` 中）。

**Residual risk**: 无。

---

### CR4: owner cancellation 并发测试缺口 — CLOSED ✓

**Fix method**: 添加 `_ControllableCancellationToken` + `test_same_attempt_concurrent_owner_cancellation_reports_durable_missing` 并发测试。

**Verified evidence**:
- `tests/host/test_toolruntime_duplicate_governance.py:99-130` — `_ControllableCancellationToken` 实现 `cancel(reason)` 方法，`is_cancelled()` 在 cancel 后返回 `True`。
- `tests/host/test_toolruntime_duplicate_governance.py:958-1008` — 测试流程：
  1. owner 以 controllable token 启动，进入 blocking tool 执行。
  2. waiter 在 owner 执行中创建。
  3. `token.cancel("owner cancelled by test")` 触发 owner cancellation。
  4. 断言：`tool.call_count == 1`（waiter 不执行真实调用）。
  5. 断言：owner outcome 为 `ToolFailedOutcome`，hint 为 `"tool_runtime_cancelled"`。
  6. 断言：waiter outcome 为 `ToolFailedOutcome`，hint 为 `"duplicate_prior_accept_missing"`。
  7. `release.set()` 后第三次调用：`tool.call_count == 2`，outcome 为 `ToolCompletedOutcome`（fresh owner 成功执行）。

**并发真实性**: 使用 `asyncio.Event`（`entered`/`release`）控制时序，`asyncio.wait_for(gather, timeout=1.0)` 防止死锁。无 `time.sleep` 或固定延时。

**Residual risk**: 无。

---

### CR5: timeout durable-missing 测试断言过弱 — CLOSED ✓

**Fix method**: 补齐 timeout 测试与 rejected 测试等价的断言。

**Verified evidence** — `tests/host/test_toolruntime_duplicate_governance.py:876-914`:
- `tool.call_count == 1` — waiter 不执行真实调用。✓
- `isinstance(owner_outcome.records[0].outcome, ToolFailedOutcome)` — owner outcome 类型。✓
- `isinstance(waiter_outcome.records[0].outcome, ToolFailedOutcome)` — waiter outcome 类型。✓
- `waiter_outcome.records[0].outcome.result.hint == "duplicate_prior_accept_missing"` — waiter hint。✓
- 第三次调用：`tool.call_count == 2`，`isinstance(later.records[0].outcome, ToolFailedOutcome)` — fresh owner 重新执行。✓

与 rejected 测试（`test_same_attempt_concurrent_rejected_accept_reports_durable_missing`）断言结构等价。

**Residual risk**: 无。

---

### CR6: `_duplicate_message()` fallback 不应脱离 configured policy — CLOSED ✓

**Fix method**: 删除 `_duplicate_message()` 函数；duplicate governed/reuse candidate 缺少 `duplicate_decision_message` 时 fail fast。

**Verified evidence**:
- `rg "_duplicate_message"` — `tool_runtime.py` 中零匹配。
- `rg "DuplicateGovernanceMessages"` — `tool_runtime.py` 中零匹配（不再 import 该类型）。
- `tool_runtime.py:3836-3837` — `if candidate.duplicate_decision_message is None: raise ValueError("duplicate decision requires duplicate_decision_message")`。
- `tool_runtime.py:3956-3958` — `if candidate.duplicate_decision_message is None: raise ValueError("reuse requires duplicate_decision_message")`。
- `tool_runtime.py:4690` — `_policy_decision_from_duplicate` 从 `duplicate_decision.message` 填充 candidate 字段。
- `tool_runtime.py:4777` — `_record_duplicate_accepted` 从 `duplicate_decision.message` 填充 candidate 字段。
- `tests/host/test_toolruntime_duplicate_governance.py:1057-1066` — `test_duplicate_candidate_validation_rejects_missing_duplicate_message` 验证缺少 message 时抛出 `ValueError`。

**设计正确性**: `duplicate_decision.message` 始终由 `InMemoryAttemptDuplicateGovernance` 从 `policy.messages.message_for(kind)` 填充（`tool_duplicate_governance.py:374`、`449`、`501`）。删除 fallback 后，若新 `DuplicateGovernancePort` 实现遗漏 message，验证会在 candidate 构建时 fail fast，而非静默使用默认消息。

**Residual risk**: 无。

## Fix Quality Assessment

### 是否引入新 bug

- **dispatch.py**: 移除了 `InMemoryRunScopedDuplicateGovernanceRegistry` 的 import、实例化、`clear_run`/`clear_all` 调用和 build request 传参。这些操作原本是 no-op facade（`duplicate_governance_for_run` 忽略 `run_id`，每次创建新 `InMemoryAttemptDuplicateGovernance`）。移除不影响 duplicate governance 语义。✓
- **tool_runtime.py**: `ToolRuntimeBuildRequest` 从 `duplicate_governance_registry` 变为 `duplicate_governance_policy`。factory 直接使用 policy 创建 governance 实例。dispatch 构建 request 时传入 policy（非 registry）。路径一致。✓
- **validation 收紧**: 删除 `_duplicate_message` fallback 后，所有非 ALLOW 决策路径必须携带 message。当前 `InMemoryAttemptDuplicateGovernance` 的三个决策生成点均填充 message。✓

### 是否引入类型问题

- pyright 0 errors, 0 warnings, 0 informations。✓

### 测试假阳性检查

- 新增 cancellation 测试使用 `_ControllableCancellationToken`（可控 cancel 信号），非 mock patch。✓
- `asyncio.sleep(0)` 仅用于 yield event loop，不依赖时序假设。✓
- `asyncio.wait_for(gather, timeout=1.0)` 防止 deadlock，超时会 fail test 而非静默通过。✓
- 所有并发测试使用 `asyncio.Event` 同步，无 `time.sleep` 或固定延时。✓

### Scope 越界检查

- CR2 fix 扩展到 `dispatch.py` 和 `tests/host/test_dispatch_scheduler.py` — 这是 controller adjudication 明确授权的范围扩展（"为彻底删除 run-scoped compatibility surface，本次 fix 允许最小范围扩展到 dispatch.py 和 test_dispatch_scheduler.py"）。✓
- 未修改 `dayu/host/tool_duplicate_governance.py` 以外的 typed contract 文件。✓
- 未修改 README（controller 未授权）。✓

## Plan Compliance Re-Check

| Plan Slice 1 要求 | 状态 | 证据 |
|---|---|---|
| typed contracts 迁移至 `tool_duplicate_governance.py` | ✓ | 完成 |
| `DuplicateGovernancePort` 在 `tool_duplicate_governance.py` | ✓ | CR3 fix |
| `__all__` 不 re-export duplicate governance types | ✓ | CR1 fix |
| 无 RunScoped/RunLocal compatibility surface | ✓ | CR2 fix |
| in-flight owner/waiter 状态机 | ✓ | 原实现正确 |
| owner terminal → durable-missing | ✓ | 原实现 + CR4/CR5 测试覆盖 |
| `_duplicate_message` fallback 删除 | ✓ | CR6 fix |
| 无 `Any`/`object`/无类型签名 | ✓ | pyright 验证 |
| 中文 docstring 完整 | ✓ | 已验证 |
| 测试覆盖（26 tests） | ✓ | CR4 +2 tests, CR6 +1 test, CR5 strengthened |

## Conclusion

**6 accepted findings (CR1-CR6) 全部 closed。** fix 未引入新 bug、类型问题、测试假阳性或 scope 越界。dispatch.py 的范围扩展经 controller 授权且最小化。所有验证通过。

**Remaining blocking findings: 0**

---

## Re-Review Metadata

- Re-reviewer: MiMo (re-review specialist)
- Date: 2026-06-01
- Target branch: `fix/wu-tool-01-attempt-scoped-duplicate-governance`
- Artifact path: `docs/reviews/wu-tool-01-code-rereview-slice1-mimo-20260601.md`
