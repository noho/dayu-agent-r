# Re-Review — WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch C1 Review-Fix

## Scope

- Mode: re-review of review-fix
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD` (workspace changes)
- Re-reviewing agent: AgentMiMo
- Input artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-code-review-ds.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-code-review-controller-adjudication.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-review-fix-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-review-fix-controller-validation.md`
- Output file: `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-rereview-mimo.md`

## Accepted Findings Under Re-Review

| Finding | Description | Severity |
| --- | --- | --- |
| `DS-C1-01` | boundary rejection must have explicit durable outcome/counter and must not increment adapter_errors | 中 |
| `C1-REVIEW-01` | unreachable STALE_CALLBACK public status and Service mapping removed | 低 |
| `DS-C1-02` | self-close uses typed internal exception, not RuntimeError message matching | 低 |
| `C1-REVIEW-02` / `DS-C1-03` | recoverable round_errors separated from fatal_errors | 低 |

## Finding-by-Finding Verification

### DS-C1-01: boundary rejection outcome/counter — ✅ CLOSED

**要求**: 持久化 `poll_last_outcome` 使用独立的 boundary-rejection 语义值；新增独立计数器；`adapter_errors` 不再计入边界拒绝。

**代码验证**:

| 检查项 | 文件(行号) | 结果 |
| --- | --- | --- |
| `WaitPollLastOutcome.BOUNDARY_REJECTED` 枚举值存在 | `dayu/host/durable/state.py:197` | ✅ |
| schema CHECK 约束包含 `boundary_rejected` | `dayu/host/durable/schema.py:863` | ✅ |
| `_release_expired_or_invalid_boundary` 使用 `BOUNDARY_REJECTED` | `dayu/host/wait_adapter.py:1220` | ✅ |
| `poll_once` 新增 `boundary_rejections` 独立计数器 | `dayu/host/wait_adapter.py:908,931` | ✅ |
| 边界拒绝不再递增 `adapter_errors` | `dayu/host/wait_adapter.py:927-933` | ✅ |
| `WaitPollOnceResult` 包含 `boundary_rejections` 字段 | `dayu/host/wait_adapter.py:445` | ✅ |
| `WaitPollerDiagnosticsSnapshot` 包含 `boundary_rejections` 字段 | `dayu/host/wait_adapter.py:490` | ✅ |
| diagnostics 累加函数正确传递 `boundary_rejections` | `dayu/host/wait_adapter.py:1833-1835` | ✅ |
| `BOUNDARY_REJECTED` codec round-trip 测试 | `tests/host/test_wait_record_state.py:420-427` | ✅ |

**测试验证**:

| 测试 | 关键断言 | 结果 |
| --- | --- | --- |
| `test_expired_poll_wait_is_released_before_provider_observation` | `adapter_errors == 0`, `boundary_rejections == 1`, `poll_last_outcome is BOUNDARY_REJECTED` | ✅ |
| `test_invalid_poll_deadline_fails_closed_without_business_lost` | `adapter_errors == 0`, `boundary_rejections == 1`, `poll_last_outcome is BOUNDARY_REJECTED` | ✅ |

**结论**: 持久化 outcome 和 poll 计数器均正确表达 Host 边界拒绝语义，`adapter_errors` 不再被边界拒绝污染。finding 关闭。

---

### C1-REVIEW-01: STALE_CALLBACK 枚举和 Service mapping — ✅ CLOSED

**要求**: 从 `WaitCallbackAdapterStatus` 删除不可达的 `STALE_CALLBACK`；删除 Service HTTP mapping。

**代码验证**:

| 检查项 | 文件(行号) | 结果 |
| --- | --- | --- |
| `WaitCallbackAdapterStatus` 不含 `STALE_CALLBACK` | `dayu/host/wait_callback.py:35-52` | ✅ |
| Service endpoint mapper 不含 `STALE_CALLBACK` 映射 | `dayu/service/wait_callback_endpoint.py:726-753` | ✅ |
| 全局 grep 无 `STALE_CALLBACK` 生产代码引用 | 全仓库 `.py` 排除 test | ✅ |

**测试验证**:

| 测试 | 结果 |
| --- | --- |
| `tests/service/test_wait_callback_endpoint.py` 无 `STALE_CALLBACK` 引用 | ✅ |

**结论**: `STALE_CALLBACK` 已从枚举、endpoint mapper 和全部生产代码中彻底移除。finding 关闭。

---

### DS-C1-02: self-close typed exception — ✅ CLOSED

**要求**: 用 typed exception 替代 `RuntimeError` 字符串匹配。

**代码验证**:

| 检查项 | 文件(行号) | 结果 |
| --- | --- | --- |
| `_WaitPollerSelfCloseError(RuntimeError)` 类定义存在 | `dayu/host/wait_adapter.py:87-88` | ✅ |
| `close()` raise `_WaitPollerSelfCloseError` | `dayu/host/wait_adapter.py:1468` | ✅ |
| `_run_loop` catch `_WaitPollerSelfCloseError` by type | `dayu/host/wait_adapter.py:1538` | ✅ |
| `_WAIT_POLLER_SELF_CLOSE_MESSAGE` 仅用于 raise 点，不用于 catch | `dayu/host/wait_adapter.py:82-84,1468` | ✅ |

