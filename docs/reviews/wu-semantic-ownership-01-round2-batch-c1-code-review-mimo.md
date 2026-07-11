# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD` (workspace changes against current HEAD)
- Output file: `docs/reviews/wu-semantic-ownership-01-round2-batch-c1-code-review-mimo.md`
- Included scope:
  - `dayu/host/wait_boundary.py` (new file)
  - `dayu/host/waiting.py`
  - `dayu/host/wait_adapter.py`
  - `dayu/host/wait_callback.py`
  - `dayu/fins/ingestion/wait_adapter.py`
  - `tests/host/test_resolve_wait_command.py`
  - `tests/host/test_wait_callback.py`
  - `tests/host/test_wait_adapter_polling.py`
  - `tests/host/test_wait_poller_runtime.py`
  - `tests/fins/test_fins_ingestion_tools.py`
- Excluded scope: Batch C2 (dispatch, promotion, cancel predispatch, tool accept duplicate index, Engine retry).
- Parallel review coverage: 无。

## Review Context

- 批次: `WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch C1` — Host wait expiry / supervisor / claim-release / EventLogStore DI。
- Accepted findings under review:
  - `144159-01` / `145711-12` wait deadline/expiry owner drift.
  - `150304-01` WaitPollerSupervisor single transient exception should not permanently fail service.
  - `150304-02` `_resolve_claimed_wait` recovery read-back failure should not crash supervisor.
  - `150304-22` `_abandon_cancelled_wait` CAS_LOST should release current claim.
  - `150304-23` `waiting.py` EventLogStore DI bypass.

## Findings

### C1-REVIEW-01-未修复-低-`WaitCallbackAdapterStatus.STALE_CALLBACK` 枚举值成为不可达的公共导出

- **入口/函数**: `dayu/host/wait_callback.py` `WaitCallbackAdapterStatus` 枚举。
- **文件(行号)**: `dayu/host/wait_callback.py:49`
- **输入场景**: 任何 callback 请求经过 `DefaultWaitCallbackAdapter.resolve_callback`。
- **实际分支**: `_stale_status_or_none` 函数已被完全删除；callback 不再解析 `deadline_at` / `expires_at`；过期边界现在由 `resolve_wait` owner 处理并返回 `INVALID_WAIT_STATE`。
- **预期行为**: 若 `STALE_CALLBACK` 不再是 callback adapter 可产出的状态，公共枚举不应继续导出该值，避免下游消费者误判。
- **实际行为**: `STALE_CALLBACK = "stale_callback"` 仍作为 `WaitCallbackAdapterStatus` 公共枚举成员导出，但无任何生产代码路径可以产出该状态。
- **直接证据**: `dayu/host/wait_callback.py:49` 定义 `STALE_CALLBACK`；`git diff` 确认 `_stale_status_or_none` 已被删除，该函数是唯一产出 `STALE_CALLBACK` 的路径。
- **影响**: 下游消费者可能仍在检查 `STALE_CALLBACK` 并执行过期特定逻辑，但该分支将永远不可达。不会导致运行时错误，但会误导 API 消费者。
- **建议改法和验证点**: 从 `WaitCallbackAdapterStatus` 删除 `STALE_CALLBACK`；检查是否有消费者依赖该值。若作为公共契约需要保留语义区分，应由 owner 层提供 typed rejection reason，不应在 callback 层保留不可达枚举。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

### C1-REVIEW-02-未修复-低-`_diagnostics_with_round_error` 复用 `fatal_errors` 计数器记录可恢复异常

- **入口/函数**: `WaitPollerSupervisor._run_loop` 和 `_diagnostics_with_round_error`。
- **文件(行号)**: `dayu/host/wait_adapter.py:1902`、`dayu/host/wait_adapter.py:1546`
- **输入场景**: 任意 poller `_poll_once()` 抛出非 self-close 异常。
- **实际分支**: `_run_loop` except 分支调用 `_diagnostics_with_round_error`，该函数将 `fatal_errors` 递增 1。loop status 保持 `RUNNING`。
- **预期行为**: 可恢复的单轮异常与不可恢复的 self-close/fatal 异常应在 diagnostics 中有独立计数，以便运维区分瞬态抖动和永久故障。
- **实际行为**: 两种异常共享 `fatal_errors` 字段。单轮瞬态异常也会递增 `fatal_errors`，但 loop status 为 `RUNNING`（非 `FAILED`）。
- **直接证据**: `dayu/host/wait_adapter.py:1902` — `fatal_errors=diagnostics.fatal_errors + 1`；`dayu/host/wait_adapter.py:1874` — `_diagnostics_with_fatal_error` 同样递增 `fatal_errors` 且设 status 为 `FAILED`。
- **影响**: 监控系统或运维人员无法通过 `fatal_errors` 计数器区分"单轮瞬态异常后自动恢复"和"supervisor 永久停止"。实现 artifact 已记录此 naming mismatch 作为已知 residual risk。
- **建议改法和验证点**: 新增 `round_errors` 计数器专用于可恢复异常；保留 `fatal_errors` 仅用于 `FAILED` 状态的不可恢复异常。或在现有字段上添加 `status` 辅助判断。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

