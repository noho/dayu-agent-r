# WU-TOOL-01 Slice 2 Code Review — DeepSeek

## 元数据

- **Review type**: Code review (implementation slice)
- **Reviewer**: DeepSeek
- **Reviewed branch**: `fix/wu-tool-01-attempt-scoped-duplicate-governance`
- **Design source**: `docs/host/design.md`
- **Control doc**: `docs/host/host-core-followup-implementation-control.md`
- **Approved plan**: `docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`
- **Accepted Slice 1 commit**: `bd782be`
- **Reviewed files**:
  - `dayu/host/tooling.py`
  - `dayu/host/dispatch.py`
  - `tests/host/test_tooling_options.py`
  - `tests/host/test_dispatch_scheduler.py`
  - `docs/reviews/wu-tool-01-implementation-slice2-codex-20260601.md`

---

## Findings

### F1 — `test_host_tooling_options_rejects_invalid_duplicate_policy_type` 使用 `cast` 绕过类型检查

**Severity**: Non-blocking / acceptable in test code

**Location**: `tests/host/test_tooling_options.py:317-328`

**Details**:

```python
duplicate_governance_policy=cast(
    DuplicateGovernancePolicy,
    "invalid-policy",
),
```

测试使用 `cast` 将字符串 `"invalid-policy"` 伪装成 `DuplicateGovernancePolicy` 类型以触发 `__post_init__` 中的 `isinstance` 校验。这是测试中故意传入非法类型的标准做法，`cast` 仅用于满足类型检查器，不违反 AGENTS.md 对生产代码的约束。

**Verdict**: Acceptable。`cast` 仅出现在测试辅助输入构造中，用于刻意绕过类型系统以验证运行时校验行为，不属于"以 cast 逃避类型边界设计"。

---

### F2 — `_tooling_options` 测试 helper 的 `duplicate_governance_policy` 参数默认逻辑

**Severity**: Info

**Location**: `tests/host/test_dispatch_scheduler.py:4330-4355`

**Details**:

```python
duplicate_governance_policy=(
    duplicate_governance_policy
    if duplicate_governance_policy is not None
    else DuplicateGovernancePolicy()
),
```

测试 helper `_tooling_options` 在 `duplicate_governance_policy=None` 时使用 `DuplicateGovernancePolicy()` 作为默认值。这与 `HostToolingOptions.duplicate_governance_policy` 的 `default_factory=DuplicateGovernancePolicy` 一致，不会产生语义偏差。

**Verdict**: Acceptable。虽然 `HostToolingOptions` 已有 `default_factory`，但 helper 显式构造默认值确保测试中 policy 可控、可追溯，优于依赖 dataclass default factory 的隐式行为。

---

### F3 — `tool_runtime.py` 中 `duplicate_governance_key as _duplicate_key` 别名

**Severity**: Info

**Location**: `dayu/host/tool_runtime.py:131`

**Details**:

```python
from dayu.host.tool_duplicate_governance import (
    ...
    duplicate_governance_key as _duplicate_key,
)
```

`duplicate_governance_key` 函数定义在 `dayu/host/tool_duplicate_governance.py:553`，在 `tool_runtime.py` 中以 `_duplicate_key` 作为私有别名导入。这不是兼容性 re-export——`__all__` 中不包含该符号，外部模块应直接从 `tool_duplicate_governance` 导入。

**Verdict**: Acceptable。私有别名属于模块级便利用法，不构成兼容性包装。

---

### F4 — `dispatch.py` 不直接 import `DuplicateGovernancePolicy`，通过 `tooling_options` 间接获取

**Severity**: Info

**Location**: `dayu/host/dispatch.py:2645,2692-2694`

**Details**:

Dispatch 代码不直接导入 `DuplicateGovernancePolicy`，而是通过 `self._local_execution.tooling_options`（类型为 `HostToolingOptions | None`）的 `.duplicate_governance_policy` 属性获取 policy 后传入 `ToolRuntimeBuildRequest`。导入链为：

```
HostLocalExecutionOptions.tooling_options: HostToolingOptions | None
  → HostToolingOptions.duplicate_governance_policy: DuplicateGovernancePolicy
    → ToolRuntimeBuildRequest.duplicate_governance_policy
      → InMemoryAttemptDuplicateGovernance(policy)
```

这是正确的分层数据流——dispatch 不关心 policy 的实现细节，只负责传递 typed policy。无需在 `dispatch.py` 中直接导入 `DuplicateGovernancePolicy`。

**Verdict**: Acceptable。符合 SOLID 原则，dispatch 作为编排层不应直接依赖 duplicate governance 的具体类型。

---

### F5 — `test_reactive_recovery_uses_fresh_duplicate_governance_attempt` 的跨 Attempt 验证

**Severity**: Non-blocking / 设计澄清

**Location**: `tests/host/test_dispatch_scheduler.py:4079-4175`

**Details**:

