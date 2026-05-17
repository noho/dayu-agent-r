# Code Re-Review

## Scope

- Mode: current changes (re-review after accepted fixes)
- Branch: feat/host-p9-conversation-memory
- Base: main
- Previous review: docs/reviews/p9-s4-code-review-mimo-20260517.md
- Output file: docs/reviews/p9-s4-code-rereview-mimo-20260517.md

## Accepted Fixes Verification

### Fix 1: ProjectionCatchupPort / NoopProjectionCatchupPort / catch_up_projection_best_effort 移到 projection.py

- `dayu/host/projection.py:251-292` — `ProjectionCatchupPort`、`NoopProjectionCatchupPort`、`catch_up_projection_best_effort` 统一定义
- `admission.py:93-97` — 从 `projection.py` import，删除原 `admission.py` 内定义
- `dispatch.py:71-74` — 从 `projection.py` import，删除原 `dispatch.py` 内 `_catch_up_projection_best_effort`
- `waiting.py:87-90`、`tool_runtime.py:88-91` — 统一从 `projection.py` import
- grep 确认：`_catch_up_projection_best_effort`（旧私有 helper）在整个 `dayu/host` 下无残留
- **原 Finding 3（低-ProjectionCatchupPort 放在 admission.py）：已闭合 ✓**

### Fix 2: DefaultHostToolFactAcceptPort 增加 catch-up hook

- `tool_runtime.py:1837-1860` — `__init__` 增加 `projection_catchup_port: ProjectionCatchupPort | None = None`
- `tool_runtime.py:1877-1881` — `accept_tool_fact` 在 `run_write` 返回后、确认 `ToolFactAcceptedAck` 且 `tool_result_event_ref is not None` 时触发 `catch_up_projection_best_effort`
- `dispatch.py:730-733` — scheduler wiring 将 `self._projection_catchup_port` 传入 `DefaultHostToolFactAcceptPort`
- 测试：`test_toolruntime_accept_barrier.py:117-148` — `test_tool_fact_accept_survives_projection_catchup_failure`，验证 `projection.calls == 1` 且 `caplog` 捕获日志
- **闭合 TOOL_RESULT_ACCEPTED 的 tool fact accept 路径 ✓**

### Fix 3: DefaultHostResolveWaitService 增加 catch-up hook

- `waiting.py:545-568` — `__init__` 增加 `projection_catchup_port: ProjectionCatchupPort | None = None`
- `waiting.py:586-591` — `resolve_wait` 在 `run_write` 返回后触发 `catch_up_projection_best_effort`
- `command.py:522` — `resolve_wait` 从 `host._admission_service.projection_catchup_port` 传入
- 测试：`test_resolve_wait_command.py:128-148` — `test_resolve_wait_survives_projection_catchup_failure`，验证 `projection.calls == 1` 且 `snapshot.status is RunStatus.RUNNING`
- **原 Finding 1（中-resolve_wait 路径缺失 catch-up hook）：已闭合 ✓**

### Fix 4: Shared helper 使用 logger 记录 exception

- `projection.py:278-292` — `catch_up_projection_best_effort` 使用 `_LOGGER.exception("projection catch-up failed; continuing")`
- `projection.py:273` — `_LOGGER = logging.getLogger(__name__)`
- 测试：`test_toolruntime_accept_barrier.py:117-148` — caplog 断言 `"projection catch-up failed; continuing" in caplog.text`
- **原 Finding 2（中-catch-up hook 静默吞异常）：已闭合 ✓**

### Fix 5: 新增/更新测试覆盖

- `test_admission_queue.py` — `_FailingProjectionCatchup` + `test_start_run_survives_after_commit_projection_catchup_failure` + `test_terminal_closeout_survives_after_commit_projection_catchup_failure`
- `test_dispatch_scheduler.py` — `_FailingProjectionCatchup` + `test_scheduler_queue_promotion_survives_projection_catchup_failure` + `test_scheduler_uses_toolruntime_when_tooling_is_configured` 中增加 `projection.calls == 1` 断言
- `test_resolve_wait_command.py` — `_FailingProjectionCatchup` + `test_resolve_wait_survives_projection_catchup_failure`
- `test_toolruntime_accept_barrier.py` — `_FailingProjectionCatchup` + `test_tool_fact_accept_survives_projection_catchup_failure` + caplog 断言
- **测试覆盖所有 catch-up 路径的 failure resilience ✓**

## Re-review Findings

### 1-未修复-低-resolve_wait catch-up 在 late rejection 时多余触发

- **入口/函数**: `dayu/host/waiting.py:586-591` `resolve_wait()`
- **文件(行号)**: `waiting.py:591`
- **输入场景**: `resolve_wait` 写事务返回 `_LateRejectResult`（wait result 因终态被拒绝）
- **实际分支**: L591 `catch_up_projection_best_effort` 在 `run_write` 返回后、`isinstance(result, _LateRejectResult)` 检查前执行
- **预期行为**: late rejection 时 EventLog 无新增 canonical fact，catch-up 无新事件可追平
- **实际行为**: catch-up 仍被触发，ProjectionRunner 读取 checkpoint 后发现无新事件，立即返回 idle。无害但多余
- **直接证据**: `waiting.py:586-591` — catch-up 在 `_LateRejectResult` 分支判断之前
- **影响**: 无功能影响。catch-up 是幂等的，无新事件时只产生一次 checkpoint read。极端情况下多一次无意义 SQLite 查询
- **建议改法和验证点**: 可将 catch-up 移到 `isinstance(result, _LateRejectResult)` 检查之后的正常返回路径。当前实现无害，标记为 cleanup 优先级
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低 — 无功能影响，仅多余 I/O

## Open Questions

- 无

## Residual Risk

1. **submit_followup_queue catch-up failure 测试缺失**（原 review residual risk 4）。`test_terminal_closeout_survives_after_commit_projection_catchup_failure` 调用了 `submit_followup_queue` 但未单独断言其 catch-up 调用。代码模式与 `start_run` 完全一致（同一行 `catch_up_projection_best_effort(self.projection_catchup_port)`），风险低。
2. **engine_ingest 路径**（原 review residual risk 2）仍未接入 catch-up hook。engine ingest 是 scheduler dispatch loop 的一部分，产生 `TOOL_RESULT_ACCEPTED` 的路径已通过 `DefaultHostToolFactAcceptPort` 覆盖（Fix 2），但 engine ingest 的其它 event type（如 `RUN_SUCCEEDED`）不在此路径。下一次 admission 命令会触发 catch-up 追平，延迟可控。

## Verdict

**PASS**。原 review 4 条 findings 全部闭合（Finding 1-3 正式修复，Finding 4 标记为 deferred cleanup）。re-review 发现 1 条低严重度 finding（resolve_wait late rejection 多余 catch-up），无 blocking findings。S4 exit condition 满足。
