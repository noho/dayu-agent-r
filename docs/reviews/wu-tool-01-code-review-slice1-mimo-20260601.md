# WU-TOOL-01 Slice 1 Code Review

## Gate / Work Unit / Slice

- Gate: code review
- Work unit: WU-TOOL-01 Attempt-scoped Duplicate Governance
- Slice: 1 - Typed Policy And Attempt-scoped Duplicate State
- Approved plan: `docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`
- Implementation artifact: `docs/reviews/wu-tool-01-implementation-slice1-codex-20260601.md`
- Review date: 2026-06-01

## Review Target Files

- `dayu/host/tool_duplicate_governance.py`
- `dayu/host/tool_runtime.py`
- `tests/host/test_toolruntime_duplicate_governance.py`
- `docs/reviews/wu-tool-01-implementation-slice1-codex-20260601.md`

## Verification Results

- `pytest tests/host/test_toolruntime_duplicate_governance.py`: **24 passed, 0 failed** ✓
- `pyright dayu/host/tool_duplicate_governance.py dayu/host/tool_runtime.py tests/host/test_toolruntime_duplicate_governance.py`: **0 errors** ✓
- `rg "run-local|run-scoped|RunScoped|RunLocal|同 Run"`: remaining matches are truncation-related (allowed) and `RunScopedDuplicateGovernanceRegistry` / `InMemoryRunScopedDuplicateGovernanceRegistry` (blocking — see findings).

## Overall Verdict

**3 blocking findings, 2 non-blocking findings。**

核心 typed contracts 和 attempt-scoped in-flight 状态机实现正确，测试覆盖并发时序合理。但 `tool_runtime.py` 仍保留 `__all__` re-export 和 run-scoped compatibility class/protocol，违反 plan Slice 1 的明确要求。

---

## Blocking Findings

### 1-BLOCKING-[MEDIUM]-tool_runtime.py `__all__` 仍 re-export 全部 duplicate governance typed contracts

**Evidence:**

`tool_runtime.py:5466-5537` 的 `__all__` 包含以下从 `dayu.host.tool_duplicate_governance` import 的符号：

```
DuplicateAcceptedEntry, DuplicateDecision, DuplicateDecisionKind,
DuplicateDurableMissingReason, DuplicateGovernanceMessages,
DuplicateGovernancePolicy, DuplicateGovernanceRequest,
DuplicateGovernanceScope, InMemoryAttemptDuplicateGovernance
```

Plan §6 明确要求："Do not keep compatibility re-exports in `tool_runtime.py`; callers must import duplicate governance typed contracts from `dayu.host.tool_duplicate_governance`."

测试 `test_toolruntime_duplicate_governance.py:56-60` 已正确从 `dayu.host.tool_duplicate_governance` 导入，但 `__all__` re-export 仍允许外部模块从 `tool_runtime.py` 导入这些类型，破坏单一来源原则。

**Risk:** 外部调用者可以继续从 `tool_runtime.py` 导入，导致迁移不彻底。Slice 2 dispatch 导入路径变更时可能遗漏。

---

### 2-BLOCKING-[MEDIUM]-RunScopedDuplicateGovernanceRegistry 兼容 surface 未删除

**Evidence:**

- `tool_runtime.py:1030-1063` — `RunScopedDuplicateGovernanceRegistry` Protocol 仍定义，含 `duplicate_governance_for_run()` / `clear_run()` / `clear_all()` 方法。
- `tool_runtime.py:1518-1569` — `InMemoryRunScopedDuplicateGovernanceRegistry` class 仍定义，docstring 称"调度器旧装配路径使用的 registry 占位实现"。
- `tool_runtime.py:2056` — `ToolRuntimeBuildRequest.duplicate_governance_registry: RunScopedDuplicateGovernanceRegistry | None = None` 字段保留。
- `dispatch.py:190` — `from dayu.host.tool_runtime import InMemoryRunScopedDuplicateGovernanceRegistry`。
- `dispatch.py:735` — `self._duplicate_governance_registry = InMemoryRunScopedDuplicateGovernanceRegistry()`。

Plan §3 明确要求："不做兼容 re-export / wrapper / facade；旧 run-scoped symbol 和测试必须删除或重命名为 attempt-scoped 真源。" Plan §7 decision 3 要求："Delete `RunScopedDuplicateGovernanceRegistry`, `InMemoryRunScopedDuplicateGovernanceRegistry`, `_RunLocalDuplicateGovernanceState`, and `InMemoryRunLocalDuplicateGovernance` naming."

