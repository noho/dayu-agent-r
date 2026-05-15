# Host Phase 6 Aggregate Re-Review — AgentDS

- **Review type**: adversarial re-review of accepted aggregate blocker fix
- **Review date**: 2026-05-15
- **Previous artifact**: `docs/reviews/host-phase6-aggregate-review-ds-20260515.md`
- **Controller adjudication**: `docs/reviews/host-phase6-aggregate-review-controller-adjudication-20260515.md`
- **Fix artifact**: `docs/reviews/host-phase6-aggregate-fix-run-local-duplicate-governance-20260515.md`
- **Branch**: `feat/host-phase-6-toolruntime`
- **Verdict**: PASS — P6-AGG-F1 is fixed; no regressions detected

## Scope

### Changes re-reviewed

| File | Delta | Role |
|------|-------|------|
| `dayu/host/tool_runtime.py` | +200/-25 | New `_RunLocalDuplicateGovernanceState`, `InMemoryRunScopedDuplicateGovernanceRegistry`, `RunScopedDuplicateGovernanceRegistry` protocol; `InMemoryRunLocalDuplicateGovernance` accepts optional shared `state`; `DefaultToolRuntimeFactory` uses registry when provided; `__all__` updated |
| `dayu/host/dispatch.py` | +34/-3 | Scheduler owns `InMemoryRunScopedDuplicateGovernanceRegistry`; injects into `ToolRuntimeBuildRequest`; cleanup on terminal closeout, cancel, and scheduler close |
| `tests/host/test_toolruntime_duplicate_governance.py` | +73/-2 | `test_new_runtime_does_not_inherit_duplicate_index` → `test_same_run_runtime_handles_share_duplicate_index` + new `test_different_runs_do_not_share_duplicate_index`; `_executor` helper accepts `run_id` and `duplicate_governance_registry` params |
| `tests/host/test_dispatch_scheduler.py` | +2/-0 | `active_run_count()` assertions in `test_scheduler_uses_toolruntime_when_tooling_is_configured` |
| `dayu/host/README.md` | +1/-1 | Description updated from "索引只存在于当前 ToolRuntime 实例内" to registry-based shared fact |

### Verification

