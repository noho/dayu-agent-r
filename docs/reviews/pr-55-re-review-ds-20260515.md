# PR 55 Re-Review — AgentDS (PR55-DS-1 Fix)

- **Review type**: 定向重审（仅 PR55-DS-1 修复及回归）
- **Review date**: 2026-05-15
- **Repository**: noho/dayu-agent-r
- **PR**: [#55](https://github.com/noho/dayu-agent-r/pull/55)
- **Fix commit**: `c79d6b8` — fix: handle ToolRuntime accept retry exhaustion
- **Prior review**: `docs/reviews/pr-55-deepreview-ds-20260515.md` (PASS, 2 medium, 5 low)
- **Controller adjudication**: `docs/reviews/pr-55-deepreview-controller-adjudication-20260515.md` (PR55-DS-1 accepted for fix)
- **Fix artifact**: `docs/reviews/pr-55-fix-accept-retry-exhausted-20260515.md`
- **Verdict**: PASS — 修复正确，无回归，无新发现

## Scope

### Fix delta

| File | Change |
|------|--------|
| `dayu/host/tool_runtime.py` | +2 lines: 新增 `HostTransactionRetryExhaustedError` import (line 60)，`except TimeoutError` 扩展为 `except (HostTransactionRetryExhaustedError, TimeoutError)` (line 2471) |
| `tests/host/test_toolruntime_executor.py` | +51 lines: 新增 `_RetryExhaustedAcceptPort` 假端口与 `test_accept_retry_exhausted_returns_governed_timeout` 测试 |
| `docs/reviews/` | +4 files: DS/MiMo PR review artifacts, controller adjudication, fix artifact |

### Verification baseline (controller post-fix)

| Item | Result |
|------|--------|
| `pytest tests/host/test_toolruntime_executor.py -q` | 8 passed |
| `pytest tests/host -q` | 350 passed |
| `python -m pyright dayu/host/tool_runtime.py tests/host/test_toolruntime_executor.py` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean |

---

## Findings

### 已修复确认 — PR55-DS-1 — HostTransactionRetryExhaustedError 被正确捕获并转换为有界 ToolFactAcceptTimedOut

**修复轨迹**:

1. **Import**: `dayu/host/tool_runtime.py:60` — `HostTransactionRetryExhaustedError` 从 `dayu.host.durable.errors` 导入。此异常是 `HostDurableError` 的直接子类（非 `TimeoutError`），在 SQLite busy/locked 重试耗尽时抛出。

2. **Catch 扩展**: `dayu/host/tool_runtime.py:2471` — `except TimeoutError:` → `except (HostTransactionRetryExhaustedError, TimeoutError):`。两行生产代码变更。

3. **Catch 范围确认 — 刻意收窄**: `except` 子句**不含** `HostDurableError`（已导入但未在此路径中捕获）。其他 durable 错误（`HostIdempotencyConflictError`、`HostPayloadReferenceError`、事务内 schema/data/payload/foreign-key 错误）不在捕获范围内，仍会向上传播为 implementation defect。符合 controller adjudication 要求的 "不得捕获宽泛 HostDurableError"。

4. **有界重试转换路径**（逐行验证）:
   - `tool_runtime.py:2467-2471`: 进入 retry loop，`accept_tool_fact` 抛出 `HostTransactionRetryExhaustedError`
   - `tool_runtime.py:2471`: 被 `except (HostTransactionRetryExhaustedError, TimeoutError)` 捕获
   - `tool_runtime.py:2472-2477`: 构造 `ToolFactAcceptTimedOut(attempt_count=...)` 并继续 retry loop
   - `tool_runtime.py:2490`: 当 `attempt_count >= max_attempts` 时 `break`
   - `tool_runtime.py:2494-2504`: 回落路径返回最终 `ToolFactAcceptTimedOut`（含诊断 ref）
   - `tool_runtime.py:2305-2321` (`_execute_one`): `accept_result` 为 `ToolFactAcceptTimedOut`，不被 `ToolFactAcceptedAck` 匹配，落入 line 2318 `_accept_failure_outcome(accept_result)`
   - `_accept_failure_outcome` 将定时输出转换为 `ToolFailedOutcome` 且 `error="tool_accept_timeout"`
   - 结论：异常在 retry loop 内部被捕获，作为定时输出进行重试，并在 `max_attempts` 耗尽后转为 governed error，**不会**穿透并导致工具执行崩溃。

5. **新测试验证**（`tests/host/test_toolruntime_executor.py:299-318`）:
   - `_RetryExhaustedAcceptPort` (line 193-218): 假端口始终抛出 `HostTransactionRetryExhaustedError`
   - 使用 `ToolAcceptRetryPolicy(max_attempts=2, backoff_seconds=0.0)` 配置 executor
   - 断言:
     - `callable_.call_count == 1` — callable 执行了（产生了原始结果）
     - `len(accept_port.candidates) == 2` — retry 次数与 `max_attempts` 一致
     - `isinstance(record.outcome, ToolFailedOutcome)` — 返回给 Engine 的是治理后错误
     - `record.outcome.result.error == "tool_accept_timeout"` — 错误码正确
     - `"retry-exhausted-raw" not in record.outcome.result.message` — 原始工具结果未泄露
   - 该测试在结构上与此前已有的测试镜像对齐：`test_accept_timeout_bounded_retry_returns_governed_error` (line 265) 验证显式 `ToolFactAcceptTimedOut` 返回，`test_accept_rejected_does_not_expose_raw_fake_result` (line 239) 验证拒绝不泄露原始结果。新测试完全证明了异常传播的转换。

### 无回归

- **类型**: 新增 import 为标准库类型（来自 `dayu.host.durable.errors`），无 `Any`/`object` 新增。pyright clean。
- **测试**: 350 项 Host 测试通过（从 349 增至 350，新增测试被计入）。
- **文档**: 修复范围极窄（两行生产代码），无需触发 README 更新规则。
- **架构边界**: 未触及分层、导入方向或模块职责边界。

---

## Open Questions

无。

---

## Residual Risks

1. **`ToolFactRejectedAck.retryable` 语义仍未实现**（已在上一轮记录为 PR55-DS-7）——本次修复未涉及。当前生产环境排队的被拒绝 ack 均为不可重试，因此无行为差异。此项已推迟至 ToolRuntime 强化阶段。

2. **修复未处理更通用的重试耗尽情况**（例如：工具执行的事务死锁，而非 accept 事物）。本次修复仅限缩于 `_accept_with_retry` 内的 accept barrier 边界。工具调度派发阶段的 durable 错误（`ToolDispatcher.dispatch_tool_call`）仍会传播。因 accept barrier 是 SQLite 竞争的主要来源（同步事务内的多次写入），这是一个合理的范围。

---

## 最终裁决

**PASS**

PR55-DS-1 已修复。`_accept_with_retry` 现在能将 `HostTransactionRetryExhaustedError` 转换为有界 `ToolFactAcceptTimedOut`，后者通过 `_execute_one` 中的现有流程被治理为 `tool_accept_timeout` 并返回给 Engine。修复范围非常局限（两行生产代码），刻意收窄（不含宽泛 `HostDurableError`），且经过测试证明：原始工具结果不泄露，重试次数符合 `ToolAcceptRetryPolicy`，最终结果是受治理的错误。未引入回归：350 项测试通过，pyright clean，无架构边界变更。