Implementation artifact 承认这是 residual 并归因于不允许编辑 `dispatch.py`。但 plan Slice 1 allowed files 包含 `tool_runtime.py`，且 plan 要求在 Slice 1 内完成删除。`dispatch.py` 的后续适配是 Slice 2 职责，不应阻塞 `tool_runtime.py` 内的清理。

**Risk:** 旧 Protocol 和 class 继续存在于 `tool_runtime.py`，dispatch 继续使用旧路径，违背 "删除或重命名" 的明确要求。

---

### 3-BLOCKING-[LOW]-DuplicateGovernancePort Protocol 应随 typed contracts 迁移至 tool_duplicate_governance.py

**Evidence:**

- `tool_runtime.py:987-1027` — `DuplicateGovernancePort` async Protocol 仍定义在 `tool_runtime.py`。
- `tool_runtime.py:5478` — `DuplicateGovernancePort` 在 `__all__` 中。
- `tool_duplicate_governance.py` 不导出 `DuplicateGovernancePort`。

Plan §6 contract changes 列出 `DuplicateGovernancePort` 变更为 async Protocol 作为本 slice 内容。该 Protocol 是 duplicate governance capability 的端口契约，其方法签名依赖 `DuplicateGovernanceRequest`、`DuplicateDecision`、`DuplicateAcceptedEntry`、`DuplicateDurableMissingReason` — 全部已在 `tool_duplicate_governance.py`。将 Protocol 留在 `tool_runtime.py` 导致 Protocol 与其依赖类型分属两个模块，且 `RunScopedDuplicateGovernanceRegistry` 对 `DuplicateGovernancePort` 的返回类型引用进一步固化跨模块耦合。

**Risk:** 当 Slice 2 删除 `RunScopedDuplicateGovernanceRegistry` 时，`DuplicateGovernancePort` 的归属仍未确定，可能需要二次迁移。

---

## Non-blocking Findings

### 4-NON-BLOCKING-[LOW]-缺少外部 cancellation token 触发 durable-missing 的并发测试

**Evidence:**

Implementation artifact §Plan Gaps 承认："A direct mutable cancellation-token concurrency test remains a useful review follow-up."

`_execute_one()` 中 `durable_missing_reason` 初始值为 `GOVERNED_BEFORE_ACCEPT`（`tool_runtime.py:2230`），`_durable_missing_reason_for_policy()` 在 `reason_code == _TOOL_RUNTIME_CANCELLED_REASON` 时映射为 `OWNER_CANCELLED`（`tool_runtime.py:4685-4686`）。这条路径的正确性依赖 `_dispatch_tool_call_with_bounds` 在 cancellation 时返回正确的 bounded_policy_decision，但无专门测试覆盖。

当前测试覆盖：accept rejected、accept timeout、tool exception。缺少：外部 cancellation token `is_cancelled()=True` 触发的 owner terminal → waiter durable-missing 完整时序。

---

### 5-NON-BLOCKING-[INFO]-`_duplicate_message()` fallback 使用默认 policy 而非已配置 policy

**Evidence:**

- `tool_runtime.py:4737-4744` — `_duplicate_message()` 创建 `DuplicateGovernanceMessages()` 默认实例。
- `tool_runtime.py:4672` — `_policy_decision_from_duplicate()` 在 `decision.message` 为 `None` 时 fallback 到 `_duplicate_message()`。

实际运行中 `InMemoryAttemptDuplicateGovernance.decide_duplicate()` 始终设置 `decision.message`（从 `self._policy.messages` 读取），所以此 fallback 是 dead code。但如果未来有新的 `DuplicateGovernancePort` 实现不设置 message，fallback 不会使用已配置的 policy messages，而是使用默认值。

---

## Plan Compliance Checklist