该测试通过 dispatch + reactive recovery 集成路径证明：
1. 同一 Attempt 内：REUSE policy 下同 tool/args 的第二次调用复用第一次结果（`tool.call_count == 1`，line 4147）
2. Reactive recovery 产生新 Attempt：`accepted_snapshots[0].attempt_id != accepted_snapshots[1].attempt_id`（line 4167）
3. 新 Attempt 中同 tool/args 作为 fresh request 执行（`tool.call_count == 2`，line 4172）

测试访问的是两个不同的 `AgentRunRequest.tool_executor`（分别属于 Attempt 1 和 Attempt 2 的 ToolRuntime），而非"两个 executor 实例"的误比较。这是因为每个 Attempt dispatch 会通过 `ToolRuntimeBuildRequest` 创建独立的 ToolRuntime handle，其中包含独立的 `InMemoryAttemptDuplicateGovernance`。

review brief 中"不是只测了两个 executor 实例"的关切已满足——测试通过 dispatch → reactive recovery → 第二次 accept 的完整路径验证跨 Attempt 不继承，直接证明了 ToolRuntime 的 attempt-scoped 边界。

**Verdict**: Acceptable。测试是行为验证而非实现细节断言。

---

### F6 — 残留旧术语检查

**Severity**: Verified clean

**Details**:

`dispatch.py` 中无 `_duplicate_governance_registry`、`InMemoryRunScopedDuplicateGovernanceRegistry`、`clear_all`、`clear_run`、`RunScoped`、`run-scoped`、`RunLocal`、`run-local` 残留。

`tool_runtime.py` 中仍有 `run-scoped` 出现，但全部属于 truncation / `fetch_more` cursor 相关（`ToolTruncationCursor`、`TruncationManager`、`enable_truncation_manager`），不属于 duplicate governance 语义。plan 明确允许该类文案保留。

`test_dispatch_scheduler.py` 中 close lifecycle matrix（lines 195-252）的 6 个场景均不涉及 duplicate registry cleanup。已删除场景中 `expected_resource_cleanup` 的描述均对应 active worker registry / lane controller / active handles / active tasks 清理，而非 duplicate registry。

`tests/host/test_toolruntime_duplicate_governance.py` 中无 `RunScoped` / `run-scoped` / `RunLocal` / `run-local` / `同 Run` / `同Run` 残留。

**Verdict**: Clean。仅 truncation 相关文案合法保留。

---

### F7 — AGENTS.md 合规检查

**Severity**: Verified compliant

| 检查项 | 状态 | 证据 |
|---|---|---|
| 中文 docstring（参数/返回值/异常） | ✅ | `tooling.py:71-116`，`tool_duplicate_governance.py` 全部导出类/函数 |
| 禁止 `Any`/`object`/无类型签名 | ✅ | 所有新代码使用具体类型注解 |
| 禁止 lazy import | ✅ | `tooling.py:17` 直接 import，无 TYPE_CHECKING 条件导入 duplicate governance |
| 禁止兼容性 re-export/wrapper | ✅ | `HostToolingOptions` 不从 tool_runtime 重导出 `DuplicateGovernancePolicy` |
| 禁止 god object/function/dataclass | ✅ | `DuplicateGovernancePolicy` 只含 policy 字段；`DuplicateGovernanceMessages` 只含消息字段 |
| 分层架构 | ✅ | `duplicate_governance_policy` 沿 `HostToolingOptions → ToolRuntimeBuildRequest → InMemoryAttemptDuplicateGovernance` 传递，不反向依赖 |
| 测试覆盖 | ✅ | 70 passed（test_tooling_options.py 13 + test_dispatch_scheduler.py 57） |
| pyright | ✅ | 0 errors, 0 warnings, 0 informations |
| README 决策 | ✅ | 按 approved plan 推迟到 Slice 4；README 未受本次变更影响 |

**唯一注意点**: `_require_non_empty_text` 等三个私有 validator 函数（`tool_duplicate_governance.py:574-612`）位于 `tool_duplicate_governance.py` 中且未标注 `__all__`，仅作为模块内辅助。它们符合"模块级私有辅助函数优先"规范，无问题。

---

### F8 — `dispatch.py` 中 `_run_input_builder_for_attempt` 每 Attempt 构造独立 `ToolRuntimeBuildRequest`

**Severity**: Verified correct

**Location**: `dayu/host/dispatch.py:2665-2696`

**Details**:

```python
tool_runtime = DefaultToolRuntimeFactory(...).create_tool_runtime(
    ToolRuntimeBuildRequest(
        ...
        execution_scope=ToolRuntimeExecutionScope(
            ...
            attempt_id=snapshot.attempt_id,
            ...
        ),
        ...
        duplicate_governance_policy=(
            tooling_options.duplicate_governance_policy
        ),
    )
)
```

每次调用 `_run_input_builder_for_attempt` 都构造新的 `ToolRuntimeBuildRequest`，其中 `execution_scope.attempt_id` 来自当前 snapshot，`duplicate_governance_policy` 从 `tooling_options` 传入。`DefaultToolRuntimeFactory.create_tool_runtime()` 为每个 request 创建独立的 `InMemoryAttemptDuplicateGovernance(policy)` 实例（`tool_runtime.py:2756-2757`），天然保证跨 Attempt 不共享状态。