**测试验证**:

| 测试 | 关键断言 | 结果 |
| --- | --- | --- |
| `test_close_from_supervisor_thread_marks_failed_diagnostics` | `last_error_type == "_WaitPollerSelfCloseError"`, `fatal_errors == 1` | ✅ |

**结论**: self-close 控制流信号已从字符串匹配迁移到 typed exception 分发。finding 关闭。

---

### C1-REVIEW-02 / DS-C1-03: round_errors 与 fatal_errors 分离 — ✅ CLOSED

**要求**: 新增 `round_errors` 计数器专用于可恢复轮次异常；`fatal_errors` 仅用于 terminal supervisor failure。

**代码验证**:

| 检查项 | 文件(行号) | 结果 |
| --- | --- | --- |
| `WaitPollerDiagnosticsSnapshot` 包含 `round_errors` 字段 | `dayu/host/wait_adapter.py:494` | ✅ |
| `_diagnostics_with_round_error` 递增 `round_errors`，保持 `fatal_errors` 不变 | `dayu/host/wait_adapter.py:1928-1929` | ✅ |
| `_diagnostics_with_fatal_error` 递增 `fatal_errors`，保持 `round_errors` 不变 | `dayu/host/wait_adapter.py:1898-1899` | ✅ |
| `_diagnostics_with_fatal_error` 设 status 为 `FAILED` | `dayu/host/wait_adapter.py:1886` | ✅ |
| `_diagnostics_with_round_error` 保持 status 不变 | `dayu/host/wait_adapter.py:1916` | ✅ |

**测试验证**:

| 测试 | 关键断言 | 结果 |
| --- | --- | --- |
| `test_single_round_exception_is_diagnosed_and_next_round_continues` | `round_errors == 1`, `fatal_errors == 0`, `status is RUNNING` | ✅ |
| `test_close_from_supervisor_thread_marks_failed_diagnostics` | `fatal_errors == 1`, `round_errors == 0`, `status is FAILED` | ✅ |

**结论**: 可恢复轮次异常和不可恢复 fatal 异常使用独立计数器，语义清晰分离。finding 关闭。

---

## 新引入问题检查

逐项检查 review-fix 变更是否引入新问题：

| 检查项 | 结果 |
| --- | --- |
| 新增枚举值 `BOUNDARY_REJECTED` 是否破坏 schema CHECK 约束兼容性 | ✅ 无问题 — schema CHECK 已同步更新包含 `boundary_rejected` |
| `boundary_rejections` 字段在 diagnostics 累加链路中是否完整传递 | ✅ — `_diagnostics_with_poll_result` 和 `_diagnostics_with_initial` 均包含 |
| `_WaitPollerSelfCloseError` 是否影响 `_run_loop` 中其它 `RuntimeError` 的 catch 逻辑 | ✅ 无问题 — `_run_loop` 中非 self-close 的 `Exception` 仍走 round error 路径 |
| `round_errors` 新增字段是否破坏 `WaitPollerDiagnosticsSnapshot` 构造 | ✅ 无问题 — 所有构造点已同步更新 |
| Service endpoint 删除 `STALE_CALLBACK` mapping 是否影响现有 4xx/5xx 路由 | ✅ 无问题 — `STALE_CALLBACK` 从未被生产代码产出，删除不可达分支不影响路由 |
| README 更新是否准确反映 owner 边界变更 | ✅ — `dayu/host/README.md` 和 `tests/README.md` 已更新 |

未发现新引入问题。

---

## Residual Risk

1. **过期 wait 无限 WAITING**: 过期 wait 永不自动进入终态，backoff 无限增长。这是产品策略层面的已知限制，非 review-fix 引入，与本次 fix 无关。
2. **abandon CAS_LOST 并发场景测试 gap**: claim 已被其他 poller 抢占的并发场景缺少显式回归测试。非 review-fix 引入。
3. **Batch C2 未覆盖**: dispatch、promotion、cancel predispatch、tool accept duplicate index、Engine retry 不在 C1 范围内。

## Conclusion

- **conclusion**: 全部 4 个 accepted findings 均已正确关闭。DS-C1-01 通过 `BOUNDARY_REJECTED` 枚举 + `boundary_rejections` 独立计数器彻底分离边界拒绝与 adapter 错误语义；C1-REVIEW-01 通过删除 `STALE_CALLBACK` 枚举和 Service mapping 消除不可达公共契约；DS-C1-02 通过 `_WaitPollerSelfCloseError` typed exception 消除字符串匹配脆弱性；C1-REVIEW-02/DS-C1-03 通过 `round_errors` 与 `fatal_errors` 分离实现可恢复/不可恢复异常的清晰诊断区分。测试断言均精确验证 owner 级 contract 行为。未发现新引入问题。
- **findings count**: 0（未发现新问题）
- **accepted findings closed**: 4/4
- **artifact**: `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-rereview-mimo.md`
- **residual risk**: 过期 wait 无限 WAITING（产品策略）、abandon CAS_LOST 并发测试 gap、Batch C2 未覆盖
- **no code changes confirmation**: 本次 re-review 未修改任何代码。仅产出 review artifact。