## Open Questions

- 无。

## Residual Risk

1. **`STALE_CALLBACK` 不可达但已发布**: 若存在外部消费者检查该枚举值，删除是 breaking change。需确认 callback adapter 的公共契约版本策略。
2. **`fatal_errors` 语义双关**: runtime status 区分了 `RUNNING` vs `FAILED`，行为正确；但 diagnostics 字段命名可能导致监控误判。后续 diagnostics 清理应拆分计数器。
3. **self-close 检测基于字符串比较**: `_WAIT_POLLER_SELF_CLOSE_ERROR` 常量在 `close()` 和 `_run_loop()` 之间通过字符串相等传递。单模块内可控，但若未来 `close()` 重构可能引入不一致。
4. **Batch C2 未覆盖**: dispatch、promotion、cancel predispatch、tool accept duplicate index、Engine retry 不在本次 review 范围。
5. **边界 owner 统一后的行为变更**: 过期 wait 现在 fail closed（保持 `WAITING` + late diagnostic + poll backoff），不再是业务终态。若产品策略后续需要过期自动终态化，需由 Host wait policy owner 新增决策。

## Review Verification

### 语义所有权验证

| 找到 | 状态 | 证据 |
| --- | --- | --- |
| Host wait owner 是 deadline/expires 解析的唯一 owner | ✅ | `wait_boundary.py` 是唯一解析 `deadline_at`/`expires_at` 的模块；callback 的 `_stale_status_or_none` 和 fins 的 `_wait_boundary_lost` 均已删除。 |
| callback 不再修复/guess/转换 Host wait 边界语义 | ✅ | `wait_callback.py` 删除 `_stale_status_or_none` 和 `parse_utc_timestamp` import；callback 只做认证、digest 校验、delegate to resolve_wait。 |
| Fins provider adapter 不再读取 Host deadline | ✅ | `dayu/fins/ingestion/wait_adapter.py` 删除 `_wait_boundary_lost` 和 `parse_utc_timestamp` import；transient unavailable 直接返回 `WaitPollNotReady`。 |
| expired/invalid 结果在 callback 和 poll 间一致 | ✅ | 两者均通过 `resolve_wait` owner path 处理；callback 得到 `INVALID_WAIT_STATE`；poll 通过 `_release_expired_or_invalid_boundary` 释放 claim 并记录 backoff。 |
| supervisor 瞬态异常隔离不隐藏不可恢复故障 | ✅ | self-close RuntimeError 精确匹配并触发 `FAILED`；其它异常仅记录 round error 并继续。 |
| `_resolve_claimed_wait` recovery read 失败不 crash supervisor | ✅ | 内层 try/except 捕获 read 失败，返回 `INVALID_STATE`，claim 通过 `_release_with_backoff` 释放。 |
| cancelled abandon CAS_LOST 释放当前 claim | ✅ | `_abandon_cancelled_wait` CAS_LOST 分支调用 `_release_with_backoff`；测试验证 `poll_claim_id is None`。 |
| `waiting.py` 使用注入的 EventLogStore | ✅ | `_wait_tool_call_requested_event` 和 `_validate_wait_request_arguments_digest` 接收 `event_log_store` 参数；测试验证 DI store 被调用。 |
| 测试断言 owner 级 contract | ✅ | callback 测试改为断言 `resolve_wait` owner 行为（late event、WAITING status）；poller 测试断言 Host-owned 边界拦截在 provider 调用前。 |

### 编码约束验证

| 检查项 | 状态 |
| --- | --- |
| 无兼容性 shim / re-export | ✅ (除 STALE_CALLBACK 不可达枚举) |
| 无 weak typing / `Any` / `object` | ✅ |
| docstring 完整 | ✅ |
| 无 Batch C2 scope creep | ✅ |

### 结论

**Approved with minor observations.** Batch C1 正确实现了 Host wait 边界语义的唯一所有权集中，supervisor 瞬态异常隔离、claim 释放、recovery read 容错和 EventLogStore DI 均基于直接证据验证通过。发现 2 个低严重程度的 maintainability 问题（不可达枚举和 diagnostics 计数器语义双关），均不阻塞 merge。