**Verdict**: Correct。无需额外的 per-run 清理逻辑或 registry 管理。

---

### F9 — `tooling.py` 中 `__post_init__` 的 policy 类型校验方式

**Severity**: Info

**Location**: `dayu/host/tooling.py:101-107`

**Details**:

```python
if not isinstance(
    self.duplicate_governance_policy, DuplicateGovernancePolicy
):
    raise ValueError(...)
```

由于 `HostToolingOptions` 是 frozen dataclass，而 `default_factory=DuplicateGovernancePolicy` 在正常情况下保证类型正确，该 `isinstance` 校验主要防范通过 `object.__setattr__` 或测试中 `cast` 注入非法值。这是防御性校验，合理。

**Verdict**: Acceptable。防御性校验不增加运行时开销，提供显式错误信息。

---

## Open Questions

**OQ-1**: `test_host_tooling_options_rejects_invalid_duplicate_policy_type` 的 `cast(DuplicateGovernancePolicy, "invalid-policy")` 是否需要在 future 改为 `pytest.raises` 内直接使用 `unsafe_hash` 或 dataclass field 绕过？当前做法是测试标准实践，不建议为了消除 `cast` 而过度设计测试构造。

**Answer**: 不需要。`cast` 在测试中用于刻意突破类型检查以验证运行时校验，不违反"禁止以 cast 逃避类型设计"的 AGENTS.md 约束。

**OQ-2**: `_tooling_options` test helper 的 `duplicate_governance_policy` 参数和 `HostToolingOptions` 本身的 `default_factory` 是否存在双重默认风险？如果未来 default_factory 逻辑变化，测试 helper 可能产生与生产代码不一致的默认行为。

**Answer**: 当前 helper 显式调用 `DuplicateGovernancePolicy()` 和 `HostToolingOptions` 的 `default_factory` 行为一致。这是一个微小的维护风险（DRY 违规），但不是 correctness 风险。可作为低优先级的 helper 重构放在 WU-LAYER-02 或将来统一 helper 收敛中处理。

---

## Verification

| 验证项 | 命令 | 结果 |
|---|---|---|
| 单元测试 | `pytest tests/host/test_tooling_options.py tests/host/test_dispatch_scheduler.py` | 70 passed |
| 类型检查 | `pyright` | 0 errors, 0 warnings, 0 informations |
| 旧 registry 残留 | `rg "RunScoped\|run.scoped\|RunLocal\|run.local" dayu/host/dispatch.py` | 0 matches |
| 旧 registry 残留 (tests) | `rg "RunScoped\|run.scoped\|RunLocal\|run.local" tests/host/test_dispatch_scheduler.py` | 0 matches |
| dispatch 旧清理 | `rg "clear_all\|clear_run\|_duplicate_governance_registry\|InMemoryRunScoped" dayu/host/dispatch.py` | 0 matches |
| lazy import | `rg -i "lazy" dayu/host/tooling.py dayu/host/dispatch.py` | 0 matches |
| 兼容 re-export | `rg "duplicate_governance" dayu/host/__init__.py` | 0 matches |

---

## Conclusion

### Remaining blocking findings: 0

Slice 2 实现满足 approved plan 中的所有验收信号：

1. **HostToolingOptions 暴露 typed duplicate_governance_policy**（F4, F9）：✅ 从 `dayu.host.tool_duplicate_governance` 直接导入，无 lazy import，无兼容 re-export。
2. **Dispatch 传入每个 per-Attempt ToolRuntimeBuildRequest**（F8）：✅ 每次构造独立的 `ToolRuntimeBuildRequest`，policy 从 `tooling_options.duplicate_governance_policy` 传入，factory 为每个 Attempt 创建独立的 `InMemoryAttemptDuplicateGovernance`。
3. **Reactive recovery 测试证明新 Attempt 不继承 duplicate index**（F5）：✅ 测试通过 dispatch → reactive recovery 集成路径证明跨 Attempt 同 tool/args 作为 fresh request 执行（`call_count == 2`）。
4. **Custom message / justification 参数名 / 空 message 与空 argument name validation 测试**（F1, F2, F7）：✅ 覆盖：默认消息非空、custom message 透传、custom justification 参数名、空消息拒绝、空 argument name 拒绝、非法 policy 类型拒绝。
5. **旧术语残留**（F6）：✅ dispatch.py 和 test_dispatch_scheduler.py 中无 duplicate governance 的 run-scoped/run-local 残留；tool_runtime.py 中残留文案均为 truncation 相关，合法。
6. **AGENTS.md 合规**（F7）：✅ 全部通过：中文 docstring、无 Any/object、无 lazy import、无兼容 wrapper、分层正确、测试/pyright/README 决策 complete。

无 blocking finding。所有 findings 均为 non-blocking 或 info 级别。

### 下一 slice 入口

Slice 3: Governed Event / Diagnostic / Trace Scope（`TOOL_CALL_GOVERNED` payload 增加 `duplicate_scope`，tool trace summary 同步）。