| Item | Result |
|------|--------|
| `pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_dispatch_scheduler.py -q` | 28 passed |
| `pytest tests/host -q` | 349 passed |
| `pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean |

---

## Findings

### P6-AGG-F1 — 已修复 — 确认同 Run 同进程多 ToolRuntime handle 共享 duplicate 记忆

原始发现：`InMemoryRunLocalDuplicateGovernance._entries_by_key` 仅存在于单个 ToolRuntime 实例内，同一 Run 的后续 Attempt 创建新 ToolRuntime 时丢失 duplicate 记忆。

修复方案：
1. 引入 `RunScopedDuplicateGovernanceRegistry` typed protocol 与 `InMemoryRunScopedDuplicateGovernanceRegistry` 实现。
2. 引入 `_RunLocalDuplicateGovernanceState` 私有类封装共享内存索引（含 `RLock`）。
3. `InMemoryRunLocalDuplicateGovernance` 通过可选 `state` 参数绑定共享索引；未提供时仍创建私有索引以保持向后兼容。
4. `DefaultToolRuntimeFactory.create_tool_runtime` 在 `request.duplicate_governance_registry` 非 None 时调用 `registry.duplicate_governance_for_run(run_id=..., policy=...)` 获取共享索引的 governance port。
5. `HostDispatchScheduler` 在 `__init__` 创建 registry，在 `_run_input_builder_for_dispatch` 注入 registry，在三处清理点释放内存。

**逐路径验证**：

**路径 1 — 共享语义链路**：`dispatch.py:332-333` → `dispatch.py:730` → `tool_runtime.py:2600-2607` → `tool_runtime.py:1648-1689`

- 入口：`dispatch.py:332` scheduler 构造时创建 `InMemoryRunScopedDuplicateGovernanceRegistry()`
- 注入：`dispatch.py:730` 将 `self._duplicate_governance_registry` 传入 `ToolRuntimeBuildRequest`
- 消费：`tool_runtime.py:2600-2607` `create_tool_runtime` 中检查 registry 非 None 时调用 `registry.duplicate_governance_for_run(run_id=request.execution_scope.run_id, ...)`
- 结果：`registry.duplicate_governance_for_run` (`tool_runtime.py:1665-1689`) 按 `run_id` 查找或创建 `_RunLocalDuplicateGovernanceState`，返回绑定该共享 state 的 `InMemoryRunLocalDuplicateGovernance`
- 数据流：同 `run_id` 的多个 `InMemoryRunLocalDuplicateGovernance` 实例共享同一个 `_RunLocalDuplicateGovernanceState._entries_by_key`，通过 `_RunLocalDuplicateGovernanceState.find()`/`record()` 读写，内部 `RLock` 保护
- 测试：`test_same_run_runtime_handles_share_duplicate_index` 验证 `first_tool.call_count == 1`、`second_tool.call_count == 0`、`outcome.records[0].outcome.result.value == {"accepted": "first-runtime"}`、`candidates[0].tool_fact_kind is REUSE`、prior refs 正确引用 first 的 accepted refs

**路径 2 — 不同 Run 隔离**：`tool_runtime.py:1662-1689`

- `_states_by_run_id` 以 `run_id` 为 key，不同 run_id 映射到不同 `_RunLocalDuplicateGovernanceState`
- 测试：`test_different_runs_do_not_share_duplicate_index` 验证两个不同 run_id 的工具各被调用 1 次（`first_tool.call_count == 1`、`second_tool.call_count == 1`），无跨 Run reuse

**路径 3 — 正常 terminal closeout 清理**：`dispatch.py:927-1012`

- `_consume_worker_events` 中三个 terminal closeout 出口均通过 `_ingest_closed_run(result)` 设置 `run_terminal_closed`
- 出口 1（line 958）：`ingestor.close_clean_eof()` 返回 terminal closeout
- 出口 2（line 971）：`ingestor.close_worker_lost()` stream error
- 出口 3（line 992/1002）：`ingestor.ingest()` 返回 terminal closeout 或 ingest exception
- `finally` 块（line 1005-1006）：`if run_terminal_closed: clear_run(record.run_id)`
- `_ingest_closed_run` 辅助函数（line 1016-1028）：只在 `terminal_closeout=True` 且 status 为 `ACCEPTED` 或 `DUPLICATE` 时返回 True，正确过滤非终态事件和 rejected ingest

**路径 4 — cancel 清理**：`dispatch.py:908`

- `_cancel_starting_attempt_inner` 在写入 cancel 事件后调用 `self._duplicate_governance_registry.clear_run(record.run_id)`

**路径 5 — scheduler close 兜底清理**：`dispatch.py:468`

- `close()` 在清理 lane controller 后调用 `self._duplicate_governance_registry.clear_all()`
- 测试：`test_scheduler_uses_toolruntime_when_tooling_is_configured` 在 `finally` 块中 `scheduler.close()` 后断言 `active_run_count() == 0`

**P6-AGG-F1 修复确认：已修复。** 同 Run 同进程多 ToolRuntime handle 通过 registry 共享 duplicate 记忆；不同 Run 隔离；清理路径覆盖正常终态、cancel 和 scheduler close。

---

### 无回归 — 无新增 durable ledger / crash recovery 承诺

- `_RunLocalDuplicateGovernanceState` 和 `InMemoryRunScopedDuplicateGovernanceRegistry` 均为纯内存数据结构（`dict` + `RLock`）
- 无 SQLite 表、无 EventLog 写入、无 durable transaction
- README 描述明确："不写 durable duplicate ledger，不承诺 crash / restart recovery"
- `InMemoryRunLocalDuplicateGovernance` 未注入 shared state 时行为与原来完全一致（创建私有 `_RunLocalDuplicateGovernanceState()`），向后兼容

### 无回归 — 线程安全

- `_RunLocalDuplicateGovernanceState` 的 `find()`/`record()` 内部持有 `RLock`
- `InMemoryRunScopedDuplicateGovernanceRegistry` 的 `duplicate_governance_for_run()`/`clear_run()`/`clear_all()`/`active_run_count()` 内部持有 `RLock`
- `RLock` 的选择合理：所有涉及共享 state 的方法均为同步方法（非 `async`），`RLock` 在同步上下文中足够且不引入 asyncio 调度问题

### 无回归 — 类型 & import

- `from threading import RLock` 是新增 import，标准库，无分层违规
- 新增 `RunScopedDuplicateGovernanceRegistry` Protocol 和 `InMemoryRunScopedDuplicateGovernanceRegistry` 实现类均进入 `__all__`
- 无 `Any`/`object` 新增
- `ToolRuntimeBuildRequest.duplicate_governance_registry` 字段类型为 `RunScopedDuplicateGovernanceRegistry | None`，默认 `None`，向后兼容

### 无回归 — README 一致性

- `dayu/host/README.md` 描述从 "索引只存在于当前 ToolRuntime 实例内" 更新为 "在同一 Host 进程内按 Run 持有短生命周期 duplicate 记忆，使同一 Run 的多个 ToolRuntime handle 可共享 accepted fact"，与代码实现一致
- 测试新增 `active_run_count()` 断言覆盖 scheduler 中 registry 生命周期

---

## P6-AGG-F2 追踪

AgentDS 原 review 中 P6-AGG-F2（`EffectiveToolBundleBuilder`/`DefaultToolRuntimeFactory` 重复构造）的裁决为 non-blocking optional cleanup。本次 fix 未改变这两者的构造模式——`_run_input_builder_for_dispatch` 仍然每 dispatch 创建新 `DefaultToolRuntimeFactory(EffectiveToolBundleBuilder())`。由于 factory 和 builder 当前为轻量无状态对象（无连接池、无缓存、无持久化），实际无性能或正确性影响。Controller 裁决此项可在自然落入 F1 fix 时顺带处理，但 F1 方案选择了 registry 注入而非 factory 提升，两种方案等价。此项继续作为低优先级维护项追踪，不阻塞 P6 exit。

---

## Residual Risks

1. **`_consume_worker_events` 的 `envelope`/`ingestor`/`handle.events()` 构造在 try 块内**（dispatch.py:928-947）：若这些 setup 代码抛出异常（可能性极低，`LocalEngineEnvelope` 为 dataclass，`EngineEventIngestor` 为轻量构造），`run_terminal_closed` 仍为 False，`clear_run` 不会执行。但 `cancel_starting_attempt_inner` 或 `scheduler.close()` 的路径最终会兜底清理。此边界与 fix 前的原有行为一致，fix 未引入新风险。

2. **`_RunLocalDuplicateGovernanceState` 的 `record()` 无条件覆盖**（tool_runtime.py:1534-1545）：与 P6-S5 原有语义一致（overwrite），经 caller `_record_duplicate_accepted` guard 过滤后仅成功执行 callable 的 ALLOW entry 才写入，语义正确。此行为未由本次 fix 改变。

3. **registry 在 scheduler 内的生命周期**：scheduler 是整个 Host 实例的生命周期内对象。registry 在 scheduler `__init__` 创建、`close()` 清理。若 scheduler 生命周期极长（如长运行期 Service），registry 会在 Run 终态前持有活跃 Run 的 state。正常路径会在 terminal closeout 时清理；异常路径（如 scheduler 被强制销毁而不调用 `close()`）会因 GC 释放。这与任何 in-memory Python 对象的行为一致，不算内存泄漏。

4. **`_ingest_closed_run` 依赖 `EngineIngestResult.terminal_closeout`**：若 ingestor 的 `terminal_closeout` 实现遗漏某些 Run 终态路径，`clear_run` 也不会被调用。但 ingestor 实现不在本次 fix 范围内，且 Run 终态后的 stale state 条目大小可控（每个 Run 的 `_entries_by_key` 跟随该 Run 的工具调用次数增长，Run 终态后不再增长）。

---

## Final Verdict

**PASS**

P6-AGG-F1 已修复。`InMemoryRunScopedDuplicateGovernanceRegistry` 提供了 Run-scoped in-memory duplicate index owner，使同一 Run 的多个 ToolRuntime handle 共享 duplicate accepted 记忆。不同 Run 正确隔离。清理路径覆盖正常 terminal closeout、cancel 和 scheduler close。无 durable ledger、crash recovery 承诺或其他 scope creep。无类型/测试/架构回归。349 项测试全部通过，pyright clean。Phase 6 可进入 ready-to-create-PR 流程。
