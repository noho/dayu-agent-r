# WU-PROJ-01 Slice 3 Code Review — AgentMiMo

## 元数据

- Work unit: `WU-PROJ-01`
- Slice: `Slice 3 - Bounded memory projection catch-up / rebuild`
- Gate: code review
- Reviewer: AgentMiMo
- 日期: 2026-06-11
- Implementation artifact: `docs/reviews/wu-proj-01-slice3-implementation-codex.md`
- 设计真源: `docs/host/design.md`; `docs/engine/design.md`
- Accepted plan: `docs/host/wu-proj-01-compact-material-truth-and-bounded-memory-catchup-plan.md`

## Review Scope

未提交 diff（`git diff HEAD`），涉及文件：

- `dayu/host/memory_repair.py`
- `dayu/host/dispatch.py`
- `dayu/host/open_host.py`
- `tests/host/test_memory_repair.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_logging.py`
- `docs/host/issues-implementation-control.md`（仅 gate bookkeeping）

## Verdict

**PASS-WITH-FINDINGS**

实现正确覆盖了 accepted plan 的 Slice 3 要求。bounded loop、budget 类型、stop reason、dispatch guard、open_host best-effort 注入、diagnostics 均与 plan 和 design 对齐。测试覆盖了关键路径。无 blocking findings。

## Findings

### Severity: LOW

#### L1: dispatch before-worker catch-up happy path 无独立集成测试

**文件**: `tests/host/test_open_host_runtime.py`

`test_open_host_dispatch_memory_catchup_budget_exhausted_blocks_worker_accept` 验证了 budget exhausted 阻断 `worker.accept` 的路径，但没有对应的 happy path 测试验证 catch-up 成功覆盖 required cursor 后 `worker.accept` 正常执行、Run 最终 `SUCCEEDED`。

现有 `test_submit_followup_queue_auto_wakes_scheduler` 间接覆盖了 happy path（因为 after-commit catch-up 会先追平 memory projection），但该测试没有显式断言 dispatch 前 catch-up 的 `target_reached` 行为。

**建议**: 补充一个测试，用 monkeypatch 让 after-commit catch-up 不追平（或只追平部分），然后验证 dispatch 前 required catch-up 成功后 worker 正常 accept 并产出 final answer。

**裁决**: 不阻塞。现有间接覆盖 + fake runner 测试已证明 bounded loop 的 `target_reached` 分支正确。

#### L2: `_safe_closeout_worker_startup_timeout` 语义重载

**文件**: `dayu/host/dispatch.py:2734-2765`

`_MemoryProjectionDispatchDiagnosticError` 被捕获后调用 `_safe_closeout_worker_startup_timeout(reason=_MEMORY_PROJECTION_REPAIR_REQUIRED_REASON)`。该 closeout 写入 `AttemptStatus.FAILED` + `RunStatus.FAILED`，与真正的 worker startup timeout 走同一 closeout 路径。

虽然 `reason` 参数区分了 `"memory_projection_repair_required"` vs `"worker_startup_timeout"`，且 warning log 包含完整的 diagnostic 字段（`operation`、`required_event_sequence`、`started_cursor`、`finished_cursor`、`events_scanned`、`batches_used`、`stop_reason`、`budget_exhausted`、`failures`），但 closeout 方法名 `_closeout_worker_startup_timeout` 语义上暗示 "timeout"，可能让后续维护者误判根因。

**建议**: 不阻塞本 slice。后续可考虑将 closeout 方法重命名为 `_closeout_worker_startup_failure` 或新增 `_closeout_memory_projection_failure` 专用路径，使 reason → closeout 语义更精确。当前 diagnostic payload 已足够区分根因。

**裁决**: 不阻塞。已有结构化 diagnostic 和不同 reason 字符串。

#### L3: `_memory_projection_catchup_budget` unsupported purpose 分支无测试

**文件**: `dayu/host/dispatch.py:344-345`

`_memory_projection_catchup_budget` 的 `else` 分支 `raise HostDurableError("unsupported memory projection repair purpose")` 没有直接测试覆盖。该分支当前不可达（因为 `MemoryProjectionRepairPurpose` 只有三个枚举值且 if/elif 已全覆盖），但作为防御性代码应有测试固定。

**建议**: 补充一个单元测试断言传入非法 purpose 时抛出 `HostDurableError`。或在代码中用 `assert_never` 替代 `else` + `raise`，让 pyright 在新增枚举值时强制处理。

**裁决**: 不阻塞。当前不可达分支。

### Severity: INFO

#### I1: budget 常量为模块级私有常量，符合 plan 约束