| Plan 要求 | 状态 | 备注 |
|---|---|---|
| `DuplicateDecisionKind` / `DuplicateGovernanceScope` / `DuplicateGovernanceRequest` / `DuplicateDecision` / `DuplicateAcceptedEntry` / `DuplicateDurableMissingReason` / `DuplicateGovernanceMessages` / `DuplicateGovernancePolicy` 迁移至 `tool_duplicate_governance.py` | ✓ | 已完成 |
| `InMemoryAttemptDuplicateGovernance` 实现 attempt-local in-flight state machine | ✓ | 已完成 |
| `DuplicateGovernanceScope` 含 `kind: Literal["attempt"]` + `attempt_id: str` + `__post_init__` 校验 | ✓ | 已完成 |
| `DuplicateGovernanceMessages` 含 typed fields + default values + `__post_init__` reject empty | ✓ | 已完成 |
| `DuplicateGovernancePolicy` 含 `messages: DuplicateGovernanceMessages = field(default_factory=...)` | ✓ | 已完成 |
| `DuplicateGovernanceRequest` 含 `scope: DuplicateGovernanceScope` | ✓ | 已完成 |
| `DuplicateDecision` 含 `scope: DuplicateGovernanceScope` + `durable_missing_reason` | ✓ | 已完成 |
| `DuplicateGovernancePort` 改为 async Protocol | ✓ | 已完成 |
| `_duplicate_key()` 包含 `attempt_id`，不包含 `index_in_iteration` | ✓ | 已完成 |
| tool_runtime.py 所有 caller await `decide_duplicate` / `record_accepted` / `record_durable_missing` | ✓ | 已完成 |
| owner terminal handling：accept rejected / timeout / tool exception / governed_before_accept → `record_durable_missing()` | ✓ | `finally` block 覆盖 |
| waiter 观察 durable-missing 后返回 governed failure，不执行第二次真实调用 | ✓ | 已完成 |
| `TOOL_CALL_GOVERNED` payload 含 `duplicate_scope` | ✓ | 已完成 |
| 不删除 `tool_runtime.py` 中 duplicate governance types 的 `__all__` re-export | ✗ | Blocking #1 |
| 不删除 `RunScopedDuplicateGovernanceRegistry` / `InMemoryRunScopedDuplicateGovernanceRegistry` | ✗ | Blocking #2 |
| `DuplicateGovernancePort` 未迁移到 `tool_duplicate_governance.py` | ✗ | Blocking #3 |
| 无 `Any` / `object` / 无类型签名 | ✓ | 已完成 |
| 完整中文 docstring | ✓ | 已完成 |
| 无 magic strings（schema 例外） | ✓ | 已完成 |
| 测试覆盖 attempt_id in key | ✓ | `test_duplicate_key_includes_attempt_id` |
| 测试覆盖并发 reuse 等待 owner accept | ✓ | `test_same_attempt_concurrent_reuse_waits_for_owner_accept` |
| 测试覆盖并发 accept rejected → durable-missing | ✓ | `test_same_attempt_concurrent_rejected_accept_reports_durable_missing` |
| 测试覆盖并发 accept timeout → durable-missing | ✓ | `test_same_attempt_concurrent_timed_out_accept_reports_durable_missing` |
| 测试覆盖并发 tool exception → durable-missing | ✓ | `test_same_attempt_concurrent_tool_exception_reports_durable_missing` |
| 测试覆盖 allow policy 并发等待 owner 后二次执行 | ✓ | `test_allow_policy_concurrent_waits_for_owner_before_second_execution` |
| 测试覆盖 allow policy owner 完成后再次执行 | ✓ | `test_allow_policy_post_owner_completion_executes_again` |
| 测试覆盖 messages reject empty | ✓ | `test_duplicate_governance_messages_reject_empty_text` |

## Concurrency Correctness Assessment

In-flight 状态机实现正确：

1. **Locking boundary**: `asyncio.Condition` 仅保护 claim creation、state reads/writes、terminal updates、waiter notification。tool callable 执行和 Host accept 在 lock 外。✓
2. **Owner/Waiter lifecycle**: owner 获取 `OWNER_RUNNING` 状态后执行真实调用；waiter 在 `condition.wait()` 中阻塞直到 terminal state。✓
3. **Terminal state**: `record_accepted()` 设置 `ACCEPTED` + `notify_all()`；`record_durable_missing()` 设置 `DURABLE_MISSING` + `notify_all()`。两者都 pop in-flight map entry。✓
4. **Post-terminal new caller**: map entry pop 后，新 caller 看不到 in-flight record，获得 fresh `ALLOW`，成为新 owner。✓
5. **Waiter reference safety**: waiter 持有 `_InFlightDuplicateRecord` 对象引用（非 map entry），pop 不影响已阻塞 waiter 的唤醒。✓
6. **Finally block**: `duplicate_owner_needs_terminal` 在 `ALLOW` + 无 `prior_event_refs` 时为 True；`finally` 中调用 `record_durable_missing()` 确保 waiter 不被永久阻塞。✓

## Conclusion

Slice 1 的 typed contracts、attempt-scoped key、in-flight 状态机和并发测试实现正确且完整。3 个 blocking findings 均涉及 `tool_runtime.py` 内残留的旧 run-scoped compatibility surface（`__all__` re-export、Protocol/class 定义、build request 字段），违反 plan 的明确要求。这些残留可由 worker 在当前 slice 内修复，无需等待 Slice 2。