`_MEMORY_PROJECTION_BEST_EFFORT_MAX_BATCHES = 1`、`_MEMORY_PROJECTION_REQUIRED_BEFORE_DISPATCH_MAX_BATCHES = 16`、`_MEMORY_PROJECTION_REBUILD_BEFORE_DISPATCH_MAX_BATCHES = 32` 均为 `dispatch.py` 模块级私有常量，不进入 public API、config schema 或 durable schema。符合 plan "第一版只支持内部常量取值" 的约束。

#### I2: `_CompositeProjectionCatchupPort` close flush 不注入 budget

`open_host.py` 的 close path 通过 `_CompositeProjectionCatchupPort.catch_up_projection()` 调用各子 port。其中 `_MemoryProjectionCatchupPort.catch_up_projection()` 使用 `_after_commit_memory_projection_budget(batch_size)` 构造 best-effort budget（`max_batches=1`）。这意味着 close flush 也是 bounded 的，不会无界追平。

这符合 plan 约束："close flush 需要追到 idle，应在 close-only helper 中显式传 `MemoryProjectionCatchupBudget.for_close_flush(...)`"。当前实现没有 `for_close_flush` 工厂方法，而是复用 best-effort budget，语义等价且更简单。

#### I3: 日志字段完整性

`_log_memory_projection_result` 在三个分支（failure / budget_exhausted / committed）均记录了完整的 diagnostic 字段：`consumer_id`、`started_cursor`、`finished_cursor`、`events_scanned`、`events_matched`、`events_applied`、`duplicates`（或省略）、`batches_used`、`stop_reason`、`max_event_sequence`、`max_batches`、`max_scanned_events`。`budget_exhausted` 和 `target_reached` 在 committed 分支有记录。符合 plan 对 diagnostic 粒度的要求。

## Checklist 逐项裁决

| 检查项 | 结果 | 说明 |
|--------|------|------|
| `MemoryProjectionCatchupBudget` 只含 `max_batches`/`max_scanned_events`/`purpose`，无 `timeout_seconds` | ✅ | `memory_repair.py:50-62` |
| bounded loop stop reasons: `failure`/`idle`/`target_reached`/`budget_exhausted` | ✅ | `memory_repair.py:41-47` |
| `batch_size` 仍是单批上限，budget 是总预算 | ✅ | `_bounded_batch_limit` 和 loop 条件 |
| budget exhausted 不是 projection failure，不写 projection failure row | ✅ | `budget_exhausted` 独立于 `failures` 计数 |
| dispatch before-worker catch-up 未 target reached 阻断 `worker.accept`，不触发 recovery | ✅ | `_raise_if_memory_projection_target_not_reached` → `_MemoryProjectionDispatchDiagnosticError` → closeout with reason |
| lag rebuild 只重建到 required cursor，预算耗尽后按 memory repair failure 收口 | ✅ | `max_event_sequence=exc.repair_request.required_event_sequence` + `_raise_if_memory_projection_target_not_reached` |
| open_host after-commit catch-up bounded best-effort，不阻塞 command path | ✅ | `_after_commit_memory_projection_budget` → `max_batches=1` |
| diagnostics/logging 足够 | ✅ | run/attempt/execution、required/started/finished cursor、events/batches、stop_reason、budget 均有记录 |
| tests 覆盖 required cursor reached | ✅ | `test_catch_up_stops_when_target_reached_before_idle` |
| tests 覆盖 budget exhausted | ✅ | `test_catch_up_budget_exhausted_stops_before_idle` + `test_rebuild_budget_exhausted_reports_target_not_reached` |
| tests 覆盖 partial checkpoint advance | ✅ | `test_catch_up_budget_exhausted_advances_only_processed_checkpoint` |
| tests 覆盖 open_host budget injection | ✅ | `test_open_host_memory_projection_port_uses_best_effort_budget` |
| tests 覆盖 dispatch worker accept guard | ✅ | `test_open_host_dispatch_memory_catchup_budget_exhausted_blocks_worker_accept` |
| pyright/test validation 可信 | ✅ | 9 + 12 + 4 tests passed, pyright 0 errors |

## Gate Bookkeeping

`docs/host/issues-implementation-control.md` 的 WU-PROJ-01 Slice 3 gate bookkeeping 状态为 "implementation completed; code review pending"，review artifacts expected 包含本 artifact。gate bookkeeping 与实现一致。

## Blocking Open Questions

无。

## Residual Risks

- `WU-PROJ-01-S2-R1`（material source failure exception taxonomy）仍为 deferred-with-owner。本 slice 未触及该问题，不新增也不关闭。
- budget 常量取值（1/16/32 batches）为第一版内部值，production profiling 后可能需要调参。当前不暴露为 public config，符合 plan 约束。
